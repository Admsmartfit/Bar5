import json

from odoo import fields
from odoo.tests import HttpCase, tagged

ROTA = "/api/boteco/webhook/cotacao_recebida"


@tagged("post_install", "-at_install", "boteco")
class TestApiCotacoes(HttpCase):
    """19/11/2026: cotações limpas do serviço externo -> radar, RFQ, oportunidade e ideia de promoção."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.write({"boteco_flag_cotacoes_externas": True, "boteco_flag_radar_precos_oportunidade": True,
                           "boteco_radar_queda_pct": 10.0, "boteco_radar_so_chave": False,
                           "boteco_estoque_dias_cobertura": 21})
        un = cls.env.ref("uom.product_uom_unit")
        kg = cls.env.ref("uom.product_uom_kgm")
        Produto = cls.env["product.product"]
        cls.cerveja = Produto.create({
            "name": "Cerveja 600 ml", "default_code": "CERV-600", "barcode": "7891149101010", "purchase_ok": True,
            "is_storable": True, "uom_id": un.id, "uom_po_id": un.id, "standard_price": 10.0,
            "available_in_pos": True, "sale_ok": True, "list_price": 18.0})
        cls.cebola = Produto.create({"name": "Cebola", "default_code": "CEB", "purchase_ok": True, "is_storable": True,
                                     "uom_id": kg.id, "uom_po_id": kg.id, "standard_price": 4.0})
        cls.fornecedor = cls.env["res.partner"].create({"name": "Atacadão Teste", "supplier_rank": 1,
                                                        "boteco_id_externo": "atacadao"})
        cls.token = cls.env["boteco.cotacoes"]._token()
        cls.Historico = cls.env["boteco.historico.preco"]
        cls.Oportunidade = cls.env["boteco.oportunidade.compra"]

    def _post(self, dados, token=None, cabecalho="Authorization"):
        self.env.flush_all()
        valor = ("Bearer %s" % (token or self.token)) if cabecalho == "Authorization" else (token or self.token)
        r = self.url_open(ROTA, data=json.dumps(dados), headers={"Content-Type": "application/json", cabecalho: valor})
        self.env.invalidate_all()
        return r

    def _comprar(self, produto, precos):
        """Compras confirmadas (base do preço médio ponderado)."""
        for qtd, preco in precos:
            pedido = self.env["purchase.order"].create({"partner_id": self.fornecedor.id, "order_line": [
                fields.Command.create({"product_id": produto.id, "product_qty": qtd, "price_unit": preco})]})
            pedido.button_confirm()

    # ------------------------------------------------------------------ segurança
    def test_sem_token_ou_token_errado_401(self):
        self.assertEqual(self._post({"preco_cotado": 1}, token="errado").status_code, 401)
        self.assertEqual(self.url_open(ROTA, data="{}", headers={"Content-Type": "application/json"}).status_code, 401)
        self.assertTrue(self.env["boteco.cotacao.log"].search([("resultado", "=", "recusado")]))
        self.assertEqual(self._post({"cotacoes": []}, cabecalho="X-API-Key").status_code, 200)

    def test_desligado_responde_503(self):
        self.company.boteco_flag_cotacoes_externas = False
        self.assertEqual(self._post({"cotacoes": []}).status_code, 503)

    # ------------------------------------------------------------------ aplicação
    def test_caixa_vira_preco_por_unidade_atualiza_radar_fornecedor_e_rfq(self):
        rfq = self.env["purchase.order"].create({"partner_id": self.fornecedor.id, "order_line": [
            fields.Command.create({"product_id": self.cerveja.id, "product_qty": 48, "price_unit": 9.0})]})
        r = self._post({"id_fornecedor": "atacadao", "id_produto_interno": "CERV-600", "unidade_medida": "cx",
                        "quantidade_embalagem": 24, "preco_cotado": 228.0, "descricao": "Brahma 600 cx c/24"}).json()
        item = r["resultados"][0]
        self.assertEqual(item["status"], "ok")
        self.assertAlmostEqual(item["preco_unidade_insumo"], 9.5)
        self.assertEqual(item["rfq_atualizadas"], 1)
        self.assertAlmostEqual(rfq.order_line.price_unit, 9.5)
        cotacao = self.Historico.search([("product_id", "=", self.cerveja.id), ("origem", "=", "servico_externo")])
        self.assertAlmostEqual(cotacao.preco_unitario, 9.5)
        info = self.env["product.supplierinfo"].search([("partner_id", "=", self.fornecedor.id),
                                                        ("product_tmpl_id", "=", self.cerveja.product_tmpl_id.id)])
        self.assertAlmostEqual(info.price, 9.5)

    def test_codigo_de_barras_gramas_e_lote_com_pendencias(self):
        r = self._post({"cotacoes": [
            {"id_fornecedor": self.fornecedor.id, "codigo_barras": "7891149101010", "unidade_medida": "un", "preco_cotado": 9.8},
            {"id_fornecedor": "atacadao", "id_produto_interno": "CEB", "unidade_medida": "g", "preco_cotado": 0.0036},
            {"id_fornecedor": "atacadao", "id_produto_interno": "NAO-EXISTE", "unidade_medida": "un", "preco_cotado": 5,
             "descricao": "Coisa nova"},
            {"id_fornecedor": "atacadao", "id_produto_interno": "CEB", "unidade_medida": "l", "preco_cotado": 3},
            {"id_fornecedor": "desconhecido", "id_produto_interno": "CEB", "unidade_medida": "kg", "preco_cotado": 3},
        ]}).json()
        status = [x["status"] for x in r["resultados"]]
        self.assertEqual(status, ["ok", "ok", "revisar", "revisar", "recusado"])
        self.assertAlmostEqual(r["resultados"][1]["preco_unidade_insumo"], 3.6)  # R$ 0,0036/g = R$ 3,60/kg
        revisar = self.env["boteco.cotacao.revisar"].search([("partner_id", "=", self.fornecedor.id)])
        self.assertEqual(len(revisar), 2)
        self.assertEqual(r["aplicados"], 2)
        self.assertTrue(self.env["boteco.cotacao.log"].search([("resultado", "=", "parcial")]))

    # ------------------------------------------------------------------ inteligência
    def test_oportunidade_sugestao_e_ideia_de_promocao(self):
        self._comprar(self.cerveja, [(24, 10.0), (24, 10.0), (48, 11.0)])  # PMP = (240+240+528)/96 = 10,50
        self.cerveja.standard_price = 10.5
        self.env["stock.warehouse.orderpoint"].create({"product_id": self.cerveja.id, "product_min_qty": 24,
                                                       "product_max_qty": 120})
        gerente = self.env["res.users"].create({
            "name": "Gerente Radar", "login": "gerente_radar",
            "groups_id": [fields.Command.set([self.env.ref("base.group_user").id, self.env.ref("boteco_base.group_gerente").id])]})
        r = self._post({"id_fornecedor": "atacadao", "id_produto_interno": "CERV-600", "unidade_medida": "un",
                        "preco_cotado": 8.4}).json()
        oportunidade = self.Oportunidade.browse(r["resultados"][0]["oportunidade_id"])
        self.assertAlmostEqual(oportunidade.preco_medio, 10.5)
        self.assertAlmostEqual(oportunidade.queda_pct, 20.0)
        self.assertEqual(oportunidade.sugestao_qtd, 120 - self.cerveja.qty_available)
        self.assertIn(gerente, oportunidade.activity_ids.user_id)
        # Painel do dono e lista de compras
        self.assertEqual(self.env["boteco.painel"]._oportunidades_compra(self.company)[0]["insumo"], "[CERV-600] Cerveja 600 ml")
        lista = self.env["boteco.lista.compras"].create({})
        lista.action_gerar()
        linha = lista.linha_ids.filtered(lambda l: l.partner_id == self.fornecedor)
        self.assertIn("oportunidade", linha.itens)
        self.assertIn("120", linha.itens)
        # Ideia de promoção: a cerveja é revenda; o custo cai R$ 2,10 e o preço sugerido mantém a margem %
        ideia = oportunidade.marketing_ids
        self.assertEqual(ideia.product_id, self.cerveja)
        self.assertAlmostEqual(ideia.custo_novo, 8.4)
        self.assertAlmostEqual(ideia.preco_promocional, 14.4)  # 8,40 / (1 - 41,7%) = 14,40
        self.assertAlmostEqual(ideia.margem_promocional_pct, ideia.margem_atual_pct, delta=0.5)
        ideia.action_criar_oferta()
        self.assertEqual(ideia.oferta_id.preco, 14.4)
        self.assertEqual(ideia.oferta_id.estado, "rascunho")

    def test_queda_pequena_nao_gera_e_so_chave(self):
        self._comprar(self.cebola, [(10, 4.0)])
        self._post({"id_fornecedor": "atacadao", "id_produto_interno": "CEB", "unidade_medida": "kg", "preco_cotado": 3.8})
        self.assertFalse(self.Oportunidade.search([("product_id", "=", self.cebola.id)]))  # só 5% abaixo
        self.company.boteco_radar_so_chave = True
        self._post({"id_fornecedor": "atacadao", "id_produto_interno": "CEB", "unidade_medida": "kg", "preco_cotado": 2.0})
        self.assertFalse(self.Oportunidade.search([("product_id", "=", self.cebola.id)]))  # cebola não é chave
        self.cebola.boteco_insumo_chave = True
        self._post({"id_fornecedor": "atacadao", "id_produto_interno": "CEB", "unidade_medida": "kg", "preco_cotado": 2.0})
        self.assertTrue(self.Oportunidade.search([("product_id", "=", self.cebola.id)]))

    def test_revisar_ligar_aplica_preco(self):
        self._post({"id_fornecedor": "atacadao", "id_produto_interno": "X1", "unidade_medida": "cx", "preco_cotado": 120,
                    "descricao": "Cerveja caixa"})
        item = self.env["boteco.cotacao.revisar"].search([("descricao", "=", "Cerveja caixa")])
        item.write({"product_id": self.cerveja.id, "fator": 12})
        item.action_ligar()
        self.assertTrue(self.Historico.search([("product_id", "=", self.cerveja.id), ("preco_unitario", "=", 10.0)]))

    # ------------------------------------------------------------------ ticket: nome bruto, telefone, condição
    def test_so_nome_bruto_vai_para_revisar_e_aprende_sinonimo(self):
        r = self._post({"id_fornecedor": "atacadao", "produto_nome_bruto": "Alcatra Grill", "unidade_medida": "kg",
                        "preco_cotado": 49.9, "condicao_promocional": "leve 4 pague 3",
                        "link_comprovante": "https://exemplo.com/encarte.jpg"}).json()
        self.assertEqual(r["resultados"][0]["status"], "revisar")
        item = self.env["boteco.cotacao.revisar"].search([("descricao", "=", "Alcatra Grill")])
        self.assertEqual(item.condicao_promocional, "leve 4 pague 3")
        self.assertEqual(item.link_comprovante, "https://exemplo.com/encarte.jpg")
        alcatra = self.env["product.product"].create({
            "name": "Alcatra", "purchase_ok": True, "uom_id": self.env.ref("uom.product_uom_kgm").id,
            "uom_po_id": self.env.ref("uom.product_uom_kgm").id})
        item.product_id = alcatra
        item.action_ligar()
        cotacao = self.Historico.search([("product_id", "=", alcatra.id)])
        self.assertAlmostEqual(cotacao.preco_unitario, 49.9)
        self.assertEqual(cotacao.condicao_promocional, "leve 4 pague 3")
        self.assertEqual(cotacao.link_comprovante, "https://exemplo.com/encarte.jpg")
        # Sinônimo aprendido: da próxima vez (com outra grafia de maiúsculas/acentos) entra sozinho
        r = self._post({"id_fornecedor": "atacadao", "produto_nome_bruto": "ALCATRA  grill", "unidade_medida": "g",
                        "preco_cotado": 0.0459, "link_comprovante": "javascript:alert(1)"}).json()
        self.assertEqual(r["resultados"][0]["status"], "ok")
        self.assertAlmostEqual(r["resultados"][0]["preco_unidade_insumo"], 45.9)
        self.assertFalse(self.Historico.search([("product_id", "=", alcatra.id)], limit=1).link_comprovante)

    def test_nome_parecido_nao_entra_sozinho(self):
        r = self._post({"id_fornecedor": "atacadao", "produto_nome_bruto": "Cebola", "unidade_medida": "kg",
                        "preco_cotado": 3.5}).json()
        self.assertEqual(r["resultados"][0]["status"], "revisar")
        item = self.env["boteco.cotacao.revisar"].search([("descricao", "=", "Cebola")])
        self.assertEqual(item.product_id, self.cebola)  # sugestão marcada: 1 toque

    def test_fornecedor_pelo_telefone_e_flag_desligada(self):
        contato = self.env["res.partner"].create({"name": "Vendedor Perim", "supplier_rank": 1,
                                                  "mobile": "(28) 99999-1234"})
        base = {"id_produto_interno": "CEB", "unidade_medida": "kg", "preco_cotado": 3.9}
        r = self._post(dict(base, telefone_origem="5528999991234")).json()
        self.assertEqual(r["resultados"][0]["status"], "ok")
        r = self._post(dict(base, telefone_origem="+55 28 9999-1234")).json()  # sem o 9 extra
        self.assertEqual(r["resultados"][0]["status"], "ok")
        self.assertEqual(self.env["boteco.cotacoes"]._fornecedor_por_telefone("5527999991234"),
                         self.env["res.partner"])  # outro DDD
        contato.boteco_cotacao_confiavel = False
        r = self._post(dict(base, telefone_origem="5528999991234")).json()
        self.assertEqual(r["resultados"][0]["status"], "recusado")
        self.fornecedor.boteco_cotacao_confiavel = False
        r = self._post(dict(base, id_fornecedor="atacadao")).json()
        self.assertEqual(r["resultados"][0]["status"], "recusado")
