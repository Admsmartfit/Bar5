from odoo.tests import tagged

from .common import BotecoCase


@tagged("post_install", "-at_install", "boteco")
class TestPerfil(BotecoCase):
    def test_perfil_define_os_grupos(self):
        self.assertTrue(self.garcom.has_group("boteco_base.group_garcom"))
        self.assertTrue(self.garcom.has_group("point_of_sale.group_pos_user"))
        self.assertFalse(self.garcom.has_group("boteco_base.group_gerente"))
        self.assertFalse(self.garcom.has_group("base.group_system"))
        # Trocar de perfil tira os acessos do perfil anterior
        self.gerente.boteco_perfil_id = self.perfil_garcom
        self.assertFalse(self.gerente.has_group("boteco_base.group_gerente"))
        self.assertFalse(self.gerente.has_group("stock.group_stock_user"))

    def test_tela_inicial(self):
        self.assertEqual(self.garcom.action_id.id, self.env.ref("boteco_base.action_boteco_inicio").id)
        self.assertTrue(self.garcom._boteco_url_inicio().startswith(("/pos/ui", "/odoo")))

    def test_garcom_ve_so_os_menus_do_perfil(self):
        """Critério de aceite: garçom entra e vê só o que o perfil permite."""
        Menu = self.env["ir.ui.menu"].with_user(self.garcom)
        visiveis = Menu.browse(Menu._visible_menu_ids())
        raizes = {int(m.parent_path.split("/")[0]) for m in visiveis}
        permitidas = set(self.perfil_garcom.menu_ids.ids)
        self.assertTrue(raizes)
        self.assertTrue(raizes <= permitidas, "Garçom vendo menus fora do perfil")
        self.assertNotIn(self.env.ref("stock.menu_stock_root").id, raizes)
        self.assertNotIn(self.env.ref("boteco_base.menu_boteco_config").id, visiveis.ids)

    def test_permissoes_liga_desliga(self):
        self.assertFalse(self.garcom.boteco_pode("pode_cancelar_item"))
        self.assertTrue(self.gerente.boteco_pode("pode_cancelar_item"))
        self.perfil_garcom.pode_cancelar_item = True
        self.assertTrue(self.garcom.boteco_pode("pode_cancelar_item"))
        self.assertTrue(
            self.env["boteco.auditoria"].search([("acao", "=", "permissao"), ("res_id", "=", self.perfil_garcom.id)])
        )

    def test_dia_de_operacao_vira_as_6h(self):
        from datetime import date, datetime

        empresa = self.env.company
        empresa.boteco_hora_virada = 6.0
        empresa.partner_id.tz = "America/Sao_Paulo"
        # 02:00 de sábado em Brasília = 05:00 UTC -> ainda é sexta
        self.assertEqual(empresa.boteco_dia_operacao(datetime(2026, 10, 10, 5, 0)), date(2026, 10, 9))
        # 07:00 de sábado em Brasília = 10:00 UTC -> sábado
        self.assertEqual(empresa.boteco_dia_operacao(datetime(2026, 10, 10, 10, 0)), date(2026, 10, 10))
        inicio, fim = empresa.boteco_intervalo_dia(date(2026, 10, 9))
        self.assertEqual(inicio, datetime(2026, 10, 9, 9, 0))
        self.assertEqual(fim, datetime(2026, 10, 10, 9, 0))
