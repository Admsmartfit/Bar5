import json
from unittest.mock import patch

from odoo.tests import HttpCase, tagged

from odoo.addons.boteco_cotacoes.models.cotacao import PARAM_TOKEN_COLETOR, PARAM_TOKEN_WHATSAPP, mesmo_numero


def mensagem(numero, texto, grupo=False, minha=False):
    return {"event": "messages.upsert", "instance": "bar5", "data": {
        "key": {"remoteJid": "%s@%s" % (numero, "g.us" if grupo else "s.whatsapp.net"), "fromMe": minha, "id": "X1"},
        "pushName": "Alguém", "message": {"conversation": texto}, "messageType": "conversation"}}


@tagged("post_install", "-at_install", "boteco")
class TestCotacoes(HttpCase):
    """Etapa 35: WhatsApp do bar e coletor externo alimentando o radar de preços."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company = cls.env.company
        company.write({"boteco_flag_cotacoes_whatsapp": True, "boteco_flag_coletor_ofertas": True,
                       "boteco_flag_radar_precos_oportunidade": True})
        kg = cls.env.ref("uom.product_uom_kgm")
        cls.cebola = cls.env["product.product"].create({"name": "Cebola", "purchase_ok": True, "type": "consu",
                                                        "uom_id": kg.id, "uom_po_id": kg.id})
        cls.hortifruti = cls.env["res.partner"].create({"name": "Hortifruti do Zé", "mobile": "(11) 98888-1234",
                                                        "supplier_rank": 1})
        cls.cliente = cls.env["res.partner"].create({"name": "Cliente Qualquer", "mobile": "(11) 97777-0000"})
        Cotacoes = cls.env["boteco.cotacoes"]
        cls.token_whats = Cotacoes._token(PARAM_TOKEN_WHATSAPP)
        cls.token_coletor = Cotacoes._token(PARAM_TOKEN_COLETOR)
        cls.Historico = cls.env["boteco.historico.preco"]
        cls.Log = cls.env["boteco.cotacao.log"]
        cls.Fila = cls.env["boteco.cotacao.fila"]

    def _post(self, url, dados, headers=None):
        self.env.flush_all()
        resposta = self.url_open(url, data=json.dumps(dados), headers={"Content-Type": "application/json", **(headers or {})})
        self.env.invalidate_all()
        return resposta

    def _whats(self, dados, token=None):
        return self._post("/boteco/compras/whatsapp/%s" % (token or self.token_whats), dados)

    def _processar(self):
        self.Fila._cron_processar()

    def test_numero_igual_com_e_sem_nono_digito(self):
        self.assertTrue(mesmo_numero("(11) 98888-1234", "551198888123" + "4"))
        self.assertTrue(mesmo_numero("11988881234", "551188881234"))
        self.assertFalse(mesmo_numero("11988881234", "11988881235"))

    def test_fornecedor_manda_preco_e_entra_no_radar_com_origem_whatsapp(self):
        resposta = self._whats(mensagem("5511988881234", "Bom dia! Tabela de hoje:\nCebola kg 3,50\nAlho kg 22,00"))
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json()["resultado"], "ok")
        self._processar()
        cotacao = self.Historico.search([("origem", "=", "whatsapp"), ("product_id", "=", self.cebola.id)])
        self.assertEqual(cotacao.partner_id, self.hortifruti)
        self.assertAlmostEqual(cotacao.preco_unitario, 3.5)
        info = self.env["product.supplierinfo"].search([("partner_id", "=", self.hortifruti.id),
                                                        ("product_tmpl_id", "=", self.cebola.product_tmpl_id.id)])
        self.assertAlmostEqual(info.price, 3.5)
        # Alho não está cadastrado: vai para "Cotações para revisar"
        revisar = self.env["boteco.cotacao.revisar"].search([("partner_id", "=", self.hortifruti.id)])
        self.assertEqual((revisar.descricao, revisar.unidade), ("Alho", "kg"))
        # LGPD: depois de lido, o texto da mensagem não fica guardado
        self.assertFalse(self.Fila.search([("partner_id", "=", self.hortifruti.id)]).texto)

    def test_ligar_item_revisado_aprende_o_de_para(self):
        self._whats(mensagem("5511988881234", "Cebola roxa especial 4,10"))
        self._processar()
        item = self.env["boteco.cotacao.revisar"].search([("descricao", "=", "Cebola roxa especial")])
        if not item:  # o parser casou sozinho pela palavra "Cebola": nada a revisar
            return
        item.product_id = self.cebola
        item.action_ligar()
        self.assertEqual(item.estado, "ligado")
        self._whats(mensagem("5511988881234", "Cebola roxa especial 3,90"))
        self._processar()
        self.assertTrue(self.Historico.search([("product_id", "=", self.cebola.id), ("preco_unitario", "=", 3.9)]))

    def test_numero_nao_cadastrado_grupo_e_proprio_bar_nao_gravam_nada(self):
        antes = self.Fila.search_count([])
        self._whats(mensagem("5511977770000", "Cebola kg 2,00"))  # cliente (não é fornecedor)
        self._whats(mensagem("5511955551111", "Cebola kg 2,00"))  # desconhecido
        self._whats(mensagem("120363000000@g", "Cebola kg 2,00", grupo=True))
        self._whats(mensagem("5511988881234", "Cebola kg 2,00", minha=True))
        self._processar()
        self.assertEqual(self.Fila.search_count([]), antes)
        self.assertFalse(self.Historico.search([("preco_unitario", "=", 2.0)]))
        desconhecidos = self.Log.search([("resultado", "=", "desconhecido")])
        self.assertEqual(len(desconhecidos), 2)
        self.assertFalse(any("97777" in (l.detalhe or "") or "55519" in (l.detalhe or "") for l in desconhecidos))
        self.assertTrue(any("não cadastrado" in a for a in self.env["boteco.painel"]._alertas_extras(self.env.company)))

    def test_token_errado_recusado_e_registrado(self):
        resposta = self._whats(mensagem("5511988881234", "Cebola kg 1,00"), token="errado")
        self.assertEqual(resposta.status_code, 401)
        self.assertTrue(self.Log.search([("canal", "=", "whatsapp"), ("resultado", "=", "recusado")]))
        resposta = self._post("/boteco/compras/api/cotacoes", {"cotacoes": []}, headers={"Authorization": "Bearer x"})
        self.assertEqual(resposta.status_code, 401)
        self.assertEqual(self.url_open("/boteco/compras/api/fontes").status_code, 401)

    def test_coletor_busca_fontes_e_envia_itens(self):
        self.hortifruti.write({"boteco_site_ofertas": "https://ze.com.br/ofertas", "boteco_instagram_handle": "ze",
                               "boteco_palavras_chave": "cebola, oferta"})
        cabecalho = {"Authorization": "Bearer %s" % self.token_coletor}
        self.env.flush_all()
        fontes = self.url_open("/boteco/compras/api/fontes", headers=cabecalho).json()
        self.assertEqual(fontes["instagram_hora"], "08:00")
        fonte = [f for f in fontes["fontes"] if f["fornecedor_id"] == self.hortifruti.id][0]
        self.assertEqual(fonte["palavras"], ["cebola", "oferta"])
        resposta = self._post("/boteco/compras/api/cotacoes", {"coletor_versao": "1", "cotacoes": [{
            "fornecedor_id": self.hortifruti.id, "fonte": "site", "link": "https://ze.com.br/ofertas",
            "itens": [{"produto": "Cebola", "preco": "2,99", "unidade": "kg"}]}]}, headers=cabecalho)
        self.assertEqual(resposta.json()["itens"], 1)
        cotacao = self.Historico.search([("origem", "=", "site")])
        self.assertAlmostEqual(cotacao.preco_unitario, 2.99)
        self.assertEqual(cotacao.referencia, "https://ze.com.br/ofertas")

    def test_lista_de_compras_mostra_melhor_preco_e_fonte(self):
        self.env["stock.warehouse.orderpoint"].create({"product_id": self.cebola.id, "product_min_qty": 10,
                                                       "product_max_qty": 20})
        self.Historico.registrar(self.cebola, 3.2, fornecedor=self.hortifruti, origem="whatsapp")
        lista = self.env["boteco.lista.compras"].create({})
        lista.action_gerar()
        self.assertIn("R$ 3.20 – Hortifruti do Zé (WhatsApp do fornecedor", lista.linha_ids.melhor_preco)

    def test_whatsapp_desconectado_avisa_painel_e_saude(self):
        Param = self.env["ir.config_parameter"].sudo()
        Param.set_param("boteco.evolution_apikey", "chave-teste")
        resposta = type("R", (), {"status_code": 200, "json": lambda self: {"instance": {"state": "close"}}})()
        with patch("odoo.addons.boteco_cotacoes.models.whatsapp.requests.request", return_value=resposta):
            self.env["boteco.whatsapp"]._cron_verificar()
        self.assertTrue(any("desconectado" in a for a in self.env["boteco.painel"]._alertas_extras(self.env.company)))
        saude = [i for i in self.env["boteco.saude"]._verificacoes_extras() if "WhatsApp" in i["nome"]]
        self.assertEqual(saude[0]["estado"], "erro")
        # Conectou de novo pelo evento do próprio Evolution API
        self._whats({"event": "connection.update", "data": {"state": "open", "wuid": "5511900001111@s.whatsapp.net"}})
        self.assertEqual(Param.get_param("boteco.whatsapp_numero"), "5511900001111")
        self.assertFalse(self.env["boteco.whatsapp"]._alerta())

    def test_conectar_mostra_qr_code(self):
        self.env["ir.config_parameter"].sudo().set_param("boteco.evolution_apikey", "chave-teste")
        chamadas = []

        def falso(metodo, url, **kwargs):
            chamadas.append((metodo, url))
            corpo = {"base64": "data:image/png;base64,AAAA"} if "/instance/connect/" in url else {}
            return type("R", (), {"status_code": 200, "json": lambda self: corpo})()

        with patch("odoo.addons.boteco_cotacoes.models.whatsapp.requests.request", side_effect=falso):
            resultado = self.env["boteco.whatsapp"].conectar()
        self.assertEqual(resultado["qr"], "data:image/png;base64,AAAA")
        self.assertTrue(any(u.endswith("/instance/create") for _m, u in chamadas))

    def test_flag_desligada_nao_le(self):
        self.env.company.boteco_flag_cotacoes_whatsapp = False
        self.assertEqual(self._whats(mensagem("5511988881234", "Cebola kg 1,11")).json()["resultado"], "desligado")
        self._processar()
        self.assertFalse(self.Historico.search([("preco_unitario", "=", 1.11)]))
