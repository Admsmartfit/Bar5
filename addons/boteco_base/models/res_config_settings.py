"""Esconde as opções da versão paga (Odoo Enterprise) na tela de Configurações.

O Odoo Community mostra algumas opções pagas com a etiqueta "Enterprise"; marcar uma delas só abre
uma janela de propaganda ("Fazer upgrade agora"). Elas são identificadas pelo componente
``upgrade_boolean``: removemos esses blocos da tela, em todos os módulos (mesmo os instalados depois).
"""

from odoo import api, models

WIDGET_PAGO = "upgrade_boolean"


def remover_opcoes_pagas(arch):
    """Tira do XML da tela as opções pagas. Devolve quantas foram removidas."""
    removidas = 0
    for campo in arch.xpath("//field[@widget='%s']" % WIDGET_PAGO):
        if campo.getparent() is None:
            continue  # já saiu junto com um bloco removido antes
        bloco = next(campo.iterancestors("setting"), None)
        principal = bloco is not None and bloco.xpath(".//field")[:1] == [campo]
        if principal:
            alvo = bloco  # a opção inteira é paga
        else:
            # Sub-opção paga dentro de uma opção gratuita: tira só a linha dela
            alvo = campo.getparent() if campo.getparent().tag == "div" else campo
        if alvo.getparent() is not None:
            alvo.getparent().remove(alvo)
            removidas += 1
    # Seções que ficaram vazias (ex.: "Código de barras" só tinha opções pagas)
    for secao in arch.xpath("//block"):
        if not secao.xpath(".//setting|.//field") and secao.getparent() is not None:
            secao.getparent().remove(secao)
    return removidas


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    @api.model
    def _get_view(self, view_id=None, view_type="form", **options):
        arch, view = super()._get_view(view_id, view_type, **options)
        if view_type == "form":
            remover_opcoes_pagas(arch)
        return arch, view
