from odoo import api, fields, models


class RestaurantTable(models.Model):
    _inherit = "restaurant.table"

    boteco_chamou_garcom = fields.Boolean("Chamou o garçom", copy=False)
    boteco_chamou_garcom_em = fields.Datetime(copy=False)
    boteco_pediu_conta = fields.Boolean("Pediu a conta", copy=False)
    boteco_pediu_conta_em = fields.Datetime(copy=False)

    @api.model
    def _load_pos_data_fields(self, config_id):
        campos = super()._load_pos_data_fields(config_id)
        return campos + ["boteco_chamou_garcom", "boteco_chamou_garcom_em", "boteco_pediu_conta", "boteco_pediu_conta_em"]

    def _boteco_dados_mesa(self):
        self.ensure_one()
        return {
            "id": self.id,
            "numero": self.table_number,
            "boteco_chamou_garcom": self.boteco_chamou_garcom,
            "boteco_chamou_garcom_em": fields.Datetime.to_string(self.boteco_chamou_garcom_em) if self.boteco_chamou_garcom_em else False,
            "boteco_pediu_conta": self.boteco_pediu_conta,
            "boteco_pediu_conta_em": fields.Datetime.to_string(self.boteco_pediu_conta_em) if self.boteco_pediu_conta_em else False,
        }

    def _boteco_avisar(self, evento=None):
        """Avisa os PDVs (mapa de mesas e celular do garçom) em tempo real."""
        for mesa in self:
            for config in mesa.floor_id.pos_config_ids:
                if config.current_session_id:
                    config._notify("BOTECO_MESA", {**mesa._boteco_dados_mesa(), "evento": evento})

    def boteco_marcar(self, chamou_garcom=None, pediu_conta=None):
        agora = fields.Datetime.now()
        vals = {}
        if chamou_garcom is not None:
            vals.update(boteco_chamou_garcom=chamou_garcom, boteco_chamou_garcom_em=agora if chamou_garcom else False)
        if pediu_conta is not None:
            vals.update(boteco_pediu_conta=pediu_conta, boteco_pediu_conta_em=agora if pediu_conta else False)
        if vals:
            self.sudo().write(vals)
            evento = "pediu_conta" if pediu_conta else "chamou_garcom" if chamou_garcom else "atendido"
            self._boteco_avisar(evento)
        return True

    def _boteco_limpar_chamados(self):
        marcadas = self.filtered(lambda m: m.boteco_chamou_garcom or m.boteco_pediu_conta)
        if marcadas:
            marcadas.sudo().write({
                "boteco_chamou_garcom": False, "boteco_chamou_garcom_em": False,
                "boteco_pediu_conta": False, "boteco_pediu_conta_em": False,
            })
            marcadas._boteco_avisar("liberada")
