import json

from odoo.tests import HttpCase, tagged

from .common import BotecoCase


@tagged("post_install", "-at_install", "boteco")
class TestPinDesbloqueio(HttpCase, BotecoCase):
    """Auditoria: o gerente desbloqueia a pessoa na própria tela de PIN."""

    def _rpc(self, rota, params):
        self.env.flush_all()
        r = self.url_open(rota, data=json.dumps({"jsonrpc": "2.0", "method": "call", "params": params}),
                          headers={"Content-Type": "application/json"}).json()
        self.env.invalidate_all()
        return r.get("result", r.get("error"))

    def test_gerente_desbloqueia_na_tela(self):
        Tentativa = self.env["boteco.pin.tentativa"]
        for _i in range(5):
            Tentativa.create({"user_id": self.caixa.id, "tipo": "login", "sucesso": False, "ip": "127.0.0.1"})
        self.assertTrue(Tentativa._bloqueado(self.caixa.id, "login", "127.0.0.1"))
        errado = self._rpc("/boteco/pin/desbloquear", {"user_id": self.caixa.id, "pin_gerente": "0000"})
        self.assertIn("não confere", errado["erro"])
        certo = self._rpc("/boteco/pin/desbloquear", {"user_id": self.caixa.id, "pin_gerente": "7314"})
        self.assertTrue(certo["ok"])
        self.assertFalse(Tentativa._bloqueado(self.caixa.id, "login", "127.0.0.1"))
        self.assertTrue(self.env["boteco.auditoria"].search([("acao", "=", "pin_desbloqueado")]))
