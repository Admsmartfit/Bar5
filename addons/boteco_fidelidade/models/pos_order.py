from odoo import _, fields, models

from odoo.addons.boteco_pos.models.boteco_crm import link_whatsapp


class PosOrder(models.Model):
    _inherit = "pos.order"

    def confirm_coupon_programs(self, coupon_data):
        """O servidor não confia na tela: consumo de funcionário (ou fidelidade desligada) não ganha pontos."""
        sem_pontos = self.boteco_tipo_conta == "funcionario" or not self.company_id.boteco_recurso_ativo("fidelidade")
        if sem_pontos and coupon_data:
            pontos = self.env["loyalty.program"].sudo().browse(
                {int(v.get("program_id") or 0) for v in coupon_data.values()} - {0}
            ).filtered(lambda p: p.program_type == "loyalty").ids
            coupon_data = {
                k: ({**v, "points": min(v.get("points") or 0, 0)} if v.get("program_id") in pontos else v)
                for k, v in coupon_data.items()
            }
        return super().confirm_coupon_programs(coupon_data)

    def _boteco_resumo_mesa(self, mesa):
        """'Minha conta' no tablet/QR: também o saldo de fidelidade do cliente da mesa."""
        resumo = super()._boteco_resumo_mesa(mesa)
        pedidos = self.sudo().search([("table_id", "=", mesa.id), ("state", "=", "draft")])
        company = pedidos[:1].company_id or mesa.floor_id.pos_config_ids[:1].company_id or self.env.company
        Programa = self.env["loyalty.program"].sudo()
        resumo["fidelidade"] = [
            {**saldo, "cliente": (parceiro.name or "").split(" ")[0]}
            for parceiro in pedidos.partner_id
            for saldo in Programa._boteco_saldos(parceiro, company)
        ]
        return resumo


class BotecoReguaCrm(models.TransientModel):
    _inherit = "boteco.regua.crm"

    def action_gerar(self):
        """Aniversariante: com o cupom de aniversário ligado, a mensagem já leva o código (um por ano)."""
        resultado = super().action_gerar()
        programa = self.env["loyalty.program"].sudo().search(
            [("boteco_modelo", "=", "aniversario"), ("active", "=", True)], limit=1)
        if not programa or not self.env.company.boteco_recurso_ativo("fidelidade"):
            return resultado
        Cartao = self.env["loyalty.card"].sudo()
        inicio_ano = fields.Date.context_today(self).replace(month=1, day=1)
        for linha in self.linha_ids.filtered(lambda l: l.motivo == "aniversario" and l.partner_id):
            cupom = Cartao.search([("program_id", "=", programa.id), ("partner_id", "=", linha.partner_id.id),
                                   ("create_date", ">=", inicio_ano), ("points", ">", 0)], limit=1)
            if not cupom:
                cupom = Cartao.with_context(action_no_send_mail=True).create(
                    {"program_id": programa.id, "partner_id": linha.partner_id.id, "points": 1})
            mensagem = "%s %s" % (linha.mensagem, _("Seu presente: use o código %s no caixa.", cupom.code))
            cliente = linha.partner_id
            linha.write({"mensagem": mensagem, "link_whatsapp": link_whatsapp(cliente.mobile or cliente.phone, mensagem)})
        return resultado
