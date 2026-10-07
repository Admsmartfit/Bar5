import secrets

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class BotecoDispositivo(models.Model):
    """Aparelho que pede pela mesa: celular do cliente (QR) ou tablet fixo da mesa.

    Celular: precisa da aprovação do garçom no primeiro pedido e vale só enquanto a mesa
    estiver na mesma sessão (o código muda a cada abertura de mesa).
    Tablet: cadastrado pelo gerente, preso a uma mesa, já vem liberado.
    """

    _name = "boteco.dispositivo"
    _description = "Aparelho de autoatendimento"
    _order = "id desc"

    name = fields.Char("Nome", compute="_compute_name", store=True)
    token = fields.Char("Identificador", required=True, index=True, copy=False,
                        default=lambda s: secrets.token_urlsafe(24))
    tipo = fields.Selection([("celular", "Celular do cliente"), ("tablet", "Tablet da mesa")],
                            default="celular", required=True)
    mesa_id = fields.Many2one("restaurant.table", string="Mesa", required=True, ondelete="cascade", index=True)
    codigo_sessao = fields.Char("Sessão da mesa", index=True)
    estado = fields.Selection(
        [("pendente", "Esperando o garçom"), ("aprovado", "Liberado"), ("recusado", "Recusado")],
        default="pendente", required=True, index=True,
    )
    aprovado_por_id = fields.Many2one("res.users", string="Liberado por")
    aprovado_em = fields.Datetime()
    ip = fields.Char()
    navegador = fields.Char()
    active = fields.Boolean(default=True)
    company_id = fields.Many2one("res.company", default=lambda s: s.env.company)

    @api.depends("tipo", "mesa_id")
    def _compute_name(self):
        for d in self:
            d.name = "%s – Mesa %s" % (dict(self._fields["tipo"].selection).get(d.tipo), d.mesa_id.table_number or "?")

    def _valido(self):
        """Pode pedir agora? Tablet: sempre que ativo. Celular: aprovado nesta sessão da mesa."""
        self.ensure_one()
        if not self.active or self.estado != "aprovado":
            return False
        if self.tipo == "tablet":
            return True
        return bool(self.mesa_id.boteco_codigo_sessao) and self.codigo_sessao == self.mesa_id.boteco_codigo_sessao

    def _dados(self):
        self.ensure_one()
        return {"id": self.id, "estado": self.estado if self.estado != "aprovado" or self._valido() else "pendente",
                "tipo": self.tipo, "mesa": self.mesa_id.table_number}

    # ------------------------------------------------------------------ garçom
    def boteco_aprovar(self):
        """Um toque do garçom libera o celular (e abre a sessão da mesa, se for o primeiro)."""
        if not self.env.user.boteco_pode("pode_aprovar_qr"):
            raise UserError(_("Você não pode liberar celulares do QR. Chame o gerente."))
        for disp in self:
            mesa = disp.mesa_id
            codigo = mesa._boteco_garantir_sessao()
            disp.sudo().write({"estado": "aprovado", "codigo_sessao": codigo,
                               "aprovado_por_id": self.env.user.id, "aprovado_em": fields.Datetime.now()})
            self.env["boteco.auditoria"].registrar(
                "aprovacao_qr", registro=mesa, descricao=_("Celular liberado na mesa %s", mesa.table_number),
                referencia=disp.token[:8],
            )
            disp._avisar()
        return True

    def boteco_recusar(self):
        if not self.env.user.boteco_pode("pode_aprovar_qr"):
            raise UserError(_("Você não pode recusar celulares do QR."))
        self.sudo().write({"estado": "recusado"})
        for disp in self:
            disp._avisar()
        return True

    def _avisar(self):
        for disp in self:
            for config in disp.mesa_id.floor_id.pos_config_ids:
                if config.current_session_id:
                    config._notify("BOTECO_DISPOSITIVO", {"id": disp.id, "estado": disp.estado, "mesa_id": disp.mesa_id.id})

    @api.model
    def boteco_pendentes(self):
        """Celulares esperando liberação (mostrados no PDV do garçom)."""
        return [
            {"id": d.id, "mesa": d.mesa_id.table_number, "mesa_id": d.mesa_id.id,
             "criado": fields.Datetime.to_string(d.create_date)}
            for d in self.sudo().search([("estado", "=", "pendente"), ("tipo", "=", "celular")], limit=30)
        ]

    def action_gerar_link_tablet(self):
        """Link para abrir no tablet da mesa (modo quiosque)."""
        self.ensure_one()
        config = self.mesa_id.floor_id.pos_config_ids[:1]
        if not config:
            raise UserError(_("A mesa não está em nenhum PDV."))
        url = config._get_self_order_url(self.mesa_id.id)
        separador = "&" if "?" in url else "?"
        return {"type": "ir.actions.act_url", "url": "%s%sboteco_tablet=%s" % (url, separador, self.token), "target": "new"}
