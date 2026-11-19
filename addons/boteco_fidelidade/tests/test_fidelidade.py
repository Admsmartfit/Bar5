from datetime import timedelta

from odoo import fields
from odoo.tests import tagged

from odoo.addons.boteco_cardapio.tests.common_pos import BotecoPosCase


@tagged("post_install", "-at_install", "boteco")
class TestFidelidade(BotecoPosCase):
    """Etapa 31: fidelidade / cashback sobre o loyalty gratuito."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.ref("boteco_cardapio.happy_hour_padrao").active = False
        cls.env.company.boteco_flag_fidelidade = True
        Programa = cls.env["loyalty.program"].with_context(active_test=False)
        Programa.search([("boteco_modelo", "!=", False)]).unlink()  # o banco de teste não tinha chope na instalação
        cls.chope_500 = cls.env["product.product"].create({
            "name": "Chope 500 ml", "list_price": 15.0, "available_in_pos": True, "type": "consu",
            "taxes_id": [fields.Command.clear()], "boteco_setor_id": cls.setor_bar.id,
        })
        Programa._boteco_criar_modelos()
        cls.cartao = Programa.search([("boteco_modelo", "=", "cartao_chope")])
        cls.cliente = cls.env["res.partner"].create({"name": "Ana Souza", "mobile": "11988887777"})

    def _carregados(self):
        Programa = self.env["loyalty.program"]
        dominio = Programa._load_pos_data_domain({"pos.config": {"data": [{"id": self.config.id}]}})
        return Programa.search(dominio)

    def _cartao_da_cliente(self):
        return self.env["loyalty.card"].search([("partner_id", "=", self.cliente.id), ("program_id", "=", self.cartao.id)])

    def test_modelos_criados_desligados(self):
        modelos = self.env["loyalty.program"].with_context(active_test=False).search([("boteco_modelo", "!=", False)])
        self.assertEqual(set(modelos.mapped("boteco_modelo")), {"cartao_chope", "cashback", "aniversario"})
        self.assertFalse(any(modelos.mapped("active")))
        self.assertEqual(self.cartao.rule_ids.product_ids, self.chope | self.chope_500)
        self.assertEqual(self.cartao.reward_ids.reward_product_id, self.chope)  # o chope mais barato
        self.assertEqual(self.cartao.reward_ids.required_points, 9)  # 9 pagos, o 10º grátis
        self.assertTrue(self.cartao.boteco_auto_resgate)
        # Rodar de novo não duplica
        self.env["loyalty.program"]._boteco_criar_modelos()
        self.assertEqual(self.env["loyalty.program"].with_context(active_test=False).search_count(
            [("boteco_modelo", "=", "cartao_chope")]), 1)

    def test_flag_desligada_nao_oferece_programas_no_pdv(self):
        self.cartao.active = True
        self.assertIn(self.cartao, self._carregados())
        self.env.company.boteco_flag_fidelidade = False
        self.assertFalse(self._carregados())

    def test_pontos_entram_e_funcionario_nao_ganha(self):
        self.cartao.active = True
        pedido = self._sincronizar(self._pedido([self._linha(self.chope, 3)], partner_id=self.cliente.id))
        pedido.confirm_coupon_programs({-1: {"program_id": self.cartao.id, "coupon_id": -1, "points": 3,
                                             "partner_id": self.cliente.id, "barcode": "", "date_to": False}})
        self.assertEqual(self._cartao_da_cliente().points, 3)
        consumo = self._sincronizar(self._pedido([self._linha(self.chope, 5)], partner_id=self.cliente.id))
        consumo.boteco_tipo_conta = "funcionario"
        cartao = self._cartao_da_cliente()
        consumo.confirm_coupon_programs({cartao.id: {"program_id": self.cartao.id, "coupon_id": cartao.id,
                                                     "points": 5, "partner_id": self.cliente.id}})
        self.assertEqual(cartao.points, 3)

    def test_saldo_aparece_na_minha_conta_do_tablet(self):
        self.cartao.active = True
        self.env["loyalty.card"].create({"program_id": self.cartao.id, "partner_id": self.cliente.id, "points": 7})
        self._sincronizar(self._pedido([self._linha(self.chope, 1)], mesa=self.mesa1, partner_id=self.cliente.id))
        saldo = self.env["pos.order"]._boteco_resumo_mesa(self.mesa1)["fidelidade"]
        self.assertEqual(len(saldo), 1)
        self.assertEqual(saldo[0]["pontos"], 7)
        self.assertEqual(saldo[0]["faltam"], 2)
        self.assertEqual(saldo[0]["cliente"], "Ana")
        self.env.company.boteco_flag_fidelidade = False
        self.assertEqual(self.env["pos.order"]._boteco_resumo_mesa(self.mesa1)["fidelidade"], [])

    def test_aniversariante_recebe_codigo_do_cupom(self):
        self.env.company.boteco_flag_crm_whatsapp_ia = True
        aniversario = self.env["loyalty.program"].with_context(active_test=False).search(
            [("boteco_modelo", "=", "aniversario")])
        aniversario.active = True
        self.cliente.boteco_aniversario = fields.Date.today() + timedelta(days=2)
        regua = self.env["boteco.regua.crm"].create({})
        regua.action_gerar()
        linha = regua.linha_ids.filtered(lambda l: l.partner_id == self.cliente)
        cupom = self.env["loyalty.card"].search([("program_id", "=", aniversario.id), ("partner_id", "=", self.cliente.id)])
        self.assertEqual(len(cupom), 1)
        self.assertIn(cupom.code, linha.mensagem)
        self.assertIn("wa.me", linha.link_whatsapp)
        # Gerar a régua de novo não cria outro cupom no mesmo ano
        regua.action_gerar()
        self.assertEqual(self.env["loyalty.card"].search_count(
            [("program_id", "=", aniversario.id), ("partner_id", "=", self.cliente.id)]), 1)
