"""Fornecedor (Compras inteligentes).

19/11/2026: a leitura do Instagram saiu do Odoo. Sites, Instagram, WhatsApp e fotos ficam no serviço externo
de cotações, que manda só dados limpos pela API (boteco_cotacoes, docs/integracao_cotacoes.md).
"""

from odoo import models


class ResPartner(models.Model):
    _inherit = "res.partner"
