from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .boteco_perfil import PERMISSOES, PERMISSOES_DICT
from .boteco_pin_tentativa import JANELA_BLOQUEIO_MIN, MAX_TENTATIVAS

VALIDADE_MINUTOS = 5


class BotecoAutorizacao(models.Model):
    """Autorização dada na hora com o PIN do gerente.

    Fluxo: a tela pede o PIN -> ``solicitar`` confere e cria a autorização ->
    o servidor ``consumir`` quando a ação acontece de fato (ex.: o item é
    cancelado na sincronização do PDV). Uma autorização vale para uma ação só
    e expira em poucos minutos.
    """

    _name = "boteco.autorizacao"
    _description = "Autorização do gerente"
    _order = "id desc"

    permissao = fields.Selection(PERMISSOES, required=True, readonly=True)
    solicitante_id = fields.Many2one("res.users", string="Quem pediu", readonly=True, ondelete="restrict")
    autorizado_por_id = fields.Many2one("res.users", string="Quem autorizou", readonly=True, ondelete="restrict")
    motivo = fields.Char(readonly=True)
    referencia = fields.Char(
        readonly=True,
        index=True,
        help="Identifica o que foi autorizado (ex.: uuid da linha do pedido).",
    )
    valor = fields.Float(readonly=True)
    validade = fields.Datetime(readonly=True)
    usada = fields.Boolean(readonly=True, index=True)
    usada_em = fields.Datetime(readonly=True)
    company_id = fields.Many2one("res.company", default=lambda s: s.env.company, readonly=True)

    @api.model
    def _gerente_pelo_pin(self, pin, permissao):
        """Pessoa ativa com a permissão cujo PIN confere (ou vazio)."""
        candidatos = self.env["res.users"].sudo().search(
            [("share", "=", False), ("boteco_pin_hash", "!=", False)]
        )
        for user in candidatos:
            if user.boteco_pode(permissao) and user._boteco_pin_confere(pin):
                return user
        return self.env["res.users"]

    @api.model
    def solicitar(self, pin, permissao, motivo=None, referencia=None, valor=0.0):
        """Confere o PIN do gerente e devolve a autorização.

        Se quem pede já tem a permissão no próprio perfil, o PIN pode ficar em branco.
        Retorna dict para as telas OWL: {id, autorizado_por, autorizado_por_id} ou {erro}.

        Não levanta exceção quando o PIN é recusado: assim a tentativa e a auditoria
        de "PIN recusado" são gravadas junto com a resposta (exceção desfaria tudo).
        """
        if permissao not in PERMISSOES_DICT:
            raise UserError(_("Permissão desconhecida."))
        Tentativa = self.env["boteco.pin.tentativa"]
        solicitante = self.env.user
        if not pin and solicitante.boteco_pode(permissao):
            gerente = solicitante
        else:
            if Tentativa._bloqueado(solicitante.id, "autorizacao"):
                return {
                    "erro": _("Muitos PINs errados. Espere %s minutos ou chame o dono.") % JANELA_BLOQUEIO_MIN,
                    "bloqueado": True,
                }
            gerente = self._gerente_pelo_pin(pin, permissao)
            ip = self.env["res.users"]._boteco_ip()
            if not gerente:
                Tentativa._registrar_isolado(solicitante.id, "autorizacao", False, ip)
                self.env["boteco.auditoria"].registrar(
                    "autorizacao_negada",
                    descricao=_("PIN recusado para: %s", PERMISSOES_DICT[permissao]),
                    motivo=motivo,
                    referencia=referencia,
                    valor=valor,
                )
                restantes = MAX_TENTATIVAS - Tentativa._falhas_recentes(solicitante.id, "autorizacao")
                return {
                    "erro": _("PIN não confere ou essa pessoa não pode autorizar isso. Restam %s tentativas.")
                    % max(restantes, 0),
                    "bloqueado": restantes <= 0,
                }
            Tentativa._registrar_isolado(solicitante.id, "autorizacao", True, ip)
        autorizacao = self.sudo().create(
            {
                "permissao": permissao,
                "solicitante_id": solicitante.id,
                "autorizado_por_id": gerente.id,
                "motivo": motivo,
                "referencia": referencia,
                "valor": valor or 0.0,
                "validade": fields.Datetime.now() + timedelta(minutes=VALIDADE_MINUTOS),
            }
        )
        return {
            "id": autorizacao.id,
            "autorizado_por": gerente.name,
            "autorizado_por_id": gerente.id,
        }

    @api.model
    def consumir(self, permissao, referencia=None, autorizacao_id=None):
        """Usa uma autorização válida (não usada, não vencida). Retorna o registro ou vazio."""
        domain = [
            ("permissao", "=", permissao),
            ("usada", "=", False),
            ("validade", ">=", fields.Datetime.now()),
        ]
        if autorizacao_id:
            domain.append(("id", "=", int(autorizacao_id)))
        if referencia:
            domain.append(("referencia", "=", referencia))
        autorizacao = self.sudo().search(domain, order="id desc", limit=1)
        if autorizacao:
            autorizacao.write({"usada": True, "usada_em": fields.Datetime.now()})
        return autorizacao

    @api.model
    def _limpar_vencidas(self):
        """Cron: apaga autorizações não usadas vencidas há mais de 7 dias (as usadas ficam na auditoria)."""
        self.sudo().search(
            [("usada", "=", False), ("validade", "<", fields.Datetime.now() - timedelta(days=7))]
        ).unlink()
