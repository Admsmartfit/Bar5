from odoo import models


class ResCompany(models.Model):
    _inherit = "res.company"

    def write(self, vals):
        res = super().write(vals)
        if "boteco_flag_garcom_tags_rapidas" in vals:
            self._boteco_aplicar_tags_rapidas()
        return res

    def _boteco_aplicar_tags_rapidas(self):
        """Etapa 20: liga/desliga as observações de 1 toque ([Sem cebola], [Ao ponto]...) nos PDVs."""
        notas = self.env["pos.note"].sudo().search([("boteco_tag_rapida", "=", True)])
        for company in self:
            configs = self.env["pos.config"].sudo().search([("company_id", "=", company.id)])
            comando = "link" if company.boteco_flag_garcom_tags_rapidas else "unlink"
            for config in configs:
                config.note_ids = [(4 if comando == "link" else 3, n.id) for n in notas]
