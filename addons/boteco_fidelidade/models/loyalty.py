"""Fidelidade do boteco sobre o loyalty gratuito do Odoo (Etapa 31)."""

import re

from odoo import _, api, fields, models

CHOPE_RE = re.compile(r"(?i)\bchop+e?")
ICP_MODELOS = "boteco.fidelidade_modelos_criados"


class LoyaltyProgram(models.Model):
    _inherit = "loyalty.program"

    boteco_auto_resgate = fields.Boolean(
        "Resgatar sozinho no PDV",
        help="Quando o cliente da conta completa os pontos, o prêmio entra sozinho (ex.: o 10º chope sai grátis).",
    )
    boteco_modelo = fields.Char("Modelo do boteco", copy=False, readonly=True)

    @api.model
    def _load_pos_data_domain(self, data):
        # Central de Recursos: fidelidade desligada = o PDV não oferece nenhum programa
        config = self.env["pos.config"].browse(data["pos.config"]["data"][0]["id"])
        if not config.company_id.boteco_recurso_ativo("fidelidade"):
            return [("id", "=", False)]
        return super()._load_pos_data_domain(data)

    @api.model
    def _load_pos_data_fields(self, config_id):
        return super()._load_pos_data_fields(config_id) + ["boteco_auto_resgate"]

    # ------------------------------------------------------------------ modelos
    @api.model
    def _boteco_chopes(self):
        produtos = self.env["product.product"].search([("available_in_pos", "=", True), ("sale_ok", "=", True)])
        chopes = produtos.filtered(lambda p: CHOPE_RE.search(p.name or ""))
        return chopes.sorted(lambda p: (p.lst_price, p.id))

    @api.model
    def _boteco_criar_modelos(self):
        """Cria (uma vez cada) os programas modelo, todos desligados: o dono liga o que quiser."""
        existentes = set(self.with_context(active_test=False).search([("boteco_modelo", "!=", False)]).mapped("boteco_modelo"))
        criados = self.browse()
        if "cartao_chope" not in existentes:
            chopes = self._boteco_chopes()
            if chopes:
                criados |= self.create({
                    "name": _("Cartão fidelidade: 10 chopes = 1 grátis"),
                    "boteco_modelo": "cartao_chope", "active": False, "boteco_auto_resgate": True,
                    "program_type": "loyalty", "applies_on": "both", "trigger": "auto",
                    "portal_visible": True, "portal_point_name": _("chopes"),
                    "rule_ids": [fields.Command.create({
                        "reward_point_mode": "unit", "reward_point_amount": 1, "minimum_qty": 0,
                        "product_ids": [fields.Command.set(chopes.ids)],
                    })],
                    # O chope grátis não soma ponto: 9 pontos = 9 pagos e o 10º sai de graça
                    "reward_ids": [fields.Command.create({
                        "reward_type": "product", "reward_product_id": chopes[0].id, "reward_product_qty": 1,
                        "required_points": 9,
                    })],
                })
        if "cashback" not in existentes:
            criados |= self.create({
                "name": _("Cashback de 5% para usar na próxima visita"),
                "boteco_modelo": "cashback", "active": False, "boteco_auto_resgate": False,
                "program_type": "loyalty", "applies_on": "both", "trigger": "auto",
                "portal_visible": True, "portal_point_name": _("R$ de cashback"),
                "rule_ids": [fields.Command.create({
                    "reward_point_mode": "money", "reward_point_amount": 0.05, "minimum_qty": 0,
                })],
                "reward_ids": [fields.Command.create({
                    "reward_type": "discount", "discount_mode": "per_point", "discount": 1,
                    "discount_applicability": "order", "required_points": 1,
                })],
            })
        if "aniversario" not in existentes:
            criados |= self.create({
                "name": _("Cupom de aniversário (10%)"),
                "boteco_modelo": "aniversario", "active": False,
                "program_type": "coupons", "applies_on": "current", "trigger": "with_code",
                "rule_ids": [fields.Command.create({"reward_point_mode": "order", "reward_point_amount": 1,
                                                    "minimum_qty": 0})],
                "reward_ids": [fields.Command.create({
                    "reward_type": "discount", "discount_mode": "percent", "discount": 10,
                    "discount_applicability": "order", "required_points": 1,
                })],
            })
        return criados

    @api.model
    def _boteco_programas_pos(self, company):
        if not company.boteco_recurso_ativo("fidelidade"):
            return self.browse()
        return self.search([("pos_ok", "=", True), ("program_type", "=", "loyalty"),
                            "|", ("company_id", "=", False), ("company_id", "=", company.id)])

    @api.model
    def _boteco_saldos(self, partner, company):
        """Saldos do cliente nos programas de pontos ligados (para o tablet e o caixa)."""
        if not partner:
            return []
        programas = self._boteco_programas_pos(company)
        if not programas:
            return []
        cartoes = self.env["loyalty.card"].sudo().search([("partner_id", "=", partner.id),
                                                         ("program_id", "in", programas.ids)])
        saldos = []
        for cartao in cartoes:
            programa = cartao.program_id
            premio = programa.reward_ids[:1]
            faltam = max((premio.required_points or 0) - cartao.points, 0) if premio else 0
            saldos.append({
                "programa": programa.name,
                "pontos": round(cartao.points, 2),
                "unidade": programa.portal_point_name or _("pontos"),
                "faltam": round(faltam, 2),
                "premio": premio.description or "",
            })
        return saldos
