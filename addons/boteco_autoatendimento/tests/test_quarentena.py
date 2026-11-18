import json
import uuid

from odoo.exceptions import UserError
from odoo.tests import BaseCase, HttpCase, tagged

from odoo.addons.boteco_autoatendimento.models import quarentena
from odoo.addons.boteco_cardapio.tests.common_pos import BotecoPosCase


def item(tipo, qtd, serve=1, max_rodada=0, nome="Item", valor=0.0):
    return {"produto_id": 1, "nome": nome, "tipo": tipo, "serve": serve, "max_rodada": max_rodada,
            "qtd": qtd, "valor": valor}


@tagged("post_install", "-at_install", "boteco")
class TestRegrasQuarentena(BaseCase):
    """Regras N+X isoladas (sem banco)."""

    def test_limites(self):
        self.assertEqual(quarentena.limite_rodada_pratos(2), 3)
        self.assertEqual(quarentena.limite_rodada_pratos(8), 10)
        self.assertEqual(quarentena.limite_saturacao_45min(2), 4)
        self.assertEqual(quarentena.limite_bebida_giro(1), 4)
        self.assertEqual(quarentena.limite_bebida_giro(4), 10)
        self.assertEqual(quarentena.limite_garrafas(3), 2)

    def test_dez_pratos_para_dois_retem(self):
        self.assertTrue(quarentena.avaliar_regras_volume([item("prato_individual", 10)], 2))

    def test_pedido_normal_passa(self):
        itens = [item("prato_individual", 2), item("bebida_giro", 4), item("prato_compartilhado", 1, serve=2)]
        self.assertEqual(quarentena.avaliar_regras_volume(itens, 4), [])

    def test_compartilhado_conta_rendimento(self):
        # 2 tábuas para 3 pessoas cada = 6 pratos para 2 clientes
        self.assertTrue(quarentena.avaliar_regras_volume([item("prato_compartilhado", 2, serve=3)], 2))

    def test_saturacao_45_min(self):
        self.assertEqual(quarentena.avaliar_regras_volume([item("prato_individual", 2)], 2, pratos_45min=0), [])
        self.assertTrue(quarentena.avaliar_regras_volume([item("prato_individual", 2)], 2, pratos_45min=3))

    def test_repeticao_mesmo_sku(self):
        self.assertTrue(quarentena.avaliar_regras_volume([item("sobremesa", 4)], 3))
        self.assertTrue(quarentena.avaliar_regras_volume([item("sobremesa", 3)], 5, ) == [])
        self.assertTrue(quarentena.avaliar_regras_volume([item("sobremesa", 3, max_rodada=2)], 5))

    def test_garrafas(self):
        self.assertEqual(quarentena.avaliar_regras_volume([item("garrafa", 1)], 2), [])
        self.assertTrue(quarentena.avaliar_regras_volume([item("garrafa", 2)], 2))

    def test_zscore(self):
        historico = [50.0, 60.0, 55.0, 45.0, 52.0] * 5
        self.assertIsNone(quarentena.avaliar_ticket(100.0, 2, historico))
        self.assertTrue(quarentena.avaliar_ticket(400.0, 2, historico))
        self.assertIsNone(quarentena.avaliar_ticket(10000.0, 2, historico[:5]))  # histórico curto: não age


