from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

from odoo.addons.boteco_cardapio.tests.common_pos import BotecoPosCase


@tagged("post_install", "-at_install", "boteco")
class TestPrimeirosPassos(BotecoPosCase):
    """Etapa 33: lista de primeiros passos que se marca sozinha."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.dono = cls._pessoa("Dono Implantação", "dono_impl", cls.perfil_dono, "8642")
        cls.Impl = cls.env["boteco.implantacao"].with_user(cls.dono)
        cls.env.company.write({"boteco_implantacao_concluida": False, "boteco_assistente_visto": False})

    def _passo(self, estado, codigo):
        return next(p for f in estado["fases"] for p in f["passos"] if p["codigo"] == codigo)

    def test_cardapio_se_marca_sozinho(self):
        self.assertEqual(self._passo(self.Impl.estado(), "cardapio")["situacao"], "pendente")
        Produto = self.env["product.template"]
        for i in range(10):
            Produto.create({"name": "Item %s" % i, "list_price": 10, "available_in_pos": True, "sale_ok": True,
                            "boteco_setor_id": self.setor_bar.id})
        self.assertEqual(self._passo(self.Impl.estado(), "cardapio")["situacao"], "feito")

    def test_impressoras_precisam_imprimir_teste(self):
        impressora = self.env["boteco.impressora"].create({"name": "Bar", "ip": "127.0.0.1"})
        for setor in self.env["boteco.setor"].search([]):
            setor.impressora_id = impressora
        self.assertEqual(self._passo(self.Impl.estado(), "impressoras")["situacao"], "pendente")
        impressora.sudo().estado = "ok"  # o papel de teste saiu
        self.assertEqual(self._passo(self.Impl.estado(), "impressoras")["situacao"], "feito")

    def test_equipe_com_pin(self):
        # common já cria garçom, caixa e gerente com PIN
        self.assertEqual(self._passo(self.Impl.estado(), "equipe_pin")["situacao"], "feito")

    def test_pular_so_opcional_e_ja_fiz_so_manual(self):
        estado = self.Impl.marcar("qr_mesas", "pulado")
        self.assertEqual(self._passo(estado, "qr_mesas")["situacao"], "pulado")
        with self.assertRaises(UserError):
            self.Impl.marcar("cardapio", "pulado")  # obrigatório
        with self.assertRaises(UserError):
            self.Impl.marcar("cardapio", "feito")  # se marca sozinho
        estado = self.Impl.marcar("venda_teste", "feito")  # manual
        self.assertEqual(self._passo(estado, "venda_teste")["situacao"], "feito")

    def test_assistente_e_abrir_a_casa(self):
        self.assertTrue(self.Impl.estado()["assistente"])
        self.Impl.salvar_assistente({"nome": "Bar do Zé", "cnpj": "11.222.333/0001-81", "rua": "Rua A, 10",
                                     "cidade": "Santos", "tipo_unidade": "bar_e_cozinha"})
        estado = self.Impl.estado()
        self.assertFalse(estado["assistente"])
        self.assertEqual(self.env.company.name, "Bar do Zé")
        self.assertEqual(self._passo(estado, "empresa_dados")["situacao"], "feito")
        self.assertTrue(self.Impl.pendente_para(self.dono))
        self.assertFalse(self.Impl.pendente_para(self.garcom))
        with self.assertRaises(UserError):
            self.Impl.concluir()  # ainda faltam obrigatórios
        self.Impl.concluir(forcar=True)
        self.assertTrue(self.env.company.boteco_implantacao_concluida)
        self.assertFalse(self.Impl.pendente_para(self.dono))

    def test_garcom_nao_configura(self):
        with self.assertRaises(UserError):
            self.env["boteco.implantacao"].with_user(self.garcom).acao("cardapio")

    def test_banco_em_uso_nao_ve_assistente(self):
        self._sincronizar(self._pedido([self._linha(self.refri, 1)], pagamentos=[(self.pm_dinheiro, 7.0)]))
        self.env["boteco.implantacao"]._marcar_banco_em_uso()
        estado = self.Impl.estado()
        self.assertFalse(estado["assistente"])
        self.assertEqual(self._passo(estado, "venda_teste")["situacao"], "feito")

    def test_acao_visita_marca_feito(self):
        acao = self.Impl.acao("recursos")
        self.assertTrue(acao)
        self.assertEqual(self._passo(self.Impl.estado(), "recursos")["situacao"], "feito")
        self.assertEqual(fields.Date.today(), fields.Date.today())


@tagged("post_install", "-at_install", "boteco")
class TestWifiEMensagens(TransactionCase):
    """Passo 'Wi-Fi' abre a tela própria (não o cadastro da empresa); chave das mensagens."""

    def test_passo_wifi_abre_tela_propria_e_salva(self):
        acao = self.env["boteco.implantacao"].acao("redes")
        self.assertEqual(acao["res_model"], "boteco.wifi")
        wifi = self.env["boteco.wifi"].browse(acao["res_id"])
        wifi.rede_clientes = "texto errado"
        with self.assertRaises(UserError):
            wifi.action_salvar()
        wifi.write({"rede_clientes": "192.168.20.0/24", "rede_equipe": ""})
        wifi.action_salvar()
        self.assertEqual(self.env.company.boteco_rede_clientes, "192.168.20.0/24")
        self.assertTrue(self.env["boteco.implantacao"]._v_redes(self.env.company))

    def test_endereco_do_roteador_vira_a_rede_inteira(self):
        acao = self.env["boteco.implantacao"].acao("redes")
        wifi = self.env["boteco.wifi"].browse(acao["res_id"])
        wifi.write({"rede_clientes": "192.168.15.1", "rede_equipe": ""})
        wifi.action_salvar()
        self.assertEqual(self.env.company.boteco_rede_clientes, "192.168.15.0/24")
        self.env.company.boteco_rede_sistema = "10.0.0.7"
        self.assertEqual(self.env.company.boteco_rede_sistema, "10.0.0.0/24")
        estado = self.env["boteco.implantacao"].estado()
        redes = [p for f in estado["fases"] for p in f["passos"] if p["codigo"] == "redes"][0]
        self.assertEqual(redes["situacao"], "feito")  # mesmo que antes tenha sido pulado

    def test_rede_do_aparelho(self):
        from odoo.addons.boteco_base.models.boteco_wifi import rede_do_ip
        self.assertEqual(rede_do_ip("192.168.0.37"), "192.168.0.0/24")
        self.assertEqual(rede_do_ip("8.8.8.8"), "")  # internet não é rede do bar
        self.assertEqual(rede_do_ip("172.18.0.1"), "")  # Docker do próprio servidor

    def test_mensagens_desligadas_por_padrao(self):
        self.assertFalse(self.env["res.company"].new({}).boteco_flag_mensagens)


@tagged("post_install", "-at_install", "boteco")
class TestPrimeirosPassosBarra(TransactionCase):
    """Caixa "Primeiros passos" na barra de cima: some ao concluir e a chave fica desligada."""

    def test_caixa_some_ao_concluir_e_chave_desliga(self):
        company = self.env.company
        company.write({"boteco_flag_assistente_implantacao": True})
        self.assertFalse(company.boteco_implantacao_concluida)
        Impl = self.env["boteco.implantacao"]
        resumo = Impl.resumo()
        self.assertTrue(resumo["mostrar"])
        self.assertIn("total", resumo)
        Impl.concluir(forcar=True)
        self.assertFalse(company.boteco_flag_assistente_implantacao)
        self.assertFalse(Impl.resumo()["mostrar"])
        # Ligar de novo na Central de Recursos reabre os Primeiros passos
        company.boteco_flag_assistente_implantacao = True
        self.assertFalse(company.boteco_implantacao_concluida)
        self.assertTrue(Impl.resumo()["mostrar"])

    def test_sem_menu_no_inicio(self):
        self.assertFalse(self.env.ref("boteco_base.menu_boteco_primeiros_passos", raise_if_not_found=False))
