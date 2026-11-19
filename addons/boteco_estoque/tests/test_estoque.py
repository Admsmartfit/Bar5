import base64
import os

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tools import file_open

from odoo.addons.boteco_cardapio.tests.common_pos import BotecoPosCase


@tagged("post_install", "-at_install", "boteco")
class TestEstoque(BotecoPosCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.ref("boteco_cardapio.happy_hour_padrao").active = False
        cls.env.company.point_of_sale_update_stock_quantities = "real"
        cls.armazem = cls.env["stock.warehouse"].search([("company_id", "=", cls.env.company.id)], limit=1)
        cls.estoque = cls.armazem.lot_stock_id
        categoria = cls.env["product.category"].create({"name": "Insumos (teste)", "property_cost_method": "average"})
        Produto = cls.env["product.product"]
        cls.bolinho_cru = Produto.create({"name": "Bolinho congelado (un)", "is_storable": True, "categ_id": categoria.id,
                                          "standard_price": 1.0, "available_in_pos": False})
        cls.molho = Produto.create({"name": "Molho (kg)", "is_storable": True, "categ_id": categoria.id,
                                    "uom_id": cls.env.ref("uom.product_uom_kgm").id,
                                    "uom_po_id": cls.env.ref("uom.product_uom_kgm").id,
                                    "standard_price": 20.0, "available_in_pos": False})
        # Ficha técnica (kit): porção = 12 bolinhos + 30 g de molho
        cls.env["mrp.bom"].create({
            "product_tmpl_id": cls.porcao.product_tmpl_id.id, "type": "phantom", "product_qty": 1,
            "bom_line_ids": [
                fields.Command.create({"product_id": cls.bolinho_cru.id, "product_qty": 12}),
                fields.Command.create({"product_id": cls.molho.id, "product_qty": 0.03,
                                       "product_uom_id": cls.env.ref("uom.product_uom_kgm").id}),
            ],
        })
        Quant = cls.env["stock.quant"].with_context(inventory_mode=True)
        for produto, qtd in ((cls.bolinho_cru, 500), (cls.molho, 10)):
            Quant.create({"product_id": produto.id, "location_id": cls.estoque.id, "inventory_quantity": qtd}).action_apply_inventory()

    def _vender(self, produto, qtd, preco=None):
        preco = produto.lst_price if preco is None else preco
        return self._sincronizar(self._pedido([self._linha(produto, qtd, preco=preco)], mesa=self.mesa1,
                                              pagamentos=[(self.pm_pix, preco * qtd)]))

    def test_vender_10_porcoes_baixa_exatamente_a_ficha_tecnica(self):
        """Critério de aceite: vender 10 porções baixa exatamente os insumos da ficha técnica."""
        antes_bolinho = self.bolinho_cru.with_context(location=self.estoque.id).qty_available
        antes_molho = self.molho.with_context(location=self.estoque.id).qty_available
        pedido = self._vender(self.porcao, 10)
        self.assertEqual(pedido.state, "paid")
        self.bolinho_cru.invalidate_recordset()
        self.molho.invalidate_recordset()
        self.assertAlmostEqual(antes_bolinho - self.bolinho_cru.with_context(location=self.estoque.id).qty_available, 120)
        self.assertAlmostEqual(antes_molho - self.molho.with_context(location=self.estoque.id).qty_available, 0.3, places=3)

    def test_cmv_da_noite_bate_com_os_custos(self):
        """Critério de aceite: CMV da noite bate com a soma dos custos dos itens vendidos."""
        pedido_kit = self._vender(self.porcao, 2)
        self.assertAlmostEqual(pedido_kit.lines.total_cost, 2 * (12 * 1.0 + 0.03 * 20.0))
        self._vender(self.porcao, 1)
        dia = pedido_kit.boteco_dia_operacao
        linhas = self.env["boteco.cmv"].search([("dia", "=", dia), ("tipo", "=", "venda"), ("product_id", "=", self.porcao.id)])
        pedidos = self.env["pos.order"].search([("boteco_dia_operacao", "=", dia), ("state", "=", "paid")])
        soma_itens = sum(pedidos.lines.filtered(lambda l: l.product_id == self.porcao).mapped("total_cost"))
        self.assertAlmostEqual(sum(linhas.mapped("custo")), soma_itens)
        self.assertAlmostEqual(sum(linhas.mapped("custo")), 3 * 12.6)
        resumo = self.env["boteco.cmv"].resumo_dia(dia)
        self.assertGreater(resumo["cmv_pct"], 0)

    def test_importar_xml_da_nota_cria_entrada_sem_digitacao(self):
        """Critério de aceite: importar um XML de nota de fornecedor cria a entrada sem digitação."""
        caminho = os.path.join(os.path.dirname(__file__), "dados", "nfe_fornecedor.xml")
        with file_open(caminho, "rb") as arq:
            conteudo = arq.read()
        assistente = self.env["boteco.nfe.importacao"].create({"arquivo": base64.b64encode(conteudo)})
        assistente.action_ler()
        self.assertEqual(assistente.numero, "12345")
        self.assertEqual(len(assistente.linha_ids), 2)
        # O fornecedor manda caixa com 24: ensina o fator uma vez (depois fica salvo no de-para)
        assistente.linha_ids.filtered(lambda l: l.codigo == "CERV-LN-355").fator = 24
        assistente.action_criar_entrada()
        compra = assistente.purchase_id
        self.assertEqual(compra.state, "purchase")
        self.assertTrue(all(p.state == "done" for p in compra.picking_ids))
        long_neck = compra.order_line.filtered(lambda l: "LONG NECK" in l.name).product_id
        self.assertEqual(long_neck.barcode, "7891149108718")
        self.assertAlmostEqual(long_neck.qty_available, 48)
        self.assertAlmostEqual(long_neck.standard_price, 4.0)  # 192 / 48
        limao = compra.order_line.filtered(lambda l: "LIMAO" in l.name)
        self.assertAlmostEqual(limao.price_subtotal, 30.0)  # com desconto
        # A mesma nota não entra duas vezes
        outra = self.env["boteco.nfe.importacao"].create({"arquivo": base64.b64encode(conteudo)})
        with self.assertRaisesRegex(UserError, "já foi importada"):
            outra.action_ler()
        # Próxima nota do mesmo fornecedor reconhece o produto e o fator sozinha
        de_para = self.env["boteco.nfe.produto"].search([("codigo", "=", "CERV-LN-355")])
        self.assertEqual(de_para.fator, 24)

    def test_fator_suspeito_na_nota_precisa_de_conferencia(self):
        """Auditoria (risco 2): fator errado multiplica o custo; a entrada só passa conferida."""
        caminho = os.path.join(os.path.dirname(__file__), "dados", "nfe_fornecedor.xml")
        with file_open(caminho, "rb") as arq:
            conteudo = arq.read()
        assistente = self.env["boteco.nfe.importacao"].create({"arquivo": base64.b64encode(conteudo)})
        assistente.action_ler()
        linha = assistente.linha_ids.filtered(lambda l: l.codigo == "CERV-LN-355")
        self.refri.standard_price = 4.0  # o insumo já cadastrado custava R$ 4 a unidade
        linha.product_id = self.refri
        linha.fator = 2  # errou: é caixa com 24
        self.assertTrue(linha.alerta_fator)
        self.assertAlmostEqual(linha.custo_unitario, 48.0)
        self.assertTrue(assistente.tem_alerta_fator)
        with self.assertRaisesRegex(UserError, "Conferi os fatores"):
            assistente.action_criar_entrada()
        linha.fator = 24
        self.assertFalse(linha.alerta_fator)

    def test_precisao_custo_4_casas_venda_2(self):
        """Custo da dose não pode arredondar para 2 casas; preço de venda continua com 2."""
        Precisao = self.env["decimal.precision"]
        self.assertEqual(Precisao.precision_get("Product Price"), 4)
        self.assertEqual(Precisao.precision_get("Product Unit of Measure"), 3)
        self.molho.standard_price = 100 / 240  # caixa de 12 L em doses de 50 ml
        self.assertAlmostEqual(self.molho.standard_price, 0.4167, places=4)
        self.assertEqual(self.env["product.template"]._fields["list_price"].get_digits(self.env), (16, 2))

    def test_lista_de_compras_por_whatsapp(self):
        fornecedor = self.env["res.partner"].create({"name": "Hortifruti do Zé", "mobile": "(11) 98888-7777"})
        self.molho.seller_ids = [fields.Command.create({"partner_id": fornecedor.id, "product_code": "MOL-1"})]
        self.env["stock.warehouse.orderpoint"].create({
            "product_id": self.molho.id, "location_id": self.estoque.id, "product_min_qty": 50, "product_max_qty": 60,
        })
        lista = self.env["boteco.lista.compras"].create({})
        lista.action_gerar()
        linha = lista.linha_ids.filtered(lambda l: l.partner_id == fornecedor)
        self.assertTrue(linha.link_whatsapp.startswith("https://wa.me/5511988887777?text="))
        self.assertIn("Molho", linha.itens)

    def test_contagem_pelo_celular_com_aprovacao_do_gerente(self):
        contagem = self.env["boteco.contagem"].create({"location_id": self.estoque.id})
        contagem.action_carregar_produtos()
        linha = contagem.linha_ids.filtered(lambda l: l.product_id == self.bolinho_cru)
        self.assertEqual(linha.quantidade_sistema, 500)
        contagem.boteco_salvar({str(linha.id): 480})
        self.assertEqual(linha.diferenca, -20)
        with self.assertRaises(UserError):
            contagem.with_user(self.garcom).action_aprovar()
        contagem.with_user(self.gerente).action_aprovar()
        self.assertEqual(contagem.estado, "aprovado")
        self.bolinho_cru.invalidate_recordset()
        self.assertEqual(self.bolinho_cru.with_context(location=self.estoque.id).qty_available, 480)
        self.assertTrue(self.env["boteco.auditoria"].search([("acao", "=", "ajuste_estoque"), ("res_id", "=", contagem.id)]))

    def test_perda_no_cmv_segue_a_virada_do_dia_da_empresa(self):
        """Auditoria: o CMV das perdas usava fuso e virada (6h) fixos; agora segue a empresa."""
        for virada in (0.0, 23.5):
            self.env.company.boteco_hora_virada = virada
            scrap = self.env["stock.scrap"].create({
                "product_id": self.molho.id, "scrap_qty": 0.5, "location_id": self.estoque.id,
                "scrap_reason_tag_ids": [fields.Command.link(self.env.ref("boteco_estoque.motivo_perda_vencido").id)]})
            scrap.do_scrap()
            linha = self.env["boteco.cmv"].search([("id", "=", scrap.id * 2 + 1)])
            self.assertEqual(linha.dia, self.env.company.boteco_dia_operacao(scrap.date_done))

    def test_perda_exige_motivo_e_entra_no_cmv(self):
        scrap = self.env["stock.scrap"].create({"product_id": self.molho.id, "scrap_qty": 1.5, "location_id": self.estoque.id})
        with self.assertRaisesRegex(UserError, "motivo"):
            scrap.do_scrap()
        scrap.scrap_reason_tag_ids = self.env.ref("boteco_estoque.motivo_perda_vencido")
        scrap.do_scrap()
        self.assertEqual(scrap.state, "done")
        registro = self.env["boteco.auditoria"].search([("acao", "=", "perda"), ("res_id", "=", scrap.id)])
        self.assertEqual(registro.motivo, "Vencido")
        perdas = self.env["boteco.cmv"].search([("tipo", "=", "perda"), ("product_id", "=", self.molho.id)])
        self.assertAlmostEqual(sum(perdas.mapped("custo")), 30.0)
        garcom_scrap = self.env["stock.scrap"].create({"product_id": self.molho.id, "scrap_qty": 1, "location_id": self.estoque.id,
                                                       "scrap_reason_tag_ids": [fields.Command.link(self.env.ref("boteco_estoque.motivo_perda_quebra").id)]})
        with self.assertRaises(UserError):
            garcom_scrap.with_user(self.garcom).do_scrap()
