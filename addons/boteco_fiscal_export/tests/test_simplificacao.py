from odoo import fields
from odoo.tests import new_test_user, tagged

from odoo.addons.boteco_cardapio.tests.common_pos import BotecoPosCase


@tagged("post_install", "-at_install", "boteco")
class TestSimplificacao(BotecoPosCase):
    """Etapa 34: B2B escondido, Contador só em Finanças, sem frete, cozinha central só para quem produz."""

    def _menus_visiveis(self, user):
        return self.env["ir.ui.menu"].with_user(user)._visible_menu_ids()

    def test_b2b_desligado_esconde_e_ligado_mostra(self):
        menu = self.env.ref("boteco_b2b.menu_boteco_b2b")
        self.env.company.boteco_flag_vendas_b2b = False
        self.assertFalse(menu.active)
        self.assertEqual(len(self.env["boteco.painel"].dados()["metas"]), 1)
        self.env.company.boteco_flag_vendas_b2b = True
        self.assertTrue(menu.active)
        self.assertEqual(len(self.env["boteco.painel"].dados()["metas"]), 3)

    def test_b2b_desligado_nao_gera_pedido_recorrente(self):
        self.env.company.boteco_flag_vendas_b2b = False
        antes = self.env["sale.order"].search_count([])
        self.env["boteco.b2b.recorrencia"]._cron_gerar_pedidos()
        self.assertEqual(self.env["sale.order"].search_count([]), antes)

    def test_contador_so_ve_financas(self):
        contador = new_test_user(self.env, login="contador_teste", name="Contador", groups="base.group_user")
        contador.boteco_perfil_id = self.env.ref("boteco_base.perfil_contador")
        visiveis = self._menus_visiveis(contador)
        self.assertIn(self.env.ref("boteco_fiscal_export.menu_fiscal_exportar").id, visiveis)
        self.assertIn(self.env.ref("boteco_painel.menu_fechamento_dia").id, visiveis)
        self.assertNotIn(self.env.ref("boteco_cardapio.menu_boteco_cardapio").id, visiveis)
        self.assertNotIn(self.env.ref("boteco_pos.menu_boteco_salao").id, visiveis)
        self.assertNotIn(self.env.ref("boteco_base.menu_boteco_config").id, visiveis)
        self.env["boteco.fiscal.registro"].with_user(contador).search([])  # tem acesso
        self.assertIn("boteco_fiscal_export.action_fiscal", contador._boteco_url_inicio())

    def test_sem_frete_nas_configuracoes_e_aplicativos(self):
        visao = self.env["res.config.settings"].get_views([(False, "form")])["views"]["form"]["arch"]
        self.assertNotIn('name="module_delivery"', visao)
        dominio = self.env.ref("base.open_module_tree").domain
        self.assertIn("delivery%", dominio)

    def test_cozinha_central_so_para_quem_produz(self):
        menu = self.env.ref("boteco_cozinha_central.menu_boteco_cozinha").id
        self.assertNotIn(menu, self._menus_visiveis(self.gerente))
        cozinheiro = self._pessoa("Cozinheira", "cozinheira_simpl", self.env.ref("boteco_base.perfil_cozinheiro"), "5937")
        self.assertIn(menu, self._menus_visiveis(cozinheiro))

    def test_botoes_avancados_do_pdv_so_gerente(self):
        self.assertTrue(self.perfil_gerente.pode_botoes_avancados_pdv)
        self.assertFalse(self.perfil_garcom.pode_botoes_avancados_pdv)
        self.assertFalse(self.perfil_caixa.pode_botoes_avancados_pdv)

    def test_congelado_so_baixa_estoque_e_frito_vai_para_a_chapa(self):
        kg = self.env.ref("uom.product_uom_kgm")
        Produto = self.env["product.product"]
        congelado = Produto.create({
            "name": "Bolinho congelado (para levar)", "boteco_produzido_cozinha": True, "uom_id": kg.id,
            "uom_po_id": kg.id, "available_in_pos": True, "list_price": 60.0, "taxes_id": [fields.Command.clear()]})
        frito = Produto.create({
            "name": "Porção de bolinho (frita)", "available_in_pos": True, "list_price": 42.0, "type": "consu",
            "boteco_setor_id": self.setor_chapa.id, "taxes_id": [fields.Command.clear()]})
        self.env["mrp.bom"].create({
            "product_tmpl_id": frito.product_tmpl_id.id, "type": "phantom", "product_qty": 1,
            "bom_line_ids": [fields.Command.create({"product_id": congelado.id, "product_qty": 0.3})]})
        self.assertFalse(congelado.product_tmpl_id.boteco_aviso_producao)
        self.assertFalse(frito.product_tmpl_id.boteco_aviso_producao)
        Ticket = self.env["boteco.kds.pedido"]
        venda_congelado = self._sincronizar(self._pedido([self._linha(congelado, 1)], mesa=self.mesa1))
        self.assertFalse(Ticket.search([("order_id", "=", venda_congelado.id)]))
        venda_frito = self._sincronizar(self._pedido([self._linha(frito, 1)], mesa=self.mesa2))
        self.assertEqual(Ticket.search([("order_id", "=", venda_frito.id)]).setor_id, self.setor_chapa)
        # Kit sem setor (preparado esquecido) gera aviso no cadastro
        frito.boteco_setor_id = False
        self.assertIn("não vai para a produção", frito.product_tmpl_id.boteco_aviso_producao)
