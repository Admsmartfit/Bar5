from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.boteco_cardapio.tests.common_pos import BotecoPosCase


@tagged("post_install", "-at_install", "boteco")
class TestPortariaETags(BotecoPosCase):
    """Etapa 20: validador de saída na portaria e tags rápidas."""

    def test_portaria_paga_e_pendente(self):
        aberta = self._sincronizar(self._pedido([self._linha(self.refri, 2)], mesa=self.mesa1))
        paga = self._sincronizar(self._pedido([self._linha(self.refri, 1)], pagamentos=[(self.pm_dinheiro, 7.0)]))
        Pedido = self.env["pos.order"]
        self.assertEqual(Pedido.boteco_validar_saida(paga.uuid)["cor"], "verde")
        resposta = Pedido.boteco_validar_saida(aberta.uuid)
        self.assertEqual(resposta["cor"], "vermelho")
        self.assertEqual(resposta["titulo"], "PENDENTE")
        self.assertEqual(Pedido.boteco_validar_saida("MESA 1")["cor"], "vermelho")
        self.assertEqual(Pedido.boteco_validar_saida("mesa 3")["cor"], "verde")
        self.assertEqual(Pedido.boteco_validar_saida("nao-existe")["cor"], "vermelho")

    def test_tags_rapidas_ligam_e_desligam(self):
        tag = self.env.ref("boteco_pos.tag_sem_cebola")
        self.env.company.boteco_flag_garcom_tags_rapidas = True
        self.assertIn(tag, self.config.note_ids)
        self.env.company.boteco_flag_garcom_tags_rapidas = False
        self.assertNotIn(tag, self.config.note_ids)


@tagged("post_install", "-at_install", "boteco")
class TestDeliveryECrm(BotecoPosCase):
    """Etapa 22: delivery (taxa por bairro e acerto) e régua de clientes."""

    def test_delivery_desligado_bloqueia(self):
        pedido = self._sincronizar(self._pedido([self._linha(self.batata, 1)]))
        self.env.company.boteco_flag_delivery_roteirizacao_motoboy = False
        with self.assertRaises(UserError):
            self.env["boteco.delivery.entrega"].create({"order_id": pedido.id})

    def test_taxa_por_bairro_e_acerto(self):
        self.env.company.boteco_flag_delivery_roteirizacao_motoboy = True
        centro = self.env["boteco.delivery.bairro"].create({"name": "Centro", "taxa": 6.0})
        moto = self.env["res.partner"].create({"name": "Zé Motoboy", "boteco_motoboy": True})
        Entrega = self.env["boteco.delivery.entrega"]
        for _i in range(3):
            pedido = self._sincronizar(self._pedido([self._linha(self.batata, 1)]))
            entrega = Entrega.create({"order_id": pedido.id, "bairro_id": centro.id, "motoboy_id": moto.id})
            self.assertEqual(entrega.taxa, 6.0)
            entrega.action_saiu()
            entrega.action_entregue()
        acerto = self.env["boteco.delivery.acerto"].create({})
        acerto.action_calcular()
        self.assertEqual(acerto.linha_ids.motoboy_id, moto)
        self.assertEqual(acerto.linha_ids.entregas, 3)
        self.assertAlmostEqual(acerto.linha_ids.total_taxas, 18.0)

    def test_regua_sumidos_e_aniversariantes(self):
        self.env.company.boteco_flag_crm_whatsapp_ia = True
        Parceiro = self.env["res.partner"]
        sumido = Parceiro.create({"name": "Carlos Sumido", "mobile": "(11) 99999-0000"})
        frequente = Parceiro.create({"name": "Ana Frequente"})
        hoje = fields.Date.context_today(Parceiro)
        aniversariante = Parceiro.create({"name": "Bia Festa", "boteco_aniversario": (hoje + timedelta(days=3)).replace(year=1990)})
        antigo = self._sincronizar(self._pedido([self._linha(self.refri, 1)], partner_id=sumido.id,
                                                pagamentos=[(self.pm_dinheiro, 7.0)]))
        antigo.date_order = fields.Datetime.now() - timedelta(days=30)
        self._sincronizar(self._pedido([self._linha(self.refri, 1)], partner_id=frequente.id,
                                       pagamentos=[(self.pm_dinheiro, 7.0)]))
        regua = self.env["boteco.regua.crm"].create({})
        regua.action_gerar()
        sumidos = regua.linha_ids.filtered(lambda l: l.motivo == "sumido")
        self.assertEqual(sumidos.partner_id, sumido)
        self.assertIn("wa.me/5511999990000", sumidos.link_whatsapp)
        self.assertEqual(regua.linha_ids.filtered(lambda l: l.motivo == "aniversario").partner_id, aniversariante)

    def test_regua_desligada(self):
        self.env.company.boteco_flag_crm_whatsapp_ia = False
        with self.assertRaises(UserError):
            self.env["boteco.regua.crm"].create({}).action_gerar()
