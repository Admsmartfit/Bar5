import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..tools import escpos

_logger = logging.getLogger(__name__)


class BotecoImpressora(models.Model):
    """Impressora de rede: pedidos (ESC/POS 80 mm) ou etiquetas (ZPL/TSPL).

    O servidor imprime direto pela rede (porta 9100), então funciona com qualquer
    marca e não depende do navegador nem da caixinha IoT.
    """

    _name = "boteco.impressora"
    _description = "Impressora de rede"
    _order = "sequence, name"

    name = fields.Char("Nome", required=True, help="Ex.: Impressora da chapa")
    sequence = fields.Integer(default=10)
    ip = fields.Char("Endereço IP", required=True)
    porta = fields.Integer("Porta", default=9100)
    linguagem = fields.Selection(
        [("escpos", "Pedidos (ESC/POS)"), ("zpl", "Etiqueta (ZPL – Zebra/Elgin)"), ("tspl", "Etiqueta (TSPL – Argox/TSC)")],
        default="escpos",
        required=True,
    )
    colunas = fields.Integer("Caracteres por linha", default=48, help="80 mm = 48 (fonte normal). 58 mm = 32.")
    codepage = fields.Selection(
        [("cp860", "Português (PC860)"), ("cp850", "Multilíngue (PC850)"), ("cp437", "EUA (PC437)")],
        default="cp860",
        string="Tabela de caracteres",
    )
    bip = fields.Boolean("Apitar ao imprimir", default=True)
    estado = fields.Selection(
        [("desconhecido", "Não testada"), ("ok", "Funcionando"), ("erro", "Com problema")],
        default="desconhecido",
        readonly=True,
    )
    ultimo_erro = fields.Char("Último problema", readonly=True)
    ultima_verificacao = fields.Datetime("Última verificação", readonly=True)
    company_id = fields.Many2one("res.company", default=lambda s: s.env.company)
    active = fields.Boolean(default=True)

    # ------------------------------------------------------------------
    def _mensagem_erro(self):
        self.ensure_one()
        return _(
            "%(nome)s não respondeu (%(ip)s). Confira se está ligada, com papel e no cabo/Wi-Fi. "
            "Depois toque em Tentar de novo.",
            nome=self.name,
            ip=self.ip,
        )

    def _marcar(self, ok, erro=None):
        vals = {"estado": "ok" if ok else "erro", "ultimo_erro": False if ok else (erro or "")[:250],
                "ultima_verificacao": fields.Datetime.now()}
        for impressora in self:
            if any(impressora[k] != v for k, v in vals.items() if k != "ultima_verificacao"):
                impressora.sudo().write(vals)

    def enviar_bytes(self, dados, levantar=True):
        """Envia bytes brutos. Com levantar=False devolve True/False em vez de erro."""
        self.ensure_one()
        try:
            escpos.enviar(dados, self.ip, self.porta or 9100)
        except escpos.ImpressoraIndisponivel as erro:
            _logger.warning("Impressora %s (%s) indisponível: %s", self.name, self.ip, erro)
            self._marcar(False, str(erro))
            if levantar:
                raise UserError(self._mensagem_erro()) from erro
            return False
        self._marcar(True)
        return True

    def novo_ticket(self):
        self.ensure_one()
        return escpos.Ticket(colunas=self.colunas or 48, codepage=self.codepage or "cp860")

    def _ticket_teste(self):
        self.ensure_one()
        agora = self.env["res.company"].boteco_agora_local()
        t = self.novo_ticket()
        t.titulo(self.env.company.name or "Boteco")
        t.texto("TESTE DE IMPRESSÃO", tamanho=2, alinhar="centro", negrito=True)
        t.separador()
        t.colunas_texto("Impressora", self.name)
        t.colunas_texto("Endereço", "%s:%s" % (self.ip, self.porta))
        t.colunas_texto("Data", agora.strftime("%d/%m/%Y %H:%M:%S"))
        t.separador()
        t.texto("Acentuação: ÁÉÍÓÚ ÂÊÔ ÃÕ Ç àéíóú ç")
        t.texto("Normal / ", tamanho=1)
        t.texto("Dobro", tamanho=2)
        t.destaque("SEM CEBOLA")
        t.qrcode("https://boteco.local/boteco/saude")
        if self.bip:
            t.bip(1)
        t.corte()
        return t.bytes()

    def _etiqueta_teste(self):
        self.ensure_one()
        if self.linguagem == "zpl":
            return (
                "^XA^CI28^PW800^LL400^FO30,30^A0N,50,50^FDTESTE DE ETIQUETA^FS"
                "^FO30,100^A0N,32,32^FD%s^FS^FO30,150^BQN,2,6^FDQA,BOTECO-TESTE^FS^XZ" % self.name
            ).encode("utf-8")
        return (
            'SIZE 100 mm,50 mm\r\nGAP 2 mm,0\r\nCODEPAGE UTF-8\r\nCLS\r\n'
            'TEXT 30,30,"3",0,1,1,"TESTE DE ETIQUETA"\r\nTEXT 30,90,"2",0,1,1,"%s"\r\n'
            'QRCODE 30,140,M,6,A,0,"BOTECO-TESTE"\r\nPRINT 1\r\n' % self.name
        ).encode("utf-8")

    def action_imprimir_teste(self):
        for impressora in self:
            dados = impressora._ticket_teste() if impressora.linguagem == "escpos" else impressora._etiqueta_teste()
            impressora.enviar_bytes(dados)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Teste enviado"),
                "message": _("Confira o papel na impressora."),
                "type": "success",
                "sticky": False,
            },
        }

    def action_verificar(self):
        for impressora in self:
            ok = escpos.testar_conexao(impressora.ip, impressora.porta or 9100)
            impressora._marcar(ok, None if ok else _("Sem resposta na porta %s") % impressora.porta)
        return True

    @api.model
    def _cron_verificar(self):
        self.search([]).action_verificar()
