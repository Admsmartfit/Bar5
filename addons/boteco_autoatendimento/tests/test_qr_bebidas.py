import json
import uuid

from odoo import fields
from odoo.tests import HttpCase, tagged

from odoo.addons.boteco_cardapio.tests.common_pos import BotecoPosCase


@tagged("post_install", "-at_install", "boteco")
class TestQrBebidas(HttpCase, BotecoPosCase):
    """Etapa 36: QR expresso de bebidas (sem liberação do garçom, só bebidas, teto só para preparadas)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.ref("boteco_cardapio.happy_hour_padrao").active = False
        company = cls.env.company
        company.write({"boteco_rede_clientes": False, "boteco_flag_qr_bebidas": True,
                       "boteco_teto_bebidas_preparadas": 4})
        cls.config.boteco_limite_qr = 50  # o limite de valor do QR comum não vale para o QR de bebidas
        cls.refri.write({"boteco_tipo_consumo": "bebida_giro", "self_order_available": True})
        cls.chope.write({"boteco_bebida_preparada": True, "self_order_available": True})
        cls.caipirinha = cls.env["product.product"].create({
            "name": "Caipirinha de limão", "list_price": 22.0, "available_in_pos": True, "type": "consu",
            "taxes_id": [fields.Command.clear()], "boteco_setor_id": cls.setor_bar.id, "boteco_maior_18": True,
            "boteco_bebida_preparada": True, "self_order_available": True,
        })

    def setUp(self):
        super().setUp()
        self.sessao = self._abrir_sessao()
        self.token = self.config.access_token
        self.mesa = self.mesa1
        self.mesa._boteco_garantir_sessao()  # garçom abriu a mesa
        self.opener.cookies.set("boteco_modo", "bebidas", path="/")

    # ------------------------------------------------------------------ helpers
    def _post(self, rota, dados):
        self.env.flush_all()  # o pedido chega por HTTP: o que o teste mudou precisa estar gravado
        return self.url_open(rota, data=json.dumps(dados), headers={"Content-Type": "application/json"}).json()

    def _rpc(self, rota, params):
        resposta = self._post(rota, {"jsonrpc": "2.0", "method": "call", "params": params})
        return resposta.get("result", resposta.get("error"))

    def _entrar(self, mesa=None):
        return self._post("/boteco/mesa/entrar", {"access_token": self.token,
                                                  "table_identifier": (mesa or self.mesa).identifier})

    def _pedir(self, itens, mesa=None):
        linhas = [[0, 0, {
            "product_id": p.id, "qty": q, "price_unit": p.lst_price, "price_subtotal": p.lst_price * q,
            "price_subtotal_incl": p.lst_price * q, "uuid": str(uuid.uuid4()), "full_product_name": p.name,
            "price_type": "original", "attribute_value_ids": [],
        }] for p, q in itens]
        pedido = {"uuid": str(uuid.uuid4()), "access_token": str(uuid.uuid4()), "state": "draft",
                  "customer_count": 1, "last_order_preparation_change": "{}", "lines": linhas}
        return self._rpc("/pos-self-order/process-order/mobile/", {
            "order": pedido, "access_token": self.token, "table_identifier": (mesa or self.mesa).identifier})

    def _pedido(self, resultado):
        self.assertIn("pos.order", resultado, resultado)
        return self.env["pos.order"].browse(resultado["pos.order"][0]["id"])

    def _enviado(self, pedido):
        itens = self.env["boteco.kds.pedido"].search([("order_id", "=", pedido.id)]).item_ids
        return {i.product_id: sum(itens.filtered(lambda x: x.product_id == i.product_id).mapped("quantidade"))
                for i in itens}

    def _idade_ok(self):
        self.mesa.with_user(self.garcom).boteco_confirmar_maior18()

    # ------------------------------------------------------------------ testes
    def test_fechadas_saem_sem_garcom_e_sem_teto(self):
        dados = self._entrar()
        self.assertEqual(dados["estado"], "pendente")
        pedido = self._pedido(self._pedir([(self.refri, 12)]))  # 12 latas: acima do limite de R$ 50 e sem teto
        self.assertEqual(pedido.boteco_origem, "qr_bebidas")
        self.assertFalse(pedido.boteco_status_aprovacao)
        self.assertEqual(self._enviado(pedido), {self.refri: 12})

    def test_mesa_fechada_nao_pede(self):
        self._entrar(self.mesa2)
        erro = self._pedir([(self.refri, 1)], mesa=self.mesa2)
        self.assertIn("abrir a mesa", json.dumps(erro, ensure_ascii=False))

    def test_comida_pelo_qr_de_bebidas_bloqueada(self):
        self._entrar()
        erro = self._pedir([(self.refri, 1), (self.batata, 1)])
        self.assertIn("só bebidas", json.dumps(erro, ensure_ascii=False))

    def test_preparadas_acima_do_teto_esperam_o_garcom_e_fechadas_saem(self):
        self._entrar()
        self._idade_ok()
        pedido = self._pedido(self._pedir([(self.caipirinha, 6), (self.refri, 2)]))
        self.assertEqual(pedido.boteco_status_aprovacao, "aguardando")
        self.assertIn("teto", pedido.boteco_motivos_retencao)
        self.assertEqual(self._enviado(pedido), {self.refri: 2})
        # Chegam mais latas enquanto as caipirinhas esperam: as latas não ficam presas
        pedido.write({"lines": [fields.Command.create({
            "product_id": self.refri.id, "qty": 3, "price_unit": 7.0, "price_subtotal": 21.0,
            "price_subtotal_incl": 21.0, "full_product_name": self.refri.name})]})
        pedido._boteco_enviar_bebidas()
        self.assertEqual(self._enviado(pedido), {self.refri: 5})
        # Garçom libera: as caipirinhas vão para o bar
        pedido.with_user(self.garcom).action_boteco_aprovar_pedido()
        self.assertEqual(self._enviado(pedido), {self.refri: 5, self.caipirinha: 6})

    def test_chope_conta_como_preparada(self):
        self._entrar()
        self._idade_ok()
        pedido = self._pedido(self._pedir([(self.chope, 5)]))
        self.assertEqual(pedido.boteco_status_aprovacao, "aguardando")

    def test_preparadas_dentro_do_teto_saem(self):
        self._entrar()
        self._idade_ok()
        pedido = self._pedido(self._pedir([(self.caipirinha, 4)]))
        self.assertFalse(pedido.boteco_status_aprovacao)
        self.assertEqual(self._enviado(pedido), {self.caipirinha: 4})

    def test_teto_automatico_pelo_numero_de_pessoas(self):
        self.env.company.boteco_teto_bebidas_preparadas = 0
        self.mesa.boteco_definir_clientes(2)  # max(4, 2*2+2) = 6
        self._entrar()
        self._idade_ok()
        pedido = self._pedido(self._pedir([(self.caipirinha, 6)]))
        self.assertFalse(pedido.boteco_status_aprovacao, pedido.boteco_motivos_retencao)
        self.assertEqual(self.mesa.boteco_n_clientes(), 2)  # o pedido do celular não muda as pessoas da mesa
        self.assertEqual(self._pedido(self._pedir([(self.caipirinha, 7)])).boteco_status_aprovacao, "aguardando")

    def test_alcool_sem_idade_conferida_espera(self):
        self._entrar()
        pedido = self._pedido(self._pedir([(self.chope, 1)]))
        self.assertTrue(pedido.boteco_aguardando_garcom)
        self.assertFalse(self._enviado(pedido))

    def test_status_mostra_as_bebidas_da_mesa_com_a_ultima_quantidade(self):
        self._entrar()
        self._pedir([(self.refri, 2)])
        self._pedir([(self.refri, 3)])
        dados = self._rpc("/boteco/mesa/status", {"access_token": self.token, "table_identifier": self.mesa.identifier})
        self.assertTrue(dados["qr_bebidas_ativo"])
        refri = [b for b in dados["bebidas_mesa"] if b["product_id"] == self.refri.id]
        self.assertEqual(len(refri), 1)
        self.assertEqual(refri[0]["ultima_qtd"], 3)

    def test_recurso_desligado_volta_a_pedir_liberacao(self):
        self.env.company.boteco_flag_qr_bebidas = False
        self._entrar()
        erro = self._pedir([(self.refri, 1)])
        self.assertIn("não liberou", json.dumps(erro, ensure_ascii=False))
        self.assertFalse(self.config._boteco_qr_bebidas("http%3A//x/pos-self/1%3Fa%3D1"))

    def test_qr_impresso_tem_o_modo_bebidas(self):
        self.assertTrue(self.config._boteco_qr_bebidas("u").endswith("%26modo%3Dbebidas"))
        self.assertTrue(self.env["ir.actions.report"]._render_qweb_html(
            "boteco_cardapio.report_qr_mesas", self.config.ids)[0])
