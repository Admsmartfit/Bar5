from odoo import api, fields, models

TIPOS = [("freezer", "Freezer"), ("camara_fria", "Câmara fria"), ("geladeira", "Geladeira / balcão refrigerado")]


class BotecoEquipamento(models.Model):
    _name = "boteco.equipamento"
    _description = "Equipamento de frio"
    _order = "name"

    name = fields.Char("Equipamento", required=True)
    tipo = fields.Selection(TIPOS, required=True, default="freezer")
    temperatura_min = fields.Float("Mínima aceita (°C)", default=-25.0)
    temperatura_max = fields.Float("Máxima aceita (°C)", default=-18.0)
    warehouse_id = fields.Many2one("stock.warehouse", string="Unidade")
    active = fields.Boolean(default=True)
    company_id = fields.Many2one("res.company", default=lambda s: s.env.company)

    @api.onchange("tipo")
    def _onchange_tipo(self):
        faixas = {"freezer": (-25.0, -18.0), "camara_fria": (0.0, 5.0), "geladeira": (0.0, 7.0)}
        self.temperatura_min, self.temperatura_max = faixas.get(self.tipo, (0.0, 5.0))


class BotecoTemperatura(models.Model):
    """Planilha diária de controle de temperatura exigida pela Vigilância Sanitária."""

    _name = "boteco.temperatura"
    _description = "Registro de temperatura"
    _order = "data desc, id desc"

    equipamento_id = fields.Many2one("boteco.equipamento", required=True, ondelete="restrict")
    data = fields.Datetime(default=fields.Datetime.now, required=True)
    temperatura = fields.Float("Temperatura (°C)", required=True)
    responsavel_id = fields.Many2one("res.users", string="Quem mediu", default=lambda s: s.env.user)
    fora_da_faixa = fields.Boolean(compute="_compute_fora_da_faixa", store=True)
    acao_corretiva = fields.Char("O que foi feito", help="Obrigatório quando a temperatura está fora da faixa.")
    company_id = fields.Many2one(related="equipamento_id.company_id", store=True)

    @api.depends("temperatura", "equipamento_id.temperatura_min", "equipamento_id.temperatura_max")
    def _compute_fora_da_faixa(self):
        for r in self:
            e = r.equipamento_id
            r.fora_da_faixa = bool(e) and not (e.temperatura_min <= r.temperatura <= e.temperatura_max)

    @api.model
    def boteco_registrar(self, equipamento_id, temperatura, acao_corretiva=None):
        registro = self.create({"equipamento_id": equipamento_id, "temperatura": temperatura,
                                "acao_corretiva": acao_corretiva or False})
        return {"id": registro.id, "fora_da_faixa": registro.fora_da_faixa}
