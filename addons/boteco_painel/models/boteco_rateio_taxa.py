"""Rateio da taxa de serviço (Etapa 23): quanto vai para cada garçom, para a cozinha/bar e para a casa."""

from odoo import _, fields, models
from odoo.exceptions import UserError

PAGOS = ("paid", "done", "invoiced")


class BotecoRateioTaxa(models.TransientModel):
    _name = "boteco.rateio.taxa"
    _description = "Rateio da taxa de serviço"

    data_inicio = fields.Date("De", default=lambda s: s.env.company.boteco_dia_operacao().replace(day=1), required=True)
    data_fim = fields.Date("Até", default=lambda s: s.env.company.boteco_dia_operacao(), required=True)
    total_taxa = fields.Float("Taxa arrecadada", digits="Product Price", readonly=True)
    linha_ids = fields.One2many("boteco.rateio.taxa.linha", "rateio_id", string="Rateio")

    def action_calcular(self):
        self.ensure_one()
        company = self.env.company
        if not company.boteco_recurso_ativo("financeiro_pix_rateio"):
            raise UserError(_("O rateio da taxa de serviço está desligado na Central de Recursos."))
        pedidos = self.env["pos.order"].sudo().search([
            ("company_id", "=", company.id), ("state", "in", PAGOS),
            ("boteco_dia_operacao", ">=", self.data_inicio), ("boteco_dia_operacao", "<=", self.data_fim),
            ("boteco_taxa_servico", ">", 0),
        ])
        total = sum(pedidos.mapped("boteco_taxa_servico"))
        parte_garcons = total * company.boteco_rateio_garcom_pct / 100.0
        por_garcom = {}
        for pedido in pedidos:
            por_garcom[pedido.user_id] = por_garcom.get(pedido.user_id, 0.0) + pedido.boteco_taxa_servico
        linhas = [fields.Command.clear()]
        for garcom, gerado in sorted(por_garcom.items(), key=lambda kv: -kv[1]):
            linhas.append(fields.Command.create({
                "beneficiario": garcom.name or _("Sem garçom"), "papel": "garcom", "user_id": garcom.id or False,
                "base": gerado, "valor": round(parte_garcons * gerado / total, 2) if total else 0.0,
            }))
        linhas.append(fields.Command.create({
            "beneficiario": _("Equipe da cozinha/bar"), "papel": "producao", "base": total,
            "valor": round(total * company.boteco_rateio_producao_pct / 100.0, 2)}))
        linhas.append(fields.Command.create({
            "beneficiario": _("Casa"), "papel": "casa", "base": total,
            "valor": round(total * company.boteco_rateio_casa_pct / 100.0, 2)}))
        self.write({"total_taxa": total, "linha_ids": linhas})
        return {"type": "ir.actions.act_window", "res_model": self._name, "res_id": self.id, "view_mode": "form",
                "target": "new"}


class BotecoRateioTaxaLinha(models.TransientModel):
    _name = "boteco.rateio.taxa.linha"
    _description = "Parte do rateio da taxa"

    rateio_id = fields.Many2one("boteco.rateio.taxa", required=True, ondelete="cascade")
    beneficiario = fields.Char("Para quem")
    papel = fields.Selection([("garcom", "Garçom"), ("producao", "Cozinha/bar"), ("casa", "Casa")])
    user_id = fields.Many2one("res.users", string="Pessoa")
    base = fields.Float("Taxa gerada", digits="Product Price")
    valor = fields.Float("Recebe", digits="Product Price")
