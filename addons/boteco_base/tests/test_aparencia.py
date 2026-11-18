from odoo.tests import HttpCase, new_test_user, tagged

from .common import BotecoCase


@tagged("post_install", "-at_install")
class TestAparencia(BotecoCase):
    def test_padrao_alto_contraste_e_claro(self):
        self.assertEqual(self.garcom.boteco_aparencia(),
                         {"tema": "claro", "alto_contraste": True, "fonte": "normal", "cor": "roxo"})

    def test_pessoa_muda_a_propria_aparencia(self):
        # Garçom não é administrador: precisa poder salvar a própria preferência
        self.garcom.with_user(self.garcom).write({"boteco_tema": "escuro", "boteco_tamanho_fonte": "grande",
                                                  "boteco_cor_destaque": "azul", "boteco_alto_contraste": False})
        self.assertEqual(self.garcom.boteco_aparencia(),
                         {"tema": "escuro", "alto_contraste": False, "fonte": "grande", "cor": "azul"})


@tagged("post_install", "-at_install")
class TestAparenciaSessao(HttpCase):
    def test_sessao_leva_a_aparencia(self):
        pessoa = new_test_user(self.env, login="tema_auto", password="tema_auto123", groups="base.group_user")
        pessoa.write({"boteco_tema": "auto", "boteco_cor_destaque": "verde"})
        self.authenticate("tema_auto", "tema_auto123")
        resposta = self.url_open("/web/session/get_session_info", data="{}",
                                 headers={"Content-Type": "application/json"})
        aparencia = resposta.json()["result"]["boteco_aparencia"]
        self.assertEqual((aparencia["tema"], aparencia["cor"]), ("auto", "verde"))
