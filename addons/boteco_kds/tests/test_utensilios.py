from datetime import timedelta

from odoo import fields
from odoo.tests import tagged

from odoo.addons.boteco_cardapio.tests.common_pos import BotecoPosCase


@tagged("post_install", "-at_install", "boteco")
class TestUtensilios(BotecoPosCase):
    """Etapa 15: copos na 1ª cerveja, vinho/taças/água, pratos compartilhados e Hold & Fire."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.ref("boteco_cardapio.happy_hour_padrao").active = False
        Produto = cls.env["product.product"]
        base = {"available_in_pos": True, "taxes_id": [fields.Command.clear()], "type": "consu"}
        cls.chope.write({"boteco_tipo_consumo": "bebida_giro", "boteco_regra_utensilio": "copo_cerveja"})
        cls.porcao.write({"boteco_tipo_consumo": "prato_compartilhado", "boteco_serve_pessoas": 3,
                          "boteco_regra_utensilio": "pratos_compartilhados"})
        cls.batata.write({"boteco_tipo_consumo": "prato_individual"})
        cls.vinho = Produto.create({**base, "name": "Vinho branco", "list_price": 90.0, "boteco_setor_id": cls.setor_bar.id,
                                    "boteco_tipo_consumo": "garrafa", "boteco_regra_utensilio": "taca_vinho_gelo"})
        cls.agua = Produto.create({**base, "name": "Água mineral", "list_price": 5.0, "boteco_setor_id": cls.setor_bar.id,
                                   "boteco_tipo_consumo": "agua"})
        cls.sorvete = Produto.create({**base, "name": "Sorvete", "list_price": 15.0, "boteco_setor_id": cls.setor_chapa.id,
                                      "boteco_tipo_consumo": "sobremesa"})
        cls.Ticket = cls.env["boteco.kds.pedido"]

    def _ticket(self, pedido, setor):
        return self.Ticket.search([("order_id", "=", pedido.id), ("setor_id", "=", setor.id)], order="id desc", limit=1)

    def _mais_uma_rodada(self, dados, enviadas, nova, **extra):
        """Nova rodada na mesma conta, como o PDV faz (snapshot acumulado)."""
        enviadas.append(nova)
        return self._sincronizar(dict(dados, lines=[[0, 0, nova]],
                                      last_order_preparation_change=self._snapshot_envio(enviadas), **extra))

    def test_copos_so_na_primeira_cerveja_e_delta(self):
        primeira = self._linha(self.chope, 2)
        dados = self._pedido([primeira], mesa=self.mesa1, pessoas=2)
        pedido = self._sincronizar(dados)
        self.assertIn("LEVAR 2 COPOS", self._ticket(pedido, self.setor_bar).avisos)
        enviadas = [primeira]
        self._mais_uma_rodada(dados, enviadas, self._linha(self.chope, 2))
        self.assertFalse(self._ticket(pedido, self.setor_bar).avisos)
        # Chegaram mais 2 pessoas
        self.mesa1.boteco_definir_clientes(4)
        self._mais_uma_rodada(dados, enviadas, self._linha(self.chope, 1), customer_count=4)
        self.assertIn("+2 COPOS EXTRAS", self._ticket(pedido, self.setor_bar).avisos)

    def test_copos_desligado_nao_imprime(self):
        self.env.company.boteco_flag_insumo_copos_primeira_cerveja = False
        p1 = self._sincronizar(self._pedido([self._linha(self.chope, 2)], mesa=self.mesa1))
        self.assertFalse(self._ticket(p1, self.setor_bar).avisos)

    def test_vinho_sem_agua_avisa_garcom(self):
        avisos = []
        original = type(self.env["pos.config"])._notify

        def espiar(config, *notificacoes, **kw):
            avisos.append(notificacoes)
            return original(config, *notificacoes, **kw)

        self.patch(type(self.env["pos.config"]), "_notify", espiar)
        self._abrir_sessao()
        p1 = self._sincronizar(self._pedido([self._linha(self.vinho, 1)], mesa=self.mesa1, pessoas=3))
        texto = self._ticket(p1, self.setor_bar).avisos
        self.assertIn("3 TAÇAS", texto)
        self.assertIn("BALDE COM GELO", texto)
        self.assertTrue(any(n[0] == "BOTECO_ALERTA" and "sem água" in n[1]["mensagem"] for n in avisos))
        # Com água na mesa não avisa mais
        avisos.clear()
        self._sincronizar(self._pedido([self._linha(self.agua, 1), self._linha(self.vinho, 1)], mesa=self.mesa2))
        self.assertFalse(any(n[0] == "BOTECO_ALERTA" for n in avisos))

    def test_pratos_compartilhados(self):
        p1 = self._sincronizar(self._pedido([self._linha(self.porcao, 1)], mesa=self.mesa1, pessoas=3))
        self.assertIn("3 PRATOS RASOS", self._ticket(p1, self.setor_chapa).avisos)

    def test_hold_fire_sobremesa(self):
        pedido = self._sincronizar(self._pedido([self._linha(self.batata, 2), self._linha(self.sorvete, 2)],
                                                mesa=self.mesa1))
        tickets = self.Ticket.search([("order_id", "=", pedido.id)])
        sobremesa = tickets.filtered("segundo_tempo")
        prato = tickets - sobremesa
        self.assertEqual(sobremesa.item_ids.product_id, self.sorvete)
        self.assertIn("2º TEMPO", sobremesa.avisos)
        self.assertEqual(prato.item_ids.product_id, self.batata)
        self.assertFalse(sobremesa.segundo_tempo_liberado)
        prato.kds_avancar()  # preparando
        prato.kds_avancar()  # pronto
        self.assertTrue(sobremesa.segundo_tempo_liberado)

    def test_pacing_entre_pracas(self):
        """Etapa 21: o prato rápido (bar, 5 min) começa 10 min depois do demorado (chapa, 15 min)."""
        self.env.company.boteco_flag_kds_totalizador_pacing = True
        self.batata.write({"boteco_setor_id": self.setor_bar.id, "boteco_tempo_preparo": 5})
        pedido = self._sincronizar(self._pedido([self._linha(self.batata, 1), self._linha(self.porcao, 1)],
                                                mesa=self.mesa1))
        rapido = self._ticket(pedido, self.setor_bar)
        demorado = self._ticket(pedido, self.setor_chapa)
        self.assertFalse(demorado.iniciar_apos)
        self.assertEqual(rapido.iniciar_apos, rapido.criado_em + timedelta(minutes=10))
        self.assertIn("PACING", rapido.avisos)
        self.assertTrue(self.Ticket.kds_dados("bar")["avancado"])

    def test_pacing_desligado(self):
        self.batata.write({"boteco_setor_id": self.setor_bar.id, "boteco_tempo_preparo": 5})
        pedido = self._sincronizar(self._pedido([self._linha(self.batata, 1), self._linha(self.porcao, 1)],
                                                mesa=self.mesa1))
        self.assertFalse(self._ticket(pedido, self.setor_bar).iniciar_apos)
        self.assertFalse(self.Ticket.kds_dados("bar")["avancado"])

    def test_hold_fire_desligado(self):
        self.env.company.boteco_flag_hold_fire_sobremesa_2_tempo = False
        pedido = self._sincronizar(self._pedido([self._linha(self.batata, 1), self._linha(self.sorvete, 1)],
                                                mesa=self.mesa1))
        self.assertFalse(self.Ticket.search([("order_id", "=", pedido.id)]).filtered("segundo_tempo"))
