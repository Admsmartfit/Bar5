from odoo.exceptions import AccessDenied, ValidationError
from odoo.tests import tagged

from ..models.res_users import pin_trivial
from .common import BotecoCase


@tagged("post_install", "-at_install", "boteco")
class TestPin(BotecoCase):
    def _login(self, user, pin):
        return self.env["res.users"].with_user(user)._check_credentials(
            {"type": "boteco_pin", "login": user.login, "pin": pin}, {"interactive": True}
        )

    def test_pin_guardado_com_hash(self):
        hash_ = self.garcom.sudo().boteco_pin_hash
        self.assertTrue(hash_)
        self.assertNotIn("2580", hash_)
        self.assertTrue(hash_.startswith("$pbkdf2-sha256$"))
        self.assertTrue(self.garcom.boteco_tem_pin)

    def test_pin_certo_entra(self):
        info = self._login(self.garcom, "2580")
        self.assertEqual(info["uid"], self.garcom.id)
        self.assertEqual(info["auth_method"], "boteco_pin")

    def test_pin_errado_nao_entra(self):
        with self.assertRaises(AccessDenied):
            self._login(self.garcom, "0000")

    def test_bloqueio_apos_5_erros(self):
        # try/except em vez de assertRaises: o assertRaises do Odoo desfaz (savepoint)
        # o que foi gravado, e em produção a tentativa é gravada num cursor separado.
        for _i in range(5):
            try:
                self._login(self.caixa, "1111")
            except AccessDenied:
                pass
            else:
                self.fail("PIN errado entrou")
        self.assertTrue(self.caixa.boteco_bloqueado)
        # Mesmo com o PIN certo, continua bloqueado
        with self.assertRaises(AccessDenied):
            self._login(self.caixa, "3691")
        # Gerente desbloqueia
        self.caixa.action_boteco_desbloquear_pin()
        self.caixa.invalidate_recordset(["boteco_bloqueado"])
        self.assertFalse(self.caixa.boteco_bloqueado)
        self.assertEqual(self._login(self.caixa, "3691")["uid"], self.caixa.id)

    def test_dono_nao_entra_com_pin(self):
        dono = self._pessoa("Dono Teste", "dono_teste", self.perfil_dono, "8642")
        with self.assertRaises(AccessDenied):
            self._login(dono, "8642")

    def test_regras_do_pin(self):
        with self.assertRaises(ValidationError):
            self.garcom.boteco_pin = "12"
        with self.assertRaises(ValidationError):
            self.garcom.boteco_pin = "abcd"
        with self.assertRaises(ValidationError):
            self.garcom.boteco_pin = "1234"  # sequência
        with self.assertRaises(ValidationError):
            self.garcom.boteco_pin = "7314"  # já é do gerente
        self.assertTrue(pin_trivial("4444"))
        self.assertTrue(pin_trivial("9876"))
        self.assertFalse(pin_trivial("2580"))

    def test_senha_normal_continua_funcionando(self):
        # O override não pode atrapalhar o login com senha
        with self.assertRaises(AccessDenied):
            self.env["res.users"].with_user(self.garcom)._check_credentials(
                {"type": "password", "login": self.garcom.login, "password": "errada"}, {"interactive": True}
            )

    def test_bloqueio_e_por_aparelho(self):
        """Auditoria: errar o PIN da pessoa num tablet não a tira dos outros (5 por aparelho, 15 no total)."""
        Users = type(self.env["res.users"])
        ip = {"atual": "10.0.0.11"}
        self.patch(Users, "_boteco_ip", lambda self_: ip["atual"])
        for _i in range(5):
            try:
                self._login(self.caixa, "1111")
            except AccessDenied:
                pass
        with self.assertRaises(AccessDenied):
            self._login(self.caixa, "3691")  # bloqueado neste tablet
        ip["atual"] = "10.0.0.12"
        self.assertEqual(self._login(self.caixa, "3691")["uid"], self.caixa.id)  # no outro, entra

    def test_mensagem_mostra_quantas_tentativas_restam(self):
        with self.assertRaisesRegex(AccessDenied, "Restam 4 tentativas"):
            self._login(self.garcom, "0000")
