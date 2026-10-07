import secrets

from odoo import _, fields, models
from odoo.exceptions import UserError


class RestaurantTable(models.Model):
    _inherit = "restaurant.table"

    boteco_codigo_sessao = fields.Char("Código da sessão da mesa", copy=False,
                                       help="Muda a cada abertura de mesa: celular liberado em outra visita não pede mais.")
    boteco_sessao_aberta_em = fields.Datetime(copy=False)
    boteco_maior18_confirmado = fields.Boolean("Idade conferida (+18)", copy=False)
    boteco_dispositivo_ids = fields.One2many("boteco.dispositivo", "mesa_id", string="Aparelhos")

    def _boteco_garantir_sessao(self):
        self.ensure_one()
        if not self.boteco_codigo_sessao:
            self.sudo().write({"boteco_codigo_sessao": secrets.token_hex(8),
                               "boteco_sessao_aberta_em": fields.Datetime.now()})
        return self.boteco_codigo_sessao

    def _boteco_mesa_aberta(self):
        self.ensure_one()
        return bool(self.boteco_codigo_sessao) or bool(
            self.env["pos.order"].sudo().search_count([("table_id", "=", self.id), ("state", "=", "draft")])
        )

    def _boteco_limpar_chamados(self):
        """Conta fechada: fecha a sessão da mesa (celulares precisam de nova liberação)."""
        res = super()._boteco_limpar_chamados()
        self._boteco_encerrar_sessao()
        return res

    def _boteco_encerrar_sessao(self):
        mesas = self.filtered(lambda m: m.boteco_codigo_sessao or m.boteco_maior18_confirmado)
        if not mesas:
            return
        # Só encerra se não sobrou outra conta aberta na mesa
        abertas = self.env["pos.order"].sudo().search([("table_id", "in", mesas.ids), ("state", "=", "draft")]).table_id
        encerrar = mesas - abertas
        if encerrar:
            encerrar.sudo().write({"boteco_codigo_sessao": False, "boteco_sessao_aberta_em": False,
                                   "boteco_maior18_confirmado": False})
            celulares = self.env["boteco.dispositivo"].sudo().search([("mesa_id", "in", encerrar.ids), ("tipo", "=", "celular")])
            celulares.write({"active": False})
            encerrar._boteco_avisar("liberada")

    def boteco_confirmar_maior18(self):
        """Garçom conferiu a idade: libera os pedidos com álcool retidos desta mesa."""
        if not self.env.user.boteco_pode("pode_aprovar_qr"):
            raise UserError(_("Você não pode confirmar a idade. Chame o gerente."))
        for mesa in self:
            mesa.sudo().boteco_maior18_confirmado = True
            retidos = self.env["pos.order"].sudo().search([("table_id", "=", mesa.id), ("boteco_aguardando_garcom", "=", True),
                                                           ("state", "=", "draft")])
            retidos.write({"boteco_aguardando_garcom": False})
            retidos.boteco_marcar_enviado()
            self.env["boteco.auditoria"].registrar(
                "aprovacao_qr", registro=mesa, descricao=_("Idade conferida (+18) na mesa %s", mesa.table_number))
            mesa._boteco_avisar("maior18_ok")
        return True
