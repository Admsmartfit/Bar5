from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.boteco_base.tests.common import BotecoCase


@tagged("post_install", "-at_install", "boteco")
class TestCapacidadeCongelados(BotecoCase):
    """Etapa 17: capacidade finita, freezer, reserva do bar vs. B2B e fator de correção/cocção."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company = cls.env.company
        cls.cc = cls.env["stock.warehouse"].create({"name": "Cozinha Central (cap)", "code": "CCC",
                                                    "boteco_tipo_unidade": "cozinha_central"})
        kg = cls.env.ref("uom.product_uom_kgm")
        Produto = cls.env["product.product"]
        cls.carne = Produto.create({"name": "Carne moída", "is_storable": True, "uom_id": kg.id, "uom_po_id": kg.id})
        cls.cebola = Produto.create({"name": "Cebola", "is_storable": True, "uom_id": kg.id, "uom_po_id": kg.id})
        cls.kibe = Produto.create({"name": "Kibe congelado", "boteco_produzido_cozinha": True, "uom_id": kg.id,
                                   "uom_po_id": kg.id, "sale_ok": True, "list_price": 50.0})
        cls.receita = cls.env["mrp.bom"].create({
            "product_tmpl_id": cls.kibe.product_tmpl_id.id, "product_qty": 10.0, "product_uom_id": kg.id,
            "type": "normal",
            "bom_line_ids": [fields.Command.create({"product_id": cls.carne.id, "product_qty": 8.0}),
                             fields.Command.create({"product_id": cls.cebola.id, "product_qty": 2.0})],
        })
        Quant = cls.env["stock.quant"].with_context(inventory_mode=True)
        Quant.create({"product_id": cls.carne.id, "location_id": cls.cc.lot_stock_id.id,
                      "inventory_quantity": 100}).action_apply_inventory()
        cls.cliente = cls.env["res.partner"].create({"name": "Bar Revenda"})
        cls.company = company

    def _venda(self, qtd):
        return self.env["sale.order"].create({
            "partner_id": self.cliente.id, "warehouse_id": self.cc.id, "commitment_date": fields.Datetime.now(),
            "order_line": [fields.Command.create({"product_id": self.kibe.id, "product_uom_qty": qtd})],
        })

    def _plano(self):
        plano = self.env["boteco.plano.producao"].create({"warehouse_id": self.cc.id})
        plano.action_calcular()
        return plano, plano.linha_ids.filtered(lambda l: l.product_id == self.kibe)

    def test_capacidade_maxima_do_item(self):
        self._venda(45).action_confirm()
        self.kibe.boteco_lote_max_diario = 25
        _plano, linha = self._plano()
        self.assertEqual(linha.necessidade, 45)
        self.assertEqual(linha.quantidade, 20)  # 2 receitas de 10 kg cabem em 25 kg/dia
        self.assertIn("máximo", linha.limitado_por)

    def test_capacidade_da_cozinha_em_kg(self):
        self._venda(45).action_confirm()
        self.cc.boteco_capacidade_prod_diaria_kg = 30
        _plano, linha = self._plano()
        self.assertEqual(linha.quantidade, 30)

    def test_freezer_cheio_limita(self):
        self._venda(45).action_confirm()
        self.kibe.boteco_volume_freezer_litros = 2.0  # 1 kg ocupa 2 L
        self.cc.boteco_capacidade_freezer_litros = 25.0  # cabem 12,5 kg
        _plano, linha = self._plano()
        self.assertEqual(linha.quantidade, 10)
        self.assertIn("freezer", linha.limitado_por)

    def test_flags_desligadas_nao_limitam(self):
        self.company.write({"boteco_flag_capacidade_finita_congelados": False, "boteco_flag_controle_volume_freezer": False})
        self._venda(45).action_confirm()
        self.kibe.boteco_lote_max_diario = 10
        self.kibe.boteco_volume_freezer_litros = 2.0
        self.cc.boteco_capacidade_freezer_litros = 5.0
        _plano, linha = self._plano()
        self.assertEqual(linha.quantidade, 50)

    def test_insumo_faltando(self):
        self._venda(45).action_confirm()
        plano, linha = self._plano()
        self.assertIn("Cebola", plano.alertas)
        self.assertIn("Cebola", linha.insumos_faltando)
        self.assertNotIn("Carne", plano.alertas)

    def test_reserva_do_bar_bloqueia_b2b(self):
        Quant = self.env["stock.quant"].with_context(inventory_mode=True)
        Quant.create({"product_id": self.kibe.id, "location_id": self.cc.lot_stock_id.id,
                      "inventory_quantity": 20, "lot_id": self.env["stock.lot"].create(
                          {"name": "K1", "product_id": self.kibe.id}).id}).action_apply_inventory()
        self.kibe.boteco_estoque_min_bar = 15
        with self.assertRaises(UserError):
            self._venda(10).action_confirm()
        self._venda(5).action_confirm()  # 20 - 15 = 5 livres para revenda
        # A reserva entra na meta do plano de produção
        _plano, linha = self._plano()
        self.assertEqual(linha.reserva_bar, 15)

    def test_reserva_desligada_libera(self):
        self.company.boteco_flag_reserva_estoque_bar_b2b = False
        self.kibe.boteco_estoque_min_bar = 15
        self._venda(10).action_confirm()

    def test_fator_de_correcao_e_coccao(self):
        linha = self.receita.bom_line_ids.filtered(lambda l: l.product_id == self.cebola)
        linha.write({"boteco_qtd_liquida": 2.0, "boteco_fator_correcao": 1.25})
        self.assertAlmostEqual(linha.product_qty, 2.5)  # sai do estoque o peso bruto
        self.receita.boteco_fator_coccao = 0.8
        # (8 / 1 + 2) x 0,8 = 8 kg prontos
        self.assertAlmostEqual(self.receita.boteco_rendimento_estimado, 8.0)
