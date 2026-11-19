import json
import time
import uuid
from unittest.mock import patch

from odoo.tests import HttpCase, tagged

from odoo.addons.boteco_cardapio.tests.common_pos import BotecoPosCase


@tagged("post_install", "-at_install", "boteco")
class TestQrMesa(HttpCase, BotecoPosCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.ref("boteco_cardapio.happy_hour_padrao").active = False
        cls.env.company.boteco_rede_clientes = False
        cls.config.boteco_limite_qr = 300

    def setUp(self):
        super().setUp()
        self.sessao = self._abrir_sessao()
        self.token = self.config.access_token
        self.mesa = self.mesa1

    # ------------------------------------------------------------------ helpers
    def _post(self, rota, dados):
        resposta = self.url_open(rota, data=json.dumps(dados), headers={"Content-Type": "application/json"})
        return resposta.json()

    def _rpc(self, rota, params):
        resposta = self._post(rota, {"jsonrpc": "2.0", "method": "call", "params": params})
        return resposta.get("result", resposta.get("error"))

    def _entrar(self, mesa=None, tablet=None):
        return self._post("/boteco/mesa/entrar", {"access_token": self.token,
                                                  "table_identifier": (mesa or self.mesa).identifier,
                                                  "tablet_token": tablet})

    def _pedir(self, produto, qtd, mesa=None, preco=None):
        linha_uuid = str(uuid.uuid4())
        pedido = {
            "uuid": str(uuid.uuid4()), "access_token": str(uuid.uuid4()), "state": "draft", "customer_count": 1,
            "last_order_preparation_change": "{}",
            "lines": [[0, 0, {
                "product_id": produto.id, "qty": qtd, "price_unit": preco or produto.lst_price,
                "price_subtotal": (preco or produto.lst_price) * qtd, "price_subtotal_incl": (preco or produto.lst_price) * qtd,
                "uuid": linha_uuid, "full_product_name": produto.name, "price_type": "original", "attribute_value_ids": [],
            }]],
        }
        return self._rpc("/pos-self-order/process-order/mobile/", {
            "order": pedido, "access_token": self.token, "table_identifier": (mesa or self.mesa).identifier,
        })

    def _liberar_celular(self):
        dados = self._entrar()
        self._rpc("/boteco/mesa/solicitar", {"access_token": self.token, "table_identifier": self.mesa.identifier})
        dispositivo = self.env["boteco.dispositivo"].browse(dados["id"])
        dispositivo.with_user(self.garcom).boteco_aprovar()
        return dispositivo

    # ------------------------------------------------------------------ testes
    def test_celular_fora_da_rede_nao_pede(self):
        """Critério de aceite: celular fora da rede do bar não consegue pedir."""
        self.env.company.boteco_rede_clientes = "192.168.20.0/24"  # o teste vem de 127.0.0.1
        self.assertEqual(self._entrar()["estado"], "fora_da_rede")
        erro = self._pedir(self.refri, 1)
        self.assertIn("Wi-Fi do bar", json.dumps(erro, ensure_ascii=False))
        self.assertFalse(self.env["pos.order"].search([("table_id", "=", self.mesa.id)]))

    def test_foto_antiga_do_qr_nao_pede(self):
        """Critério de aceite: celular com foto antiga do QR (sessão anterior da mesa) não pede."""
        dispositivo = self._liberar_celular()
        self.assertEqual(self._entrar()["estado"], "aprovado")
        pedido = self._pedir(self.refri, 1)
        self.assertIn("pos.order", pedido)
        # A conta fecha: a sessão da mesa acaba
        self.mesa._boteco_limpar_chamados()
        self.env["pos.order"].search([("table_id", "=", self.mesa.id)]).write({"state": "cancel"})
        self.mesa._boteco_encerrar_sessao()
        self.assertFalse(self.mesa.boteco_codigo_sessao)
        self.assertFalse(dispositivo.active)
        # Mesmo celular (mesmo cookie) volta outro dia: precisa de nova liberação
        self.assertEqual(self._entrar()["estado"], "pendente")
        erro = self._pedir(self.refri, 1)
        self.assertIn("ainda não liberou", json.dumps(erro, ensure_ascii=False))

    def test_primeiro_pedido_precisa_do_garcom_e_vai_para_producao(self):
        self.assertEqual(self._entrar()["estado"], "pendente")
        self.assertIn("ainda não liberou", json.dumps(self._pedir(self.batata, 1), ensure_ascii=False))
        self._liberar_celular()
        resultado = self._pedir(self.batata, 1)
        pedido = self.env["pos.order"].browse(resultado["pos.order"][0]["id"])
        self.assertEqual(pedido.boteco_origem, "qr")
        ticket = self.env["boteco.kds.pedido"].search([("order_id", "=", pedido.id)])
        self.assertEqual(ticket.setor_id.codigo, "chapa")
        self.assertTrue(self.mesa.boteco_codigo_sessao)
        self.assertTrue(self.env["boteco.auditoria"].search([("acao", "=", "aprovacao_qr"), ("res_id", "=", self.mesa.id)]))

    def test_alcool_espera_o_garcom_conferir_idade(self):
        self._liberar_celular()
        resultado = self._pedir(self.chope, 2)
        pedido = self.env["pos.order"].browse(resultado["pos.order"][0]["id"])
        self.assertTrue(pedido.boteco_aguardando_garcom)
        self.assertFalse(self.env["boteco.kds.pedido"].search([("order_id", "=", pedido.id)]))
        self.mesa.with_user(self.garcom).boteco_confirmar_maior18()
        self.assertFalse(pedido.boteco_aguardando_garcom)
        self.assertTrue(self.env["boteco.kds.pedido"].search([("order_id", "=", pedido.id)]))
        # Segunda rodada de chope não espera mais
        resultado2 = self._pedir(self.chope, 1)
        self.assertFalse(self.env["pos.order"].browse(resultado2["pos.order"][0]["id"]).boteco_aguardando_garcom)

    def test_pedir_a_conta_deixa_a_mesa_roxa_em_ate_2s(self):
        """Critério de aceite: 'Pedir a conta' muda a mesa para roxo no mapa e avisa o garçom em até 2 s."""
        self._liberar_celular()
        avisos = []
        original = type(self.env["pos.config"])._notify

        def espiar(config, *notificacoes, **kw):
            avisos.append(notificacoes)
            return original(config, *notificacoes, **kw)

        self.patch(type(self.env["pos.config"]), "_notify", espiar)
        inicio = time.time()
        resposta = self._rpc("/boteco/mesa/chamar", {"access_token": self.token, "table_identifier": self.mesa.identifier,
                                                    "tipo": "conta"})
        self.assertTrue(resposta["ok"])
        self.assertLess(time.time() - inicio, 2.0)
        self.assertTrue(self.mesa.boteco_pediu_conta)  # o mapa pinta de roxo (status "conta")
        self.assertTrue(any(n[0] == "BOTECO_MESA" and n[1]["evento"] == "pediu_conta" for n in avisos))

    def test_limite_de_valor_por_pedido_no_qr(self):
        self._liberar_celular()
        erro = self._pedir(self.porcao, 10)  # R$ 420
        self.assertIn("chame o garçom", json.dumps(erro, ensure_ascii=False))
        self.assertIn("pos.order", self._pedir(self.porcao, 2))

    def test_tablet_da_mesa_ja_vem_liberado_e_sai_com_pin(self):
        tablet = self.env["boteco.dispositivo"].create({"tipo": "tablet", "mesa_id": self.mesa2.id, "estado": "aprovado"})
        self.assertEqual(self._entrar(self.mesa2, tablet.token)["estado"], "aprovado")
        resultado = self._pedir(self.refri, 1, mesa=self.mesa2)
        pedido = self.env["pos.order"].browse(resultado["pos.order"][0]["id"])
        self.assertEqual(pedido.boteco_origem, "tablet")
        saida = self._rpc("/boteco/mesa/sair_quiosque", {"access_token": self.token,
                                                         "table_identifier": self.mesa2.identifier, "pin": "2580"})
        self.assertFalse(saida["ok"])  # garçom não tira do quiosque
        saida = self._rpc("/boteco/mesa/sair_quiosque", {"access_token": self.token,
                                                         "table_identifier": self.mesa2.identifier, "pin": "7314"})
        self.assertTrue(saida["ok"])

    def test_minha_conta_e_pedir_de_novo(self):
        self._liberar_celular()
        self._pedir(self.refri, 2)
        status = self._rpc("/boteco/mesa/status", {"access_token": self.token, "table_identifier": self.mesa.identifier})
        self.assertEqual(status["estado"], "aprovado")
        self.assertEqual(status["conta"]["itens"][0]["status"], "na fila")
        self.assertAlmostEqual(status["conta"]["consumo"], 14.0)
        self.assertAlmostEqual(status["conta"]["taxa"], 1.4)
        self.assertEqual(status["pedir_de_novo"][0]["product_id"], self.refri.id)

    # ------------------------------------------------------------------ happy hour na virada (auditoria, risco 1)
    def _happy_acabou_ha_pouco(self):
        """Simula: happy hour ativo alguns minutos atrás e já encerrado agora."""
        from odoo.addons.boteco_cardapio.models.boteco_happy_hour import BotecoHappyHour
        return patch.object(BotecoHappyHour, "_ativo_em", lambda self, momento=None, company=None: momento is not None)

    def _preco_cobrado(self, resultado):
        pedidos = self.env["pos.order"].browse([p["id"] for p in resultado["pos.order"]])
        linha = pedidos.lines.sorted("id")[-1:]  # a linha recém-enviada
        return linha.price_unit, linha.boteco_preco_origem

    def test_happy_hour_na_tolerancia_vale_o_preco_do_carrinho(self):
        self._liberar_celular()
        self.mesa.with_user(self.garcom).boteco_confirmar_maior18()
        self.env.company.boteco_happy_tolerancia_min = 5
        with self._happy_acabou_ha_pouco():
            # Carrinho mostrava R$ 7 (happy) e o envio chegou 1 min depois do fim
            self.assertEqual(self._preco_cobrado(self._pedir(self.chope, 1, preco=7.0)), (7.0, "happy"))
            # Carrinho já estava no preço cheio: continua cheio
            self.assertEqual(self._preco_cobrado(self._pedir(self.chope, 1, preco=10.0))[0], 10.0)

    def test_happy_hour_sem_tolerancia_cobra_o_preco_da_hora(self):
        self._liberar_celular()
        self.mesa.with_user(self.garcom).boteco_confirmar_maior18()
        self.env.company.boteco_happy_tolerancia_min = 0
        self.env.flush_all()
        with self._happy_acabou_ha_pouco():
            self.assertEqual(self._preco_cobrado(self._pedir(self.chope, 1, preco=7.0))[0], 10.0)

    def test_estado_do_cardapio_informa_a_tolerancia(self):
        self.env.company.boteco_happy_tolerancia_min = 7
        self.assertEqual(self.config.boteco_estado_cardapio()["happy_tolerancia_min"], 7)
