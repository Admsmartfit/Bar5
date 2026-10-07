from odoo import fields, models

from .fiscal import ORIGENS, UNIDADES


class ProductCategory(models.Model):
    """Valores fiscais e de produção padrão por categoria: o cadastro de produto já vem preenchido."""

    _inherit = "product.category"

    boteco_ncm_padrao = fields.Char("NCM padrão")
    boteco_cfop_padrao = fields.Char("CFOP padrão", help="Ex.: 5102 (revenda) ou 5101 (produção própria).")
    boteco_cst_csosn_padrao = fields.Char("CST/CSOSN padrão", help="Simples Nacional: CSOSN (ex.: 102, 500).")
    boteco_origem_padrao = fields.Selection(ORIGENS, string="Origem padrão", default="0")
    boteco_unidade_fiscal_padrao = fields.Selection(UNIDADES, string="Unidade fiscal padrão", default="UN")
    boteco_setor_padrao_id = fields.Many2one("boteco.setor", string="Setor padrão")
    boteco_maior_18_padrao = fields.Boolean("+18 por padrão", help="Ex.: categoria Cervejas.")
