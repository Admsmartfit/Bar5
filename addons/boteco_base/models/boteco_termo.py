import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class BotecoTermo(models.Model):
    """Troca nomes de menus do Odoo por linguagem de boteco (sem mexer no código do Odoo)."""

    _name = "boteco.termo"
    _description = "Termo de boteco"
    _order = "sequence, id"

    sequence = fields.Integer(default=10)
    xmlid = fields.Char("Menu (xmlid)", required=True, help="Ex.: sale.menu_sale_order")
    nome_original = fields.Char("Nome no Odoo", readonly=True)
    nome_boteco = fields.Char("Nome no boteco", required=True)
    active = fields.Boolean(default=True)

    def _aplicar(self):
        for termo in self.filtered("active"):
            menu = self.env.ref(termo.xmlid, raise_if_not_found=False)
            if not menu or menu._name != "ir.ui.menu":
                _logger.info("Termo de boteco ignorado: menu %s não existe", termo.xmlid)
                continue
            if not termo.nome_original:
                termo.nome_original = menu.with_context(lang="pt_BR").name
            for lang in ("pt_BR", "en_US"):
                if self.env["res.lang"]._lang_get(lang):
                    menu.with_context(lang=lang).name = termo.nome_boteco
        self.env.registry.clear_cache()
        return True

    def action_aplicar(self):
        return self.search([])._aplicar()

    def action_restaurar(self):
        for termo in self:
            menu = self.env.ref(termo.xmlid, raise_if_not_found=False)
            if menu and termo.nome_original:
                menu.with_context(lang="pt_BR").name = termo.nome_original
            termo.active = False
        return True

    @api.model_create_multi
    def create(self, vals_list):
        termos = super().create(vals_list)
        termos._aplicar()
        return termos
