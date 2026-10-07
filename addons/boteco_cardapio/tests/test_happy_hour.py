from datetime import datetime

from freezegun import freeze_time

from odoo.tests import tagged

from .common_pos import BotecoPosCase

# 07/10/2026 é uma quarta-feira. Brasília = UTC-3.
QUARTA_20H59 = datetime(2026, 10, 7, 23, 59, 0)   # 20:59 em Brasília
QUARTA_21H00 = datetime(2026, 10, 8, 0, 0, 0)     # 21:00 em Brasília
SEGUNDA_18H = datetime(2026, 10, 5, 21, 0, 0)     # segunda 18:00 (sem happy hour)


@tagged("post_install", "-at_install", "boteco")
class TestHappyHour(BotecoPosCase):
    def setUp(self):
        super().setUp()
        self.HH = self.env["boteco.happy.hour"]
        self.padrao = self.env.ref("boteco_cardapio.happy_hour_padrao")

    def test_padrao_quarta_a_domingo_17_as_21(self):
        self.assertTrue(self.padrao.qua and self.padrao.dom and not self.padrao.seg and not self.padrao.ter)
        self.assertEqual((self.padrao.hora_inicio, self.padrao.hora_fim), (17.0, 21.0))

    def test_20h59_happy_21h00_normal(self):
        """Critério de aceite: às 20h59 preço de happy hour; às 21h00 preço normal."""
        self.assertTrue(self.HH._ativo_em(QUARTA_20H59))
        self.assertFalse(self.HH._ativo_em(QUARTA_21H00))
        self.assertFalse(self.HH._ativo_em(SEGUNDA_18H))
        self.assertEqual(self.chope._boteco_preco_promocional(QUARTA_20H59)[:2], (7.0, "happy"))
        self.assertIsNone(self.chope._boteco_preco_promocional(QUARTA_21H00))

    def test_proxima_troca_exata(self):
        """A tela agenda a troca para a hora exata (é isso que troca o preço sem recarregar)."""
        self.assertEqual(self.HH._proxima_troca(QUARTA_20H59), QUARTA_21H00)
        # Depois das 21h, a próxima troca é quinta 17h (20:00 UTC)
        self.assertEqual(self.HH._proxima_troca(QUARTA_21H00), datetime(2026, 10, 8, 20, 0, 0))

    def test_virada_de_meia_noite(self):
        self.padrao.write({"hora_inicio": 22.0, "hora_fim": 1.0})
        # quarta 23:30 Brasília = quinta 02:30 UTC
        self.assertTrue(self.HH._ativo_em(datetime(2026, 10, 8, 2, 30)))
        # quinta 00:30 Brasília (janela que começou na quarta)
        self.assertTrue(self.HH._ativo_em(datetime(2026, 10, 8, 3, 30)))
        # quinta 01:30 Brasília
        self.assertFalse(self.HH._ativo_em(datetime(2026, 10, 8, 4, 30)))

    def test_estado_para_o_tablet(self):
        with freeze_time(QUARTA_20H59):
            estado = self.config.boteco_estado_cardapio()
        self.assertTrue(estado["happy_ativo"])
        self.assertEqual(estado["proxima_troca"] - estado["agora"], 60 * 1000)

    def test_autoatendimento_recalcula_com_happy_e_trava_o_preco(self):
        """Pedido do QR às 20h59 sai a R$ 7; mesmo recalculado depois das 21h, continua R$ 7."""
        with freeze_time(QUARTA_20H59):
            pedido = self._sincronizar(self._pedido([self._linha(self.chope, 2, preco=10.0)], mesa=self.mesa1))
            pedido.recompute_prices()
            self.assertEqual(pedido.lines.price_unit, 7.0)
            self.assertEqual(pedido.lines.boteco_preco_origem, "happy")
            self.assertEqual(pedido.amount_total, 14.0)
        with freeze_time(QUARTA_21H00):
            pedido.recompute_prices()
            self.assertEqual(pedido.lines.price_unit, 7.0)
            novo = self.env["pos.order.line"].create({
                "order_id": pedido.id, "product_id": self.chope.id, "qty": 1, "price_unit": 10.0,
                "price_subtotal": 10.0, "price_subtotal_incl": 10.0,
            })
            pedido.recompute_prices()
            self.assertEqual(novo.price_unit, 10.0)
            self.assertEqual(pedido.amount_total, 24.0)
