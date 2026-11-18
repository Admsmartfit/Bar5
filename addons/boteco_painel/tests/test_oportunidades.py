from datetime import timedelta

from odoo import fields
from odoo.tests import tagged

from odoo.addons.boteco_base.tests.common import BotecoCase


@tagged("post_install", "-at_install", "boteco")
class TestOportunidadesCompra(BotecoCase):
    """Etapa 18: card 'Oportunidades de compra' no painel do dono."""

    def test_economia_na_receita_de_congelado(self):
        kg = self.env.ref("uom.product_uom_kgm")
        Produto = self.env["product.product"]
        carne = Produto.create({"name": "Patinho", "is_storable": True, "uom_id": kg.id, "uom_po_id": kg.id})
        kibe = Produto.create({"name": "Kibe congelado", "boteco_produzido_cozinha": True, "uom_id": kg.id, "uom_po_id": kg.id})
        self.env["mrp.bom"].create({
            "product_tmpl_id": kibe.product_tmpl_id.id, "product_qty": 10.0, "product_uom_id": kg.id,
            "bom_line_ids": [fields.Command.create({"product_id": carne.id, "product_qty": 8.0})],
        })
        cozinha = self.env["stock.warehouse"].create({"name": "CC painel", "code": "CCP",
                                                      "boteco_tipo_unidade": "cozinha_central",
                                                      "boteco_capacidade_freezer_litros": 500})
        fornecedor = self.env["res.partner"].create({"name": "Frigorífico"})
        Historico = self.env["boteco.historico.preco"]
        hoje = fields.Date.context_today(Historico)
        Historico.registrar(carne, 40.0, fornecedor=fornecedor, data=hoje - timedelta(days=20))
        Historico.registrar(carne, 34.0, fornecedor=fornecedor)
        oportunidades = self.env["boteco.painel"]._oportunidades_compra(self.env.company)
        self.assertEqual(len(oportunidades), 1)
        item = oportunidades[0]
        self.assertEqual(item["insumo"], "Patinho")
        self.assertAlmostEqual(item["economia_total_receita"], 48.0)  # (40 - 34) x 8 kg
        self.assertEqual(item["freezer_livre_litros"], 500.0)
        self.assertTrue(cozinha)

    def test_radar_desligado_sem_card(self):
        self.env.company.boteco_flag_radar_precos_oportunidade = False
        self.assertEqual(self.env["boteco.painel"]._oportunidades_compra(self.env.company), [])
