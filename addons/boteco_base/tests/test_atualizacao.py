import os
import tempfile
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import BotecoCase


@tagged("post_install", "-at_install")
class TestAtualizacao(BotecoCase):
    """Tela 'Atualizar sistema': lê o que o agente do servidor escreveu e grava o pedido."""

    def setUp(self):
        super().setUp()
        self.pasta = tempfile.mkdtemp()
        ambiente = patch.dict(os.environ, {"BOTECO_ATUALIZACAO_DIR": self.pasta})
        ambiente.start()
        self.addCleanup(ambiente.stop)

    def _escrever(self, nome, texto):
        with open(os.path.join(self.pasta, nome), "w", encoding="utf-8") as arquivo:
            arquivo.write(texto)

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.dono = cls._pessoa("Dono Teste", "dono_teste_atualizacao", cls.perfil_dono, "8642")

    def _tela(self, **vals):
        return self.env["boteco.atualizacao"].with_user(self.dono).create(vals)

    def test_sem_agente(self):
        self.assertEqual(self._tela().estado, "sem_agente")

    def test_mostra_versoes_novas_e_pede_atualizacao(self):
        self._escrever("versao_atual.txt", "abc1234\t2026-11-10 10:00:00 -0300\tEtapa 18\n")
        self._escrever("disponiveis.txt", "def5678\t2026-11-17 09:00:00 -0300\tInstagram 8h e 14h\n"
                                          "bbb0000\t2026-11-16 09:00:00 -0300\tCorreção no KDS\n")
        self._escrever("verificacao.txt", "ok\n2026-11-17 09:30:00\norigin/master\n")
        tela = self._tela()
        self.assertEqual(tela.estado, "disponivel")
        self.assertEqual(tela.quantidade, 2)
        self.assertIn("Instagram 8h e 14h", tela.novidades)
        self.assertTrue(tela.versao_atual.startswith("abc1234"))
        with self.assertRaises(UserError):  # sem marcar "Entendi"
            tela.action_atualizar()
        tela.write({"confirmo": True, "atualizar_imagem": True})
        tela.action_atualizar()
        with open(os.path.join(self.pasta, "pedido.txt"), encoding="utf-8") as arquivo:
            self.assertEqual(arquivo.read().splitlines(), ["atualizar", "1", "dono_teste_atualizacao"])
        self.assertEqual(self._tela().estado, "pedido")
        with self.assertRaises(UserError):  # não empilha pedidos
            self._tela(confirmo=True).action_atualizar()
        self.assertTrue(self.env["boteco.auditoria"].search([("acao", "=", "atualizacao")]))

    def test_gerente_nao_atualiza(self):
        self._escrever("verificacao.txt", "ok\n2026-11-17 09:30:00\norigin/master\n")
        self._escrever("disponiveis.txt", "def5678\t2026-11-17 09:00:00 -0300\tNova\n")
        with self.assertRaises(UserError):
            self.env["boteco.atualizacao"].with_user(self.gerente).create({"confirmo": True}).action_atualizar()

    def test_resultado_da_ultima_atualizacao(self):
        self._escrever("verificacao.txt", "ok\n2026-11-17 09:30:00\norigin/master\n")
        self._escrever("status.txt", "falhou\n2026-11-17 02:00:00\n2026-11-17 02:06:00\nabc1234\nabc1234\nadmin\n")
        self._escrever("ultimo.log", "FALHOU. Trecho do log: ...")
        tela = self._tela()
        self.assertEqual(tela.estado, "falhou")
        self.assertIn("FALHOU", tela.ultimo_log)
        self.assertIn("admin", tela.ultima_atualizacao)

    def test_verificar_grava_pedido(self):
        self._escrever("verificacao.txt", "ok\n2026-11-17 09:30:00\norigin/master\n")
        self._tela().action_verificar()
        with open(os.path.join(self.pasta, "pedido.txt"), encoding="utf-8") as arquivo:
            self.assertEqual(arquivo.readline().strip(), "verificar")

    def test_sem_pasta_explica(self):
        os.environ["BOTECO_ATUALIZACAO_DIR"] = os.path.join(self.pasta, "nao_existe")
        with self.assertRaises(UserError):
            self._tela().action_verificar()
