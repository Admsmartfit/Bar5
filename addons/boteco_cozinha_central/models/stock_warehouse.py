from odoo import api, fields, models


class StockWarehouse(models.Model):
    _inherit = "stock.warehouse"

    boteco_impressora_etiqueta_id = fields.Many2one(
        "boteco.impressora", string="Impressora de etiquetas",
        domain="[('linguagem', 'in', ('zpl', 'tspl'))]",
        help="Etiqueta do saco a vácuo sai aqui quando a produção é finalizada.",
    )
    # Etapa 17: capacidade finita da cozinha e da câmara fria
    boteco_capacidade_prod_diaria_kg = fields.Float(
        "Capacidade de produção por dia (kg)", help="Total que a equipe/equipamentos produzem num dia. 0 = sem limite.")
    boteco_capacidade_freezer_litros = fields.Float(
        "Capacidade dos freezers (L)", help="Volume útil somado dos freezers/câmara fria a -18 °C. 0 = não controla.")
    boteco_freezer_ocupado_litros = fields.Float(
        "Freezer ocupado (L)", compute="_compute_boteco_freezer", digits=(16, 1))
    boteco_freezer_livre_litros = fields.Float(
        "Freezer livre (L)", compute="_compute_boteco_freezer", digits=(16, 1))

    def _boteco_ocupacao_freezer(self):
        """Litros ocupados: estoque de cada produto congelado x volume por unidade."""
        self.ensure_one()
        produtos = self.env["product.product"].sudo().search([("boteco_volume_freezer_litros", ">", 0)])
        if not produtos:
            return 0.0
        produtos = produtos.with_context(warehouse_id=self.id)
        return sum(max(p.qty_available, 0.0) * p.boteco_volume_freezer_litros for p in produtos)

    @api.depends("boteco_capacidade_freezer_litros")
    def _compute_boteco_freezer(self):
        for armazem in self:
            ocupado = armazem._boteco_ocupacao_freezer() if armazem.id else 0.0
            armazem.boteco_freezer_ocupado_litros = ocupado
            armazem.boteco_freezer_livre_litros = (
                max(armazem.boteco_capacidade_freezer_litros - ocupado, 0.0) if armazem.boteco_capacidade_freezer_litros else 0.0
            )
