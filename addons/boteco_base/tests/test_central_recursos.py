from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestCentralRecursos(TransactionCase):
    def test_padroes(self):
        company = self.env.company
        self.assertTrue(company.boteco_recurso_ativo("quarentena_pedidos_anomalos"))
        self.assertTrue(company.boteco_recurso_ativo("boteco_flag_ocupacao_padrao_mesa"))
        self.assertFalse(company.boteco_recurso_ativo("pdv_fichas_avulsas"))

    def test_desligar_vale_na_hora(self):
        company = self.env.company
        company.boteco_flag_correlacao_vinho_agua = False
        self.assertFalse(company.boteco_recurso_ativo("correlacao_vinho_agua"))
        company.boteco_flag_correlacao_vinho_agua = True
        self.assertTrue(company.boteco_recurso_ativo("correlacao_vinho_agua"))

    def test_flag_desconhecida_e_desligada(self):
        self.assertFalse(self.env.company.boteco_recurso_ativo("nao_existe"))

    def test_acao_abre_empresa_atual(self):
        acao = self.env["res.company"].action_boteco_central_recursos()
        # O botão do cadastro da empresa chama com o registro
        self.assertEqual(self.env.company.action_boteco_central_recursos()["res_id"], acao["res_id"])
        self.assertEqual(acao["res_id"], self.env.company.id)
        self.assertEqual(acao["res_model"], "res.company")
