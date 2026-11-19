from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged

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
