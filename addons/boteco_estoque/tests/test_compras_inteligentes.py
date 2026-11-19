import base64
import io
from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import BaseCase, tagged

from odoo.addons.boteco_base.tests.common import BotecoCase
from odoo.addons.boteco_estoque.tools import orcamento


@tagged("post_install", "-at_install", "boteco")
class TestParserOrcamento(BaseCase):
    def test_linhas_de_whatsapp(self):
        itens = orcamento.ler_texto(
            "Bom dia! Ofertas de hoje:\n"
            "Cebola nacional kg ....... R$ 3,99\n"
            "Batata lavada - 4,50/kg\n"
            "Caixa de tomate 20kg R$ 89,90\n"
            "Pedido mínimo R$ 300,00\n"
            "12/11\n"
        )
        descricoes = {i["descricao"]: i for i in itens}
        self.assertAlmostEqual(descricoes["Cebola nacional"]["preco"], 3.99)
        self.assertEqual(descricoes["Cebola nacional"]["unidade"], "kg")
        self.assertAlmostEqual(descricoes["Batata lavada"]["preco"], 4.50)
        self.assertEqual(descricoes["Batata lavada"]["unidade"], "kg")
        self.assertAlmostEqual(descricoes["Caixa de tomate 20kg"]["preco"], 89.90)
        self.assertNotIn("12/11", descricoes)

    def test_milhar(self):
        self.assertAlmostEqual(orcamento.ler_texto("Filé mignon peça 1.234,56")[0]["preco"], 1234.56)



@tagged("post_install", "-at_install", "boteco")
class TestRadarPrecos(BotecoCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        kg = cls.env.ref("uom.product_uom_kgm")
        cls.cebola = cls.env["product.product"].create({"name": "Cebola", "is_storable": True, "purchase_ok": True,
                                                        "uom_id": kg.id, "uom_po_id": kg.id})
        Parceiro = cls.env["res.partner"]
        cls.ceasa = Parceiro.create({"name": "Ceasa do Zé", "supplier_rank": 1})
        cls.atacado = Parceiro.create({"name": "Atacadão", "supplier_rank": 1})
        cls.Historico = cls.env["boteco.historico.preco"]
        hoje = fields.Date.context_today(cls.Historico)
        for dias, preco in ((50, 5.0), (30, 5.2), (10, 4.8)):
            cls.Historico.registrar(cls.cebola, preco, fornecedor=cls.ceasa, origem="nfe", data=hoje - timedelta(days=dias))

    def test_queda_de_10_por_cento_e_interessante(self):
        cotacao = self.Historico.registrar(self.cebola, 4.2, fornecedor=self.atacado, origem="manual")
        self.assertAlmostEqual(cotacao.media_60d, 5.0)
        self.assertAlmostEqual(cotacao.minimo_90d, 4.8)
        self.assertTrue(cotacao.preco_interessante)
        self.assertIn(cotacao, self.Historico.oportunidades())

    def test_queda_pequena_nao_e(self):
        self.assertFalse(self.Historico.registrar(self.cebola, 4.7, fornecedor=self.atacado).preco_interessante)

    def test_radar_desligado_nao_registra(self):
        self.env.company.boteco_flag_radar_precos_oportunidade = False
        self.assertFalse(self.Historico.registrar(self.cebola, 1.0, fornecedor=self.atacado))

    def test_lista_de_compras_escolhe_o_mais_barato(self):
        self.env["product.supplierinfo"].create({"partner_id": self.ceasa.id, "product_tmpl_id": self.cebola.product_tmpl_id.id})
        armazem = self.env["stock.warehouse"].search([("company_id", "=", self.env.company.id)], limit=1)
        self.env["stock.warehouse.orderpoint"].create({"product_id": self.cebola.id, "location_id": armazem.lot_stock_id.id,
                                                       "product_min_qty": 10, "product_max_qty": 20})
        self.Historico.registrar(self.cebola, 3.9, fornecedor=self.atacado)
        lista = self.env["boteco.lista.compras"].create({})
        lista.action_gerar()
        self.assertEqual(lista.linha_ids.partner_id, self.atacado)

    def test_ler_orcamento_colado(self):
        assistente = self.env["boteco.importar.orcamento"].create({
            "partner_id": self.atacado.id, "texto": "Cebola branca kg 3,50\nProduto que não existe 10,00"})
        assistente.action_ler()
        linha = assistente.linha_ids.filtered(lambda l: l.product_id == self.cebola)
        self.assertAlmostEqual(linha.preco, 3.5)
        self.assertEqual(len(assistente.linha_ids), 2)
        assistente.action_registrar()
        cotacao = self.Historico.search([("partner_id", "=", self.atacado.id), ("product_id", "=", self.cebola.id)])
        self.assertEqual(cotacao.origem, "orcamento_texto")
        self.assertTrue(cotacao.preco_interessante)
        # Aprendeu o de-para: na próxima vem ligado direto
        self.assertTrue(self.env["boteco.nfe.produto"].search([("partner_id", "=", self.atacado.id),
                                                              ("product_id", "=", self.cebola.id)]))

    def test_ler_orcamento_pdf(self):
        from reportlab.pdfgen import canvas

        buffer = io.BytesIO()
        pdf = canvas.Canvas(buffer)
        pdf.drawString(72, 750, "Tabela de precos Atacadao")
        pdf.drawString(72, 730, "Cebola kg R$ 3,70")
        pdf.save()
        assistente = self.env["boteco.importar.orcamento"].create({
            "partner_id": self.atacado.id, "arquivo": base64.b64encode(buffer.getvalue()), "nome_arquivo": "tabela.pdf"})
        assistente.action_ler()
        self.assertEqual(assistente.origem, "orcamento_pdf")
        self.assertEqual(assistente.linha_ids.product_id, self.cebola)
        self.assertAlmostEqual(assistente.linha_ids.preco, 3.7)


    def test_leitor_desligado(self):
        self.env.company.boteco_flag_leitor_orcamento_pdf_imagem = False
        assistente = self.env["boteco.importar.orcamento"].create({"partner_id": self.atacado.id, "texto": "Cebola 3,00"})
        with self.assertRaises(UserError):
            assistente.action_ler()



