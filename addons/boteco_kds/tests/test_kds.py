import socket
import time
from datetime import timedelta

from odoo import fields
from odoo.tests import tagged

from odoo.addons.boteco_base.tests.test_escpos import ImpressoraFalsa
from odoo.addons.boteco_cardapio.tests.common_pos import BotecoPosCase


def porta_livre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@tagged("post_install", "-at_install", "boteco")
class TestKds(BotecoPosCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.ref("boteco_cardapio.happy_hour_padrao").active = False

    def setUp(self):
        super().setUp()
        self.falsa_bar = ImpressoraFalsa()
        self.falsa_chapa = ImpressoraFalsa()
        self.addCleanup(self.falsa_bar.fechar)
        self.addCleanup(self.falsa_chapa.fechar)
        Impressora = self.env["boteco.impressora"]
        self.imp_bar = Impressora.create({"name": "Impressora do bar", "ip": "127.0.0.1", "porta": self.falsa_bar.porta})
        self.imp_chapa = Impressora.create({"name": "Impressora da chapa", "ip": "127.0.0.1", "porta": self.falsa_chapa.porta})
        self.setor_bar.impressora_id = self.imp_bar
        self.setor_chapa.impressora_id = self.imp_chapa
        self.Ticket = self.env["boteco.kds.pedido"]
        self.Job = self.env["boteco.impressao.job"]

    def _esperar(self, falsa, quantidade, segundos=3):
        limite = time.time() + segundos
        while time.time() < limite and len(falsa.recebido) < quantidade:
            time.sleep(0.02)
        return len(falsa.recebido) >= quantidade

    def test_cerveja_e_porcao_em_duas_impressoras_em_ate_2s(self):
        """Critério de aceite: pedido com cerveja e porção imprime em 2 impressoras em até 2 segundos."""
        inicio = time.time()
        self._sincronizar(self._pedido([self._linha(self.chope, 2, note="sem colarinho"),
                                        self._linha(self.porcao, 1)], mesa=self.mesa1))
        tickets = self.Ticket.search([("order_id.table_id", "=", self.mesa1.id)])
        self.assertEqual(sorted(tickets.mapped("setor_id.codigo")), ["bar", "chapa"])
        # Em produção o envio roda logo após o commit; no teste chamamos direto
        self.Job.search([("estado", "=", "esperando")])._enviar()
        self.assertTrue(self._esperar(self.falsa_bar, 1) and self._esperar(self.falsa_chapa, 1))
        self.assertLess(time.time() - inicio, 2.0)
        bar = self.falsa_bar.recebido[0]
        self.assertIn("Chope 300 ml".encode("cp860"), bar)
        self.assertIn("SEM COLARINHO".encode("cp860"), bar)
        self.assertIn("Mesa 1".encode("cp860"), bar)
        self.assertNotIn("Porção".encode("cp860"), bar)
        self.assertIn("Porção de bolinho".encode("cp860"), self.falsa_chapa.recebido[0])

    def test_impressora_desligada_nao_perde_ticket(self):
        """Critério de aceite: desligar e religar a impressora não perde nenhum ticket (e mantém a ordem)."""
        porta_original = self.imp_chapa.porta
        self.imp_chapa.porta = porta_livre()  # "desligada": ninguém escuta nessa porta
        self._sincronizar(self._pedido([self._linha(self.porcao, 1)], mesa=self.mesa1))
        self._sincronizar(self._pedido([self._linha(self.batata, 1)], mesa=self.mesa2))
        self.Job._cron_reenviar()
        esperando = self.Job.search([("impressora_id", "=", self.imp_chapa.id), ("estado", "=", "esperando")])
        self.assertEqual(len(esperando), 2)
        self.assertEqual(self.imp_chapa.estado, "erro")
        dados = self.Ticket.kds_dados("chapa")
        self.assertTrue(dados["impressoras_paradas"])
        self.assertEqual(dados["tickets_esperando_impressao"], 2)
        # "Religa": volta a escutar
        self.imp_chapa.porta = porta_original
        self.Job._cron_reenviar()
        self.assertTrue(self._esperar(self.falsa_chapa, 2))
        self.assertFalse(self.Job.search([("estado", "=", "esperando")]))
        self.assertEqual(self.imp_chapa.estado, "ok")
        primeiro, segundo = self.falsa_chapa.recebido[:2]
        self.assertIn("Porção de bolinho".encode("cp860"), primeiro)
        self.assertIn("Batata frita".encode("cp860"), segundo)

    def test_pedido_parado_31_min_alerta_gerente(self):
        """Critério de aceite: pedido parado há 31 minutos fica vermelho e gera alerta ao gerente."""
        self._sincronizar(self._pedido([self._linha(self.porcao, 1)], mesa=self.mesa1))
        ticket = self.Ticket.search([("order_id.table_id", "=", self.mesa1.id)])
        ticket.criado_em = fields.Datetime.now() - timedelta(minutes=31)
        dados = self.Ticket.kds_dados("chapa")["tickets"][0]
        self.assertGreaterEqual(dados["segundos"], 31 * 60)  # a tela pinta de vermelho acima de 20 min
        enviados = []
        original = type(self.env["bus.bus"])._sendone

        def espiar(bus, canal, tipo, mensagem):
            enviados.append((canal, tipo, mensagem))
            return original(bus, canal, tipo, mensagem)

        self.patch(type(self.env["bus.bus"]), "_sendone", espiar)
        self.Ticket._cron_alertar_atrasos()
        self.assertTrue(ticket.alerta_enviado)
        alertas = [e for e in enviados if e[1] == "simple_notification"]
        self.assertTrue(alertas)
        self.assertEqual(alertas[0][0], self.env.ref("boteco_base.group_gerente"))
        self.assertIn("Mesa 1", alertas[0][2]["message"])
        # Não repete o alerta
        enviados.clear()
        self.Ticket._cron_alertar_atrasos()
        self.assertFalse([e for e in enviados if e[1] == "simple_notification"])

    def test_fluxo_da_tela(self):
        self._sincronizar(self._pedido([self._linha(self.porcao, 1)], mesa=self.mesa1))
        ticket = self.Ticket.search([("order_id.table_id", "=", self.mesa1.id)])
        self.assertEqual(ticket.estado, "aguardando")
        ticket.with_user(self.garcom).kds_avancar()
        self.assertEqual(ticket.estado, "preparando")
        ticket.kds_voltar()  # desfazer
        self.assertEqual(ticket.estado, "aguardando")
        ticket.kds_avancar()
        ticket.kds_avancar()
        self.assertEqual(ticket.estado, "pronto")
        self.assertTrue(ticket.pronto_em)
        self.assertIn(ticket.id, [t["id"] for t in self.Ticket.kds_prontos_para_entregar()])
        ticket.kds_entregar()
        self.assertEqual(ticket.estado, "entregue")
        status = self.env["pos.order"].boteco_status_itens(ticket.order_id.uuid)
        self.assertEqual(set(status.values()), {"entregue"})
        tempos = self.env["boteco.kds.tempo"].search_read([("product_id", "=", self.porcao.id)], ["minutos_preparo", "hora"])
        self.assertEqual(len(tempos), 1)

    def test_cancelamento_vira_ticket_de_cancelamento(self):
        linha = self._linha(self.porcao, 2)
        dados = self._pedido([linha], mesa=self.mesa1)
        pedido = self._sincronizar(dados)
        menos = dict(linha, qty=1)
        self._sincronizar(dict(dados, lines=[[1, pedido.lines.id, {"qty": 1}]],
                               last_order_preparation_change=self._snapshot_envio([menos])))
        cancel = self.Ticket.search([("order_id", "=", pedido.id), ("tipo", "=", "cancelamento")])
        self.assertEqual(len(cancel), 1)
        self.assertEqual(cancel.item_ids.quantidade, 1)
        self.Job.search([("estado", "=", "esperando")])._enviar()
        self.assertTrue(self._esperar(self.falsa_chapa, 2))
        self.assertIn(b"CANCELAMENTO", self.falsa_chapa.recebido[-1])

    def test_saude_mostra_fila(self):
        nomes = [i["nome"] for i in self.env["boteco.saude"].verificar()["itens"]]
        self.assertIn("Fila de impressão", nomes)
