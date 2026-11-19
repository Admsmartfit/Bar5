from odoo.tests import tagged

from odoo.addons.boteco_base.tests.common import BotecoCase


@tagged("post_install", "-at_install", "boteco")
class TestAjudaRapida(BotecoCase):
    """Etapa 26: o índice da ajuda traz caminho real do menu e respeita o perfil."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.dono = cls._pessoa("Dono Ajuda", "dono_ajuda", cls.perfil_dono, "8642")
        cls.Artigo = cls.env["boteco.ajuda.artigo"]

    def _artigo(self, user, codigo):
        indice = self.Artigo.with_user(user).indice()
        return next((a for a in indice["artigos"] if a["codigo"] == codigo), None), indice

    def test_whatsapp_fornecedor_com_caminho_do_menu(self):
        artigo, indice = self._artigo(self.gerente, "whatsapp_fornecedor")
        self.assertEqual(artigo["caminho"], "Compras e estoque › Comprar › Fornecedores")
        self.assertEqual(artigo["acao"], "boteco_estoque.action_boteco_fornecedores")
        self.assertEqual(artigo["destacar"], "mobile")
        self.assertTrue(any(t["nome"] == "Fornecedores" for t in indice["telas"]))

    def test_caminho_acompanha_o_menu(self):
        menu = self.env.ref("boteco_estoque.menu_boteco_fornecedores")
        menu.parent_id = self.env.ref("boteco_estoque.menu_boteco_estoque")
        artigo, _indice = self._artigo(self.gerente, "whatsapp_fornecedor")
        self.assertEqual(artigo["caminho"], "Compras e estoque › Estoque › Fornecedores")

    def test_garcom_nao_ve_artigo_de_gerente(self):
        artigo, indice = self._artigo(self.garcom, "whatsapp_fornecedor")
        self.assertIsNone(artigo)
        self.assertTrue(any(a["codigo"] == "trocar_pessoa" for a in indice["artigos"]))
        self.assertFalse(indice["chaves"])  # só o dono vê as chaves da Central

    def test_dono_ve_chaves_da_central(self):
        _artigo, indice = self._artigo(self.dono, "recursos_ligar")
        self.assertTrue(any(c["campo"] == "boteco_flag_ajuda_rapida" for c in indice["chaves"]))

    def test_sem_acesso_ao_menu(self):
        # Artigo para todos apontando para tela de dono: garçom vê "peça ao gerente", sem caminho nem botão
        self.Artigo.create({"codigo": "teste_sem_acesso", "titulo": "Teste",
                            "menu_id": self.env.ref("boteco_base.menu_boteco_central_recursos").id,
                            "acao_xmlid": "boteco_base.action_boteco_central_recursos"})
        artigo, _indice = self._artigo(self.garcom, "teste_sem_acesso")
        self.assertTrue(artigo["sem_acesso"])
        self.assertFalse(artigo["caminho"])
        self.assertFalse(artigo["acao"])

    def test_registrar_busca_e_avaliacao(self):
        self.Artigo.with_user(self.garcom).registrar_busca("senha do wifi", False)
        artigo = self.env.ref("boteco_estoque.ajuda_whatsapp_fornecedor")
        self.Artigo.with_user(self.gerente).avaliar(artigo.id, False)
        buscas = self.env["boteco.ajuda.busca"].search([])
        self.assertTrue(buscas.filtered(lambda b: b.termo == "senha do wifi" and not b.achou))
        self.assertTrue(buscas.filtered(lambda b: b.nao_ajudou and b.artigo_id == artigo))
        self.assertEqual(artigo.nao_uteis, 1)

    def test_todas_as_acoes_dos_artigos_existem(self):
        for artigo in self.Artigo.search([("acao_xmlid", "!=", False)]):
            self.assertTrue(self.env.ref(artigo.acao_xmlid, raise_if_not_found=False),
                            "Ação inexistente no artigo %s: %s" % (artigo.codigo, artigo.acao_xmlid))

    def test_odoobot_desligado(self):
        if "odoobot_state" not in self.env["res.users"]._fields:
            self.skipTest("mail_bot não instalado")
        novo = self._pessoa("Nova Pessoa", "nova_pessoa_bot", self.perfil_garcom, "9753")
        self.assertEqual(novo.odoobot_state, "disabled")
        self.env["res.users"]._boteco_desligar_odoobot()
        self.assertFalse(self.env["res.users"].search([("odoobot_state", "!=", "disabled"), ("share", "=", False)]))
