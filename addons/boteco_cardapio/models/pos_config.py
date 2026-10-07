import calendar

from odoo import api, fields, models


def epoch_ms(dt):
    """datetime UTC naive (como o Odoo guarda) -> milissegundos desde 1970 (para o JavaScript)."""
    if not dt:
        return None
    return calendar.timegm(dt.timetuple()) * 1000 + dt.microsecond // 1000


class PosConfig(models.Model):
    _inherit = "pos.config"

    @api.model
    def _boteco_avisar_cardapio(self):
        """Avisa tablets, QR e caixas abertos que o cardápio mudou (preço, oferta, acabou)."""
        sessoes = self.env["pos.session"].sudo().search([("state", "in", ("opening_control", "opened"))])
        for config in sessoes.config_id:
            config._notify("BOTECO_CARDAPIO", {"versao": fields.Datetime.to_string(fields.Datetime.now())})

    def boteco_estado_cardapio(self):
        """Estado dinâmico do cardápio: happy hour (com hora exata da próxima troca) e ofertas no ar.

        O horário do servidor vai junto para a tela corrigir a diferença de relógio do tablet.
        """
        self.ensure_one()
        company = self.company_id
        HappyHour = self.env["boteco.happy.hour"].sudo()
        agora = fields.Datetime.now()
        ofertas = self.env["boteco.oferta.relampago"].sudo()._ofertas_no_ar(company)
        return {
            "agora": epoch_ms(agora),
            "happy_ativo": HappyHour._ativo_em(agora, company),
            "proxima_troca": epoch_ms(HappyHour._proxima_troca(agora, company)),
            "ofertas": [
                {
                    "id": o.id,
                    "nome": o.name,
                    "product_id": o.product_id.id,
                    "preco": o.preco,
                    "preco_normal": o.product_id.lst_price,
                    "restante": o.restante,
                    "fim": epoch_ms(o.fim),
                }
                for o in ofertas
            ],
            "esgotados": self.env["product.product"].sudo().search(
                [("boteco_esgotado", "=", True), ("available_in_pos", "=", True)]
            ).ids,
        }
