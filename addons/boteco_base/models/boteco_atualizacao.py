"""Tela "Atualizar sistema": mostra a versão e as novidades do GitHub e pede a atualização ao servidor.

O Odoo não se atualiza sozinho (teria que se parar e reiniciar). Ele só grava um pedido na pasta
compartilhada; o agente do servidor (scripts/agente_atualizacao.sh, via systemd) faz backup, baixa o
código, atualiza os módulos e, se algo falhar, volta tudo como estava.
"""

import os

from odoo import _, api, fields, models
from odoo.exceptions import UserError

PASTA_PADRAO = "/boteco_atualizacao"
ESTADOS = [
    ("sem_agente", "Servidor sem o agente de atualização"),
    ("em_dia", "Sistema em dia"),
    ("disponivel", "Atualização disponível"),
    ("pedido", "Pedido enviado ao servidor"),
    ("em_andamento", "Atualizando agora"),
    ("falhou", "A última atualização falhou (sistema voltou como estava)"),
    ("erro", "Não foi possível consultar o GitHub"),
]


def _ler(caminho):
    try:
        with open(caminho, encoding="utf-8") as arquivo:
            return arquivo.read()
    except OSError:
        return ""


def _linhas_versao(texto):
    """'commit<TAB>data<TAB>assunto' por linha -> lista de dicionários."""
    versoes = []
    for linha in texto.splitlines():
        partes = linha.split("\t", 2)
        if len(partes) == 3:
            versoes.append({"commit": partes[0], "data": partes[1][:16], "assunto": partes[2]})
    return versoes


class BotecoAtualizacao(models.TransientModel):
    _name = "boteco.atualizacao"
    _description = "Atualizar sistema"

    estado = fields.Selection(ESTADOS, compute="_compute_situacao")
    versao_atual = fields.Char("Versão instalada", compute="_compute_situacao")
    verificado_em = fields.Char("Última consulta ao GitHub", compute="_compute_situacao")
    mensagem = fields.Char(compute="_compute_situacao")
    novidades = fields.Text("O que vem na atualização", compute="_compute_situacao")
    quantidade = fields.Integer("Versões novas", compute="_compute_situacao")
    ultima_atualizacao = fields.Char("Última atualização", compute="_compute_situacao")
    ultimo_log = fields.Text("Relatório da última atualização", compute="_compute_situacao")
    contas_abertas = fields.Integer("Caixas abertos agora", compute="_compute_situacao")
    atualizar_imagem = fields.Boolean(
        "Atualizar também o Odoo (imagem Docker)",
        help="Baixa a versão mais nova do Odoo 18 (correções de segurança). Demora alguns minutos a mais.")
    confirmo = fields.Boolean("Entendi: o sistema fica fora do ar por alguns minutos")

    # ------------------------------------------------------------------
    @api.model
    def _pasta(self):
        return os.environ.get("BOTECO_ATUALIZACAO_DIR") or PASTA_PADRAO

    @api.depends_context("uid")
    def _compute_situacao(self):
        pasta = self._pasta()
        atual = _linhas_versao(_ler(os.path.join(pasta, "versao_atual.txt")))
        novas = _linhas_versao(_ler(os.path.join(pasta, "disponiveis.txt")))
        verificacao = _ler(os.path.join(pasta, "verificacao.txt")).splitlines()
        status = _ler(os.path.join(pasta, "status.txt")).splitlines()
        pedido = os.path.exists(os.path.join(pasta, "pedido.txt"))
        sessoes = self.env["pos.session"].sudo().search_count([("state", "in", ("opening_control", "opened"))])
        situacao_status = status[0] if status else ""
        if not verificacao:
            estado = "sem_agente"
        elif pedido:
            estado = "pedido"
        elif situacao_status == "em_andamento":
            estado = "em_andamento"
        elif verificacao[0] == "erro":
            estado = "erro"
        elif novas:
            estado = "disponivel"
        elif situacao_status == "falhou":
            estado = "falhou"
        else:
            estado = "em_dia"
        for registro in self:
            registro.estado = estado
            registro.versao_atual = ("%s (%s) – %s" % (atual[0]["commit"], atual[0]["data"], atual[0]["assunto"])
                                     if atual else False)
            registro.verificado_em = verificacao[1] if len(verificacao) > 1 else False
            registro.mensagem = verificacao[2] if len(verificacao) > 2 else False
            registro.quantidade = len(novas)
            registro.novidades = "\n".join("• %s  (%s)" % (v["assunto"], v["data"]) for v in novas) or False
            registro.ultima_atualizacao = (
                _("%(r)s em %(f)s (%(de)s → %(para)s), pedida por %(q)s", r=status[0], f=status[2] or status[1],
                  de=status[3], para=status[4] or "…", q=status[5])
                if len(status) >= 6 else False)
            registro.ultimo_log = _ler(os.path.join(pasta, "ultimo.log"))[-6000:] or False
            registro.contas_abertas = sessoes

    # ------------------------------------------------------------------
    def _gravar_pedido(self, acao, imagem=False):
        pasta = self._pasta()
        if not os.path.isdir(pasta):
            raise UserError(_("A pasta de atualização (%s) não existe neste servidor. "
                              "Rode 'sudo ./instalar.sh' no servidor Linux para ativar a atualização pela tela.", pasta))
        destino = os.path.join(pasta, "pedido.txt")
        if os.path.exists(destino):
            raise UserError(_("Já existe um pedido esperando o servidor. Aguarde um instante e atualize a tela."))
        temporario = destino + ".tmp"
        with open(temporario, "w", encoding="utf-8") as arquivo:
            arquivo.write("%s\n%s\n%s\n" % (acao, "1" if imagem else "0", self.env.user.login))
        os.replace(temporario, destino)  # o agente nunca vê o pedido pela metade

    def _reabrir(self):
        return {"type": "ir.actions.act_window", "res_model": self._name, "view_mode": "form", "target": "current",
                "name": _("Atualizar sistema")}

    def action_verificar(self):
        self._gravar_pedido("verificar")
        return self._reabrir()

    def action_atualizar(self):
        self.ensure_one()
        if not self.env.user.has_group("boteco_base.group_dono"):
            raise UserError(_("Só o dono pode atualizar o sistema."))
        if not self.confirmo:
            raise UserError(_("Marque 'Entendi: o sistema fica fora do ar por alguns minutos' para continuar."))
        if self.contas_abertas:
            raise UserError(_(
                "Há %s caixa(s) aberto(s). Feche os caixas antes de atualizar: durante a atualização o "
                "sistema fica fora do ar e os tablets e o PDV param.", self.contas_abertas))
        if self.estado in ("pedido", "em_andamento"):
            raise UserError(_("Já tem uma atualização em andamento."))
        self._gravar_pedido("atualizar", self.atualizar_imagem)
        self.env["boteco.auditoria"].registrar(
            "atualizacao", descricao=_("Atualização do sistema pedida pela tela (%s versão(ões) nova(s))", self.quantidade),
            valor_antigo=(self.versao_atual or "")[:7])
        return {
            "type": "ir.actions.client", "tag": "display_notification",
            "params": {
                "title": _("Atualização pedida"),
                "message": _("Em alguns segundos o sistema sai do ar para atualizar (uns 5 minutos). "
                             "Depois, abra de novo esta tela para ver o resultado."),
                "type": "warning", "sticky": True,
                "next": self._reabrir(),
            },
        }

    @api.model
    def action_abrir(self):
        return self._reabrir()
