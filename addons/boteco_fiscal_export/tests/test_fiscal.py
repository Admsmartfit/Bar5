import base64
import csv
import io
import json
from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.boteco_cardapio.tests.common_pos import BotecoPosCase


@tagged("post_install", "-at_install", "boteco")
class TestFiscal(BotecoPosCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.ref("boteco_cardapio.happy_hour_padrao").active = False
        cls.env.company.vat = "11.222.333/0001-81"
        fiscal = {"boteco_ncm": "2203.00.00", "boteco_cfop": "5405", "boteco_cst_csosn": "500", "boteco_origem": "0"}
        for produto in (cls.chope, cls.refri, cls.porcao, cls.batata):
            produto.product_tmpl_id.write(fiscal)
        for xmlid in ("boteco_pos.produto_taxa_servico", "boteco_pos.produto_couvert"):
            cls.env.ref(xmlid).product_tmpl_id.write({**fiscal, "boteco_ncm": "0000.00.00", "boteco_cfop": "5102"})
        cls.taxa = cls.env.ref("boteco_pos.produto_taxa_servico")
        cls.Registro = cls.env["boteco.fiscal.registro"]

    def _noite(self):
        """Uma noite: 2 contas normais (uma com CPF e taxa), uma cortesia total e um consumo de funcionário."""
        self._sincronizar(self._pedido(
            [self._linha(self.chope, 4), self._linha(self.porcao, 1), self._linha(self.taxa, 1, preco=8.2)],
            mesa=self.mesa1, boteco_cpf_nota="52998224725", pagamentos=[(self.pm_pix, 60), (self.pm_cartao, 30.2)]))
        self._sincronizar(self._pedido([self._linha(self.refri, 2)], mesa=self.mesa2, pagamentos=[(self.pm_dinheiro, 14)]))
        aut = self.env["boteco.autorizacao"].with_user(self.garcom).solicitar("7314", "pode_dar_cortesia")
        self._sincronizar(self._pedido(
            [self._linha(self.chope, 1, discount=100, boteco_cortesia=True, boteco_autorizacao_ref=aut["id"])],
            mesa=self.mesas[2], pagamentos=[]))
        aut = self.env["boteco.autorizacao"].with_user(self.garcom).solicitar("7314", "pode_consumo_funcionario")
        self._sincronizar(self._pedido([self._linha(self.refri, 1, preco=2.5)], mesa=None, boteco_tipo_conta="funcionario",
                                       boteco_funcionario_ref=self.garcom.id, boteco_autorizacao_ref=aut["id"],
                                       pagamentos=[(self.pm_dinheiro, 2.5)]))
        return self.env.company.boteco_dia_operacao(fields.Datetime.now())

    def _exportar(self, dia, formato="csv", reexportar=False):
        assistente = self.env["boteco.fiscal.exportacao"].create(
            {"data_inicio": dia, "data_fim": dia, "formato": formato, "reexportar": reexportar})
        assistente.action_exportar()
        return assistente

    def test_registros_pendentes_e_nao_emitir(self):
        dia = self._noite()
        registros = self.Registro.search([("dia", "=", dia)])
        self.assertEqual(sorted(registros.mapped("estado")), ["nao_emitir", "nao_emitir", "pendente", "pendente"])
        motivos = registros.filtered(lambda r: r.estado == "nao_emitir").mapped("motivo_nao_emitir")
        self.assertIn("Consumo de funcionário", motivos)
        self.assertTrue(any("Cortesia" in m for m in motivos))
        com_cpf = registros.filtered(lambda r: r.cliente_documento)
        self.assertEqual(com_cpf.cliente_documento, "52998224725")

    def test_exportar_e_importar_retorno_zera_a_noite(self):
        """Critério: exportar uma noite e importar o retorno deixa zero pendências dessa noite."""
        dia = self._noite()
        assistente = self._exportar(dia, "csv")
        lote = assistente.lote_id
        self.assertEqual(lote.quantidade, 2)
        texto = base64.b64decode(lote.arquivo).decode("utf-8-sig")
        linhas = list(csv.DictReader(io.StringIO(texto), delimiter=";"))
        self.assertEqual(linhas[0]["NCM"], "22030000")
        self.assertEqual(linhas[0]["CNPJ do emitente"], "11222333000181")
        # Retorno do emissor: referência, número e chave
        saida = io.StringIO()
        escritor = csv.writer(saida, delimiter=";")
        escritor.writerow(["referencia", "numero", "chave"])
        for i, registro in enumerate(lote.registro_ids, start=1):
            escritor.writerow([registro.referencia, str(1000 + i), "3526101122233300018165001000%06d1000000001" % i])
        retorno = self.env["boteco.fiscal.retorno"].create(
            {"arquivo": base64.b64encode(saida.getvalue().encode("utf-8")), "nome_arquivo": "retorno.csv"})
        retorno.action_importar()
        self.assertIn("2 nota(s)", retorno.resultado)
        pendentes = self.Registro.search([("dia", "=", dia), ("estado", "in", ("pendente", "exportado"))])
        self.assertFalse(pendentes)
        self.assertTrue(all(r.chave_nota for r in lote.registro_ids))

    def test_mesmo_registro_nao_sai_em_dois_lotes(self):
        """Critério: o mesmo registro não sai em dois lotes sem ação explícita."""
        dia = self._noite()
        primeiro = self._exportar(dia, "xlsx").lote_id
        with self.assertRaisesRegex(UserError, "Nada para exportar"):
            self._exportar(dia)
        segundo = self._exportar(dia, "json", reexportar=True).lote_id
        self.assertTrue(segundo.reexportacao)
        self.assertEqual(set(primeiro.registro_ids.ids), set(segundo.registro_ids.ids))
        for registro in primeiro.registro_ids:
            self.assertEqual(len(registro.lote_ids), 2)

    def test_soma_dos_itens_bate_com_o_faturamento(self):
        """Critério: a soma dos itens exportados bate com o faturamento do dia."""
        dia = self._noite()
        lote = self._exportar(dia, "json").lote_id
        dados = json.loads(base64.b64decode(lote.arquivo))
        exportado = sum(i["valor_total"] for venda in dados for i in venda["itens"]) + sum(v["taxa_servico"] for v in dados)
        fechamento = self.env["boteco.fechamento.dia"].calcular(dia)
        self.assertAlmostEqual(exportado, fechamento["vendas"], places=2)

    def test_bloqueia_exportacao_sem_ncm(self):
        self.refri.product_tmpl_id.boteco_ncm = False
        dia = self._noite()
        assistente = self.env["boteco.fiscal.exportacao"].create({"data_inicio": dia, "data_fim": dia})
        assistente.action_exportar()
        self.assertIn("Refrigerante lata: falta NCM", assistente.pendencias)
        self.assertFalse(assistente.lote_id)
        self.assertFalse(self.Registro.search([("dia", "=", dia), ("estado", "=", "exportado")]))

    def test_entrega_b2b_gera_nfe_pendente(self):
        """Critério da etapa 7: todo pedido B2B entregue entra como pendente no controle fiscal."""
        cliente = self.env["res.partner"].create({"name": "Bar do Zé", "boteco_cliente_b2b": True, "vat": "11444777000161"})
        produto = self.env["product.product"].create({"name": "Torresmo pré-frito (kg)", "is_storable": True,
                                                      "list_price": 42, "boteco_ncm": "1601.00.00", "boteco_cfop": "5101",
                                                      "boteco_cst_csosn": "101"})
        armazem = self.env["stock.warehouse"].search([("company_id", "=", self.env.company.id)], limit=1)
        self.env["stock.quant"].with_context(inventory_mode=True).create({
            "product_id": produto.id, "location_id": armazem.lot_stock_id.id, "inventory_quantity": 50}).action_apply_inventory()
        venda = self.env["sale.order"].create({"partner_id": cliente.id, "order_line": [
            fields.Command.create({"product_id": produto.id, "product_uom_qty": 10, "price_unit": 42})]})
        venda.action_confirm()
        entrega = venda.picking_ids
        entrega.move_ids.quantity = 10
        entrega.move_ids.picked = True
        entrega.button_validate()
        registro = self.Registro.search([("origem_model", "=", "stock.picking"), ("origem_id", "=", entrega.id)])
        self.assertEqual(registro.tipo, "nfe")
        self.assertEqual(registro.estado, "pendente")
        self.assertAlmostEqual(registro.valor_total, 420)
        dados = registro.dados_exportacao()[0]
        self.assertEqual(dados["cliente_documento"], "11444777000161")
        self.assertEqual(dados["itens"][0]["ncm"], "16010000")

    def test_alerta_de_pendencia_no_painel(self):
        dia = self._noite()
        registros = self.Registro.search([("dia", "=", dia), ("estado", "=", "pendente")])
        registros.write({"data_venda": fields.Datetime.now() - timedelta(days=5)})
        alertas = self.env["boteco.painel"].dados()["alertas"]
        self.assertTrue(any("sem nota" in a for a in alertas))
