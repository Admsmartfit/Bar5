from datetime import date, timedelta

from freezegun import freeze_time

from odoo import fields
from odoo.tests import tagged

from odoo.addons.boteco_base.tests.common import BotecoCase


@tagged("post_install", "-at_install", "boteco")
class TestB2b(BotecoCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company = cls.env.company
        if not company.chart_template:
            cls.env["account.chart.template"].try_loading("generic_coa", company=company, install_demo=False)
        cls.armazem = cls.env["stock.warehouse"].search([("company_id", "=", company.id)], limit=1)
        kg = cls.env.ref("uom.product_uom_kgm")
        cls.bolinho = cls.env["product.product"].create({
            "name": "Bolinho de bacalhau congelado", "boteco_produzido_cozinha": True, "uom_id": kg.id,
            "uom_po_id": kg.id, "categ_id": cls.env.ref("boteco_b2b.categoria_tira_gosto_b2b").id,
            "list_price": 50.0, "invoice_policy": "delivery", "sale_ok": True,
        })
        cls.lote = cls.env["stock.lot"].create({"name": "CC261001-001", "product_id": cls.bolinho.id,
                                                "expiration_date": fields.Datetime.now() + timedelta(days=60)})
        cls.env["stock.quant"].with_context(inventory_mode=True).create({
            "product_id": cls.bolinho.id, "location_id": cls.armazem.lot_stock_id.id, "lot_id": cls.lote.id,
            "inventory_quantity": 100,
        }).action_apply_inventory()
        cls.prazo = cls.env["account.payment.term"].create({
            "name": "14 dias", "line_ids": [fields.Command.create({"value": "percent", "value_amount": 100, "nb_days": 14})]})
        cls.bar_ze = cls.env["res.partner"].create({
            "name": "Bar do Zé", "is_company": True, "boteco_cliente_b2b": True, "vat": "11.444.777/0001-61",
            "boteco_ie": "123456789", "property_product_pricelist": cls.env.ref("boteco_b2b.tabela_b2b_padrao").id,
            "property_payment_term_id": cls.prazo.id,
        })

    def _pedido(self, kg=20):
        pedido = self.env["sale.order"].create({
            "partner_id": self.bar_ze.id, "warehouse_id": self.armazem.id,
            "order_line": [fields.Command.create({"product_id": self.bolinho.id, "product_uom_qty": kg})],
        })
        pedido.action_confirm()
        return pedido

    def test_preco_padrao_42_por_kg(self):
        pedido = self._pedido(20)
        self.assertEqual(pedido.order_line.price_unit, 42.0)
        self.assertEqual(pedido.amount_untaxed, 840.0)
        self.assertEqual(pedido.boteco_kg_total, 20)

    def test_pedido_separado_registra_lote_rastreio_e_fatura(self):
        """Critério: pedido B2B separado registra os lotes enviados e aparece no rastreio do lote."""
        pedido = self._pedido(20)
        entrega = pedido.picking_ids
        entrega.boteco_ler_lote(self.lote.name)
        entrega.boteco_concluir_separacao()
        self.assertEqual(entrega.state, "done")
        self.assertEqual(entrega.move_line_ids.lot_id, self.lote)
        rastreio = self.lote.boteco_rastreio()
        self.assertIn("Bar do Zé", rastreio["clientes"])
        # Conta a receber nasce na entrega, com o prazo do cliente
        fatura = pedido.invoice_ids
        self.assertEqual(fatura.state, "posted")
        self.assertEqual(fatura.boteco_frente, "b2b")
        self.assertEqual(fatura.invoice_date_due, fatura.invoice_date + timedelta(days=14))
        pdf, _t = self.env["ir.actions.report"]._render_qweb_pdf("boteco_b2b.report_romaneio", entrega.ids)
        self.assertTrue(pdf)

    def test_repetir_ultimo_pedido_e_recorrente(self):
        self._pedido(20)
        acao = self.bar_ze.action_boteco_repetir_ultimo_pedido()
        copia = self.env["sale.order"].browse(acao["res_id"])
        self.assertEqual(copia.order_line.product_uom_qty, 20)
        recorrencia = self.env["boteco.b2b.recorrencia"].create({
            "partner_id": self.bar_ze.id, "dia_entrega": "3",
            "linha_ids": [fields.Command.create({"product_id": self.bolinho.id, "quantidade": 15})],
        })
        with freeze_time("2026-10-07"):  # quarta: entrega de quinta é amanhã
            self.env["boteco.b2b.recorrencia"]._cron_gerar_pedidos()
            self.env["boteco.b2b.recorrencia"]._cron_gerar_pedidos()  # não duplica
        pedidos = self.env["sale.order"].search([("boteco_recorrencia_id", "=", recorrencia.id)])
        self.assertEqual(len(pedidos), 1)
        self.assertEqual(pedidos.state, "sale")
        self.assertEqual(pedidos.commitment_date.date(), date(2026, 10, 8))

    def test_contrato_gera_mensalidade_do_mes_seguinte(self):
        """Critério: contrato de assessoria gera a mensalidade do mês seguinte automaticamente."""
        contrato = self.env["boteco.contrato.assessoria"].create({
            "partner_id": self.bar_ze.id, "data_inicio": date(2026, 10, 1), "dia_vencimento": 10})
        contrato.action_ativar()
        implantacao = contrato.fatura_ids
        self.assertEqual(implantacao.amount_total, 3500)
        self.assertEqual(implantacao.boteco_frente, "assessoria")
        with freeze_time("2026-10-20"):
            self.env["boteco.contrato.assessoria"]._cron_gerar_mensalidades()
            self.env["boteco.contrato.assessoria"]._cron_gerar_mensalidades()  # não duplica
        mensalidades = contrato.fatura_ids.filtered("boteco_competencia").sorted("boteco_competencia")
        self.assertEqual(mensalidades.mapped("boteco_competencia"), [date(2026, 10, 1), date(2026, 11, 1)])
        self.assertEqual(mensalidades[-1].amount_total, 450)
        self.assertEqual(mensalidades[-1].invoice_date_due, date(2026, 11, 10))
        self.assertEqual(contrato.proxima_competencia, date(2026, 12, 1))

    def test_cliente_parado_gera_alerta(self):
        pedido = self._pedido(5)
        pedido.date_order = fields.Datetime.now() - timedelta(days=30)
        self.bar_ze.invalidate_recordset()
        self.assertTrue(self.bar_ze.boteco_parado)
        self.env["res.partner"]._cron_alertar_clientes_parados()
        self.assertTrue(self.bar_ze.activity_ids.filtered(lambda a: "parou de comprar" in a.summary))