@tagged("post_install", "-at_install", "boteco")
class TestQuarentenaTablet(HttpCase, BotecoPosCase):
    """Fluxo completo: tablet/QR -> retém -> garçom resolve -> produção."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.ref("boteco_cardapio.happy_hour_padrao").active = False
        cls.env.company.boteco_rede_clientes = False
        cls.config.boteco_limite_qr = 0
        cls.batata.write({"boteco_tipo_consumo": "prato_individual"})
        cls.refri.write({"boteco_tipo_consumo": "bebida_giro"})

    def setUp(self):
        super().setUp()
        self.sessao = self._abrir_sessao()
        self.token = self.config.access_token
        self.mesa = self.mesa1
        self._liberar_celular()
        self.mesa.boteco_definir_clientes(2)

    def _post(self, rota, dados):
        return self.url_open(rota, data=json.dumps(dados), headers={"Content-Type": "application/json"}).json()

    def _rpc(self, rota, params):
        resposta = self._post(rota, {"jsonrpc": "2.0", "method": "call", "params": params})
        return resposta.get("result", resposta.get("error"))

    def _liberar_celular(self):
        dados = self._post("/boteco/mesa/entrar", {"access_token": self.token, "table_identifier": self.mesa.identifier})
        self._rpc("/boteco/mesa/solicitar", {"access_token": self.token, "table_identifier": self.mesa.identifier})
        self.env["boteco.dispositivo"].browse(dados["id"]).with_user(self.garcom).boteco_aprovar()

    def _pedir(self, produto, qtd):
        pedido = {
            "uuid": str(uuid.uuid4()), "access_token": str(uuid.uuid4()), "state": "draft", "customer_count": 1,
            "last_order_preparation_change": "{}",
            "lines": [[0, 0, {
                "product_id": produto.id, "qty": qtd, "price_unit": produto.lst_price,
                "price_subtotal": produto.lst_price * qtd, "price_subtotal_incl": produto.lst_price * qtd,
                "uuid": str(uuid.uuid4()), "full_product_name": produto.name, "price_type": "original",
                "attribute_value_ids": [],
            }]],
        }
        resultado = self._rpc("/pos-self-order/process-order/mobile/", {
            "order": pedido, "access_token": self.token, "table_identifier": self.mesa.identifier})
        return self.env["pos.order"].browse(resultado["pos.order"][0]["id"])

    def _tickets(self, pedido):
        return self.env["boteco.kds.pedido"].search([("order_id", "=", pedido.id)])

    def test_pedido_normal_vai_direto(self):
        pedido = self._pedir(self.batata, 2)
        self.assertFalse(pedido.boteco_status_aprovacao)
        self.assertTrue(self._tickets(pedido))

    def test_dez_pratos_para_dois_fica_retido_e_nao_imprime(self):
        pedido = self._pedir(self.batata, 10)
        self.assertEqual(pedido.boteco_status_aprovacao, "aguardando")
        self.assertIn("Pratos", pedido.boteco_motivos_retencao)
        self.assertFalse(self._tickets(pedido))
        # Mesmo que um PDV tente mandar à produção, o servidor segura
        pedido.boteco_marcar_enviado()
        self.assertFalse(self._tickets(pedido))
        self.assertIn(self.batata.id, [i["produto_id"] for i in
                                       self.env["pos.order"].with_user(self.garcom).boteco_pedidos_retidos()[0]["itens"]])

    def test_ajustar_clientes_e_liberar(self):
        pedido = self._pedir(self.batata, 10)
        pedido.with_user(self.garcom).action_boteco_ajustar_clientes_e_aprovar(10)
        self.assertEqual(pedido.boteco_status_aprovacao, "aprovado")
        self.assertEqual(self.mesa.boteco_clientes_atuais, 10)
        self.assertEqual(self._tickets(pedido).item_ids.quantidade, 10)
        # Segundo garçom tocando depois: já resolvido
        with self.assertRaises(UserError):
            pedido.with_user(self.caixa).action_boteco_aprovar_pedido()

    def test_corrigir_item_de_10_para_1(self):
        pedido = self._pedir(self.batata, 10)
        linha = pedido.lines
        pedido.with_user(self.garcom).action_boteco_corrigir_item_e_aprovar({str(linha.id): 1})
        self.assertEqual(linha.qty, 1)
        self.assertAlmostEqual(pedido.amount_total, 30.0)
        self.assertEqual(self._tickets(pedido).item_ids.quantidade, 1)

    def test_recusar(self):
        pedido = self._pedir(self.batata, 10)
        pedido.with_user(self.garcom).action_boteco_rejeitar_pedido()
        self.assertEqual(pedido.boteco_status_aprovacao, "rejeitado")
        self.assertEqual(pedido.state, "cancel")
        self.assertFalse(self._tickets(pedido))

    def test_flag_desligada_nao_retem(self):
        self.env.company.boteco_flag_quarentena_pedidos_anomalos = False
        pedido = self._pedir(self.batata, 10)
        self.assertFalse(pedido.boteco_status_aprovacao)
        self.assertTrue(self._tickets(pedido))

    def test_item_sem_classificacao_nao_entra_na_regra(self):
        pedido = self._pedir(self.porcao, 10)
        self.assertFalse(pedido.boteco_status_aprovacao)
