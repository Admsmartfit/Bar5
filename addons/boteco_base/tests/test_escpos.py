import socket
import threading

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

from ..tools import escpos
from ..tools.rede import ip_na_rede


class ImpressoraFalsa:
    """Servidor TCP que finge ser uma impressora 9100 e guarda o que recebeu."""

    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(5)
        self.porta = self.sock.getsockname()[1]
        self.recebido = []
        self._thread = threading.Thread(target=self._rodar, daemon=True)
        self._thread.start()

    def _rodar(self):
        while True:
            try:
                conn, _addr = self.sock.accept()
            except OSError:
                return
            with conn:
                dados = b""
                while True:
                    parte = conn.recv(65536)
                    if not parte:
                        break
                    dados += parte
                if dados:
                    self.recebido.append(dados)

    def fechar(self):
        self.sock.close()


@tagged("post_install", "-at_install", "boteco")
class TestEscpos(TransactionCase):
    def test_ticket_com_acentos_e_qr(self):
        t = escpos.Ticket(colunas=48)
        t.titulo("MESA 12").texto("Pão de queijo · ação 🍺").qrcode("LOTE-123").corte()
        dados = t.bytes()
        self.assertTrue(dados.startswith(b"\x1b@"))
        self.assertIn("Pão".encode("cp860"), dados)
        self.assertIn(b"LOTE-123", dados)
        self.assertIn(b"\x1dV", dados)

    def test_quebra_de_linha(self):
        partes = escpos.Ticket._quebrar("porção de bolinho de bacalhau sem cebola", 12)
        self.assertTrue(all(len(p) <= 12 for p in partes))

    def test_imprimir_teste_numa_impressora_de_rede(self):
        """Critério de aceite: botão 'Imprimir teste' imprime na térmica pela rede (simulada)."""
        falsa = ImpressoraFalsa()
        try:
            impressora = self.env["boteco.impressora"].create(
                {"name": "Chapa", "ip": "127.0.0.1", "porta": falsa.porta}
            )
            impressora.action_imprimir_teste()
            for _i in range(50):
                if falsa.recebido:
                    break
                threading.Event().wait(0.05)
            self.assertTrue(falsa.recebido)
            self.assertIn("TESTE DE IMPRESSÃO".encode("cp860"), falsa.recebido[0])
            self.assertEqual(impressora.estado, "ok")
        finally:
            falsa.fechar()

    def test_impressora_desligada_da_mensagem_clara(self):
        impressora = self.env["boteco.impressora"].create({"name": "Bar", "ip": "127.0.0.1", "porta": 9})
        with self.assertRaisesRegex(UserError, "Tentar de novo"):
            impressora.action_imprimir_teste()
        self.assertFalse(impressora.enviar_bytes(b"x", levantar=False))
        self.assertEqual(impressora.estado, "erro")

    def test_rede(self):
        self.assertTrue(ip_na_rede("192.168.20.15", "192.168.20.0/24"))
        self.assertFalse(ip_na_rede("8.8.8.8", "192.168.20.0/24, 10.0.0.0/8"))
        self.assertTrue(ip_na_rede("8.8.8.8", ""))
        self.assertFalse(ip_na_rede("lixo", "192.168.20.0/24"))
