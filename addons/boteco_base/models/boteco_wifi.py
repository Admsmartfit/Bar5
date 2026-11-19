"""Tela simples do Wi-Fi do bar (Primeiros passos): em vez do cadastro inteiro da empresa."""

import ipaddress

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.http import request

from ..tools.rede import normalizar_redes


def ip_deste_aparelho():
    try:
        return request.httprequest.remote_addr if request else ""
    except RuntimeError:
        return ""


def rede_do_ip(ip):
    """192.168.0.37 -> 192.168.0.0/24 (só endereços de rede local)."""
    try:
        endereco = ipaddress.ip_address(ip or "")
    except ValueError:
        return ""
    if not endereco.is_private or endereco.version != 4 or endereco.is_loopback:
        return ""
    # Endereço interno do Docker (o navegador está no próprio servidor): não é o Wi-Fi do bar
    if endereco in ipaddress.ip_network("172.16.0.0/12") and str(endereco).endswith(".0.1"):
        return ""
    return str(ipaddress.ip_network("%s/24" % endereco, strict=False))


class BotecoWifi(models.TransientModel):
    _name = "boteco.wifi"
    _description = "Wi-Fi do bar"

    rede_equipe = fields.Char("Rede da equipe", default=lambda s: s.env.company.boteco_rede_sistema)
    rede_clientes = fields.Char("Rede dos clientes", default=lambda s: s.env.company.boteco_rede_clientes)
    ip_aparelho = fields.Char("Este aparelho está no endereço", readonly=True, default=lambda s: ip_deste_aparelho())
    rede_aparelho = fields.Char("Rede deste aparelho", readonly=True, default=lambda s: rede_do_ip(ip_deste_aparelho()))

    def _reabrir(self):
        return {"type": "ir.actions.act_window", "res_model": self._name, "res_id": self.id, "view_mode": "form",
                "views": [(False, "form")], "target": "new", "name": _("Wi-Fi do bar")}

    def action_usar_na_equipe(self):
        self.ensure_one()
        if not self.rede_aparelho:
            raise UserError(_("Não consegui descobrir a rede deste aparelho. Peça ao técnico os números da rede."))
        self.rede_equipe = self.rede_aparelho
        return self._reabrir()

    def action_usar_nos_clientes(self):
        self.ensure_one()
        if not self.rede_aparelho:
            raise UserError(_("Não consegui descobrir a rede deste aparelho. Peça ao técnico os números da rede."))
        self.rede_clientes = self.rede_aparelho
        return self._reabrir()

    def action_salvar(self):
        self.ensure_one()
        redes = {}
        for campo, texto in (("boteco_rede_sistema", self.rede_equipe), ("boteco_rede_clientes", self.rede_clientes)):
            try:
                redes[campo] = normalizar_redes(texto) or False
            except ValueError:
                raise UserError(_("\"%s\" não é uma rede. Use o formato 192.168.0.0/24 (ou o endereço do roteador, "
                                  "ex.: 192.168.0.1).", texto)) from None
        self.env.company.sudo().write(redes)
        return {"type": "ir.actions.act_window_close"}

    @api.model
    def abrir(self):
        return self.create({})._reabrir()
