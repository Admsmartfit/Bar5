from lxml import etree

from odoo.tests import TransactionCase, tagged

from ..models.res_config_settings import remover_opcoes_pagas


@tagged("post_install", "-at_install")
class TestSemEnterprise(TransactionCase):
    def test_tela_de_configuracoes_sem_opcoes_pagas(self):
        visao = self.env["res.config.settings"].get_views([(False, "form")])["views"]["form"]["arch"]
        self.assertNotIn("upgrade_boolean", visao)
        # Opções gratuitas continuam (ex.: lotes e números de série do Inventário)
        self.assertIn("group_stock_production_lot", visao)

    def test_remove_bloco_e_secao_vazia(self):
        arch = etree.fromstring("""
            <form><app>
              <block title="Código de barras">
                <setting id="pago"><field name="module_stock_barcode" widget="upgrade_boolean"/></setting>
              </block>
              <block title="Operações">
                <setting id="gratis"><field name="module_stock_picking_batch"/></setting>
                <setting id="misto">
                  <field name="module_quality_control"/>
                  <div class="row"><field name="module_quality_control_worksheet" widget="upgrade_boolean"/></div>
                </setting>
              </block>
            </app></form>""")
        self.assertEqual(remover_opcoes_pagas(arch), 2)
        self.assertFalse(arch.xpath("//setting[@id='pago']"))
        self.assertFalse(arch.xpath("//block[@title='Código de barras']"))
        self.assertTrue(arch.xpath("//setting[@id='gratis']"))
        self.assertTrue(arch.xpath("//field[@name='module_quality_control']"))
        self.assertFalse(arch.xpath("//field[@name='module_quality_control_worksheet']"))

    def test_aplicativos_sem_pagos(self):
        self.assertIn("to_buy", self.env.ref("base.open_module_tree").domain)
