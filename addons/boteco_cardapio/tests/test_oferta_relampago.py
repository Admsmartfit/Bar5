from odoo.exceptions import UserError
from odoo.tests import tagged

from .common_pos import BotecoPosCase


@tagged("post_install", "-at_install", "boteco")
class TestOfertaRelampago(BotecoPosCase):
    def setUp(self):
        super().setUp()
        # Sem happy hour para não interferir
        self.env.ref("boteco_cardapio.happy_hour_padrao").active = False
        self.oferta = self.env["boteco.oferta.relampago"].create(
            {"name": "Batata relâmpago", "product_id": self.batata.id, "preco": 19.9, "limite": 20, "duracao_min": 30}
        )

    def test_lancar_agora_coloca_no_topo(self):
        self.oferta.action_lancar_agora()
        self.assertEqual(self.oferta.estado, "ativa")
        estado = self.config.boteco_estado_cardapio()
        self.assertEqual([o["id"] for o in estado["ofertas"]], [self.oferta.id])
        self.assertEqual(self.batata._boteco_preco_promocional()[:2], (19.9, "oferta"))

    def test_some_ao_vender_a_vigesima(self):
        """Critério de aceite: oferta de 20 unidades some do tablet ao vender a 20ª."""
        self.oferta.action_lancar_agora()
        self._sincronizar(self._pedido([self._linha(self.batata, 12, preco=19.9)], mesa=self.mesa1))
        self.assertEqual(self.oferta.restante, 8)
        self.assertEqual(self.oferta.estado, "ativa")
        self._sincronizar(self._pedido([self._linha(self.batata, 7, preco=19.9)], mesa=self.mesa2))
        self.assertEqual(self.oferta.restante, 1)
        self.assertTrue(self.config.boteco_estado_cardapio()["ofertas"])
        self._sincronizar(self._pedido([self._linha(self.batata, 1, preco=19.9)], mesa=self.mesas[2]))
        self.assertEqual(self.oferta.vendidos, 20)
        self.assertEqual(self.oferta.estado, "esgotada")
        self.assertFalse(self.config.boteco_estado_cardapio()["ofertas"])
        # Depois de esgotar, o preço volta ao normal
        self.assertIsNone(self.batata._boteco_preco_promocional())

    def test_preco_digitado_pelo_caixa_nao_conta_como_oferta(self):
        self.oferta.action_lancar_agora()
        self._sincronizar(self._pedido([self._linha(self.batata, 3, preco=30.0)], mesa=self.mesa1))
        self.assertEqual(self.oferta.vendidos, 0)

    def test_nao_lanca_duas_ofertas_do_mesmo_produto(self):
        self.oferta.action_lancar_agora()
        outra = self.oferta.copy({"name": "Outra"})
        with self.assertRaises(UserError):
            outra.action_lancar_agora()

    def test_cron_encerra_vencida(self):
        self.oferta.action_lancar_agora()
        self.oferta.fim = self.oferta.inicio
        self.env["boteco.oferta.relampago"]._cron_encerrar_vencidas()
        self.assertEqual(self.oferta.estado, "encerrada")
