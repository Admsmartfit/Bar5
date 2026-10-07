import threading
from datetime import timedelta

from odoo import SUPERUSER_ID, api, fields, models

MAX_TENTATIVAS = 5
JANELA_BLOQUEIO_MIN = 15


class BotecoPinTentativa(models.Model):
    """Histórico de tentativas de PIN (login e autorização do gerente).

    Gravado num cursor separado para que a tentativa errada fique registrada
    mesmo quando a transação principal é desfeita pelo erro de acesso.
    """

    _name = "boteco.pin.tentativa"
    _description = "Tentativa de PIN"
    _order = "id desc"
    _log_access = False

    data = fields.Datetime(default=fields.Datetime.now, required=True, index=True)
    user_id = fields.Many2one("res.users", string="Pessoa", index=True, ondelete="cascade")
    tipo = fields.Selection(
        [("login", "Entrada"), ("autorizacao", "Autorização do gerente"), ("quiosque", "Sair do quiosque")],
        required=True,
    )
    sucesso = fields.Boolean()
    ip = fields.Char()

    @api.model
    def _registrar_isolado(self, user_id, tipo, sucesso, ip=None):
        """Grava a tentativa e confirma na hora, fora da transação atual.

        Nos testes automáticos tudo roda numa transação só (que é desfeita no fim),
        então ali a tentativa é gravada no cursor atual.
        """
        vals = {"user_id": user_id, "tipo": tipo, "sucesso": sucesso, "ip": ip}
        if getattr(threading.current_thread(), "testing", False):
            self.sudo().create(vals)
            return
        with self.env.registry.cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})
            env[self._name].create(vals)

    @api.model
    def _falhas_recentes(self, user_id, tipo):
        """Falhas seguidas desde o último acerto, dentro da janela de bloqueio."""
        limite = fields.Datetime.now() - timedelta(minutes=JANELA_BLOQUEIO_MIN)
        tentativas = self.sudo().search(
            [("user_id", "=", user_id), ("tipo", "=", tipo), ("data", ">=", limite)],
            order="id desc",
            limit=MAX_TENTATIVAS,
        )
        falhas = 0
        for t in tentativas:
            if t.sucesso:
                break
            falhas += 1
        return falhas

    @api.model
    def _bloqueado(self, user_id, tipo):
        return self._falhas_recentes(user_id, tipo) >= MAX_TENTATIVAS

    @api.model
    def _limpar_antigas(self):
        """Cron: guarda 90 dias de tentativas."""
        self.sudo().search([("data", "<", fields.Datetime.now() - timedelta(days=90))]).unlink()
