from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.boteco_cardapio.tests.common_pos import BotecoPosCase


@tagged("post_install", "-at_install", "boteco")
class TestOcupacaoMesa(BotecoPosCase):
    """Etapa 13: ocupação padrão na abertura e junção de mesas."""

    def test_abertura_sugere_lugares_da_mesa(self):
        self.env.company.boteco_flag_ocupacao_padrao_mesa = True
        self.mesa1.boteco_iniciar_ocupacao()
        self.assertEqual(self.mesa1.boteco_clientes_atuais, 4)
        self.assertEqual(self.mesa1.boteco_n_clientes(), 4)

    def test_flag_desligada_nao_sugere(self):
        self.env.company.boteco_flag_ocupacao_padrao_mesa = False
        self.mesa1.boteco_iniciar_ocupacao()
        self.assertEqual(self.mesa1.boteco_clientes_atuais, 0)
        self.assertEqual(self.mesa1.boteco_n_clientes(), 1)

    def test_garcom_digitou_pessoas_vira_n_da_mesa(self):
        self._sincronizar(self._pedido([self._linha(self.refri, 1)], mesa=self.mesa2, pessoas=6))
        self.assertEqual(self.mesa2.boteco_clientes_atuais, 6)

    def test_mesa_paga_zera_ocupacao(self):
        self.mesa1.boteco_definir_clientes(3)
        self.mesa1._boteco_limpar_chamados()  # nenhuma conta aberta
        self.assertEqual(self.mesa1.boteco_clientes_atuais, 0)

    def test_juncao_soma_clientes(self):
        self.env.company.boteco_flag_salao_juncao_mesas = True
        self.mesa1.boteco_definir_clientes(4)
        self.mesa2.boteco_definir_clientes(3)
        total = self.mesa2.action_boteco_agrupar_mesas(self.mesa1.id)
        self.assertEqual(total, 7)
        self.assertEqual(self.mesa2.parent_id, self.mesa1)
        self.assertEqual(self.mesa2.boteco_n_clientes(), 7)

    def test_juncao_desligada_recusa(self):
        self.env.company.boteco_flag_salao_juncao_mesas = False
        with self.assertRaises(UserError):
            self.mesa2.action_boteco_agrupar_mesas(self.mesa1.id)
