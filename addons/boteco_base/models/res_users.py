import logging
import re

from passlib.context import CryptContext

from odoo import _, api, fields, models
from odoo.exceptions import AccessDenied, UserError, ValidationError
from odoo.http import request

from .boteco_perfil import PERMISSOES_DICT
from .boteco_pin_tentativa import JANELA_BLOQUEIO_MIN, MAX_TENTATIVAS

_logger = logging.getLogger(__name__)

# PIN tem poucos dígitos: a proteção real é o bloqueio após 5 erros.
# pbkdf2 com 50 mil voltas (~30 ms) evita guardar o PIN em claro sem deixar a tela lenta.
PIN_CRYPT = CryptContext(["pbkdf2_sha256"], pbkdf2_sha256__default_rounds=50000)

PIN_RE = re.compile(r"^\d{4,6}$")

TEMAS = [("claro", "Claro"), ("escuro", "Escuro"), ("auto", "Automático (igual ao aparelho)")]
TAMANHOS_FONTE = [("normal", "Normal"), ("grande", "Grande"), ("maior", "Muito grande")]
CORES_DESTAQUE = [("roxo", "Roxo"), ("azul", "Azul"), ("verde", "Verde"), ("laranja", "Laranja"), ("grafite", "Grafite")]
CAMPOS_APARENCIA = ["boteco_tema", "boteco_alto_contraste", "boteco_tamanho_fonte", "boteco_cor_destaque"]


def pin_trivial(pin):
    """PINs fáceis demais: todos iguais (1111) ou sequência (1234, 4321)."""
    if len(set(pin)) == 1:
        return True
    digitos = [int(c) for c in pin]
    passos = {b - a for a, b in zip(digitos, digitos[1:])}
    return passos in ({1}, {-1})


class ResUsers(models.Model):
    _inherit = "res.users"

    boteco_perfil_id = fields.Many2one(
        "boteco.perfil",
        string="Perfil do boteco",
        index=True,
        help="Define os acessos, a tela inicial e os menus da pessoa.",
    )
    boteco_perfil_codigo = fields.Selection(related="boteco_perfil_id.codigo", string="Código do perfil")
    boteco_pin = fields.Char(
        string="PIN",
        compute="_compute_boteco_pin",
        inverse="_inverse_boteco_pin",
        help="4 a 6 dígitos. Guardado com criptografia: ninguém consegue ver o PIN depois.",
    )
    boteco_pin_hash = fields.Char(copy=False, groups="base.group_system")
    boteco_tem_pin = fields.Boolean(compute="_compute_boteco_tem_pin", string="Tem PIN")
    boteco_pdv_config_id = fields.Many2one(
        "pos.config",
        string="PDV que a pessoa abre",
        help="Ponto de venda aberto automaticamente ao entrar (garçom e caixa).",
    )
    boteco_tour_visto = fields.Boolean("Já viu o tour", copy=False)
    boteco_bloqueado = fields.Boolean(compute="_compute_boteco_bloqueado", string="PIN bloqueado")

    # Aparência do sistema (cada pessoa escolhe a sua, pelo botão de sol/lua na barra de cima)
    boteco_tema = fields.Selection(TEMAS, string="Tema", default="claro", required=True)
    boteco_alto_contraste = fields.Boolean("Alto contraste", default=True,
                                           help="Textos mais escuros e bordas mais fortes: mais fácil de ler.")
    boteco_tamanho_fonte = fields.Selection(TAMANHOS_FONTE, string="Tamanho da letra", default="normal", required=True)
    boteco_cor_destaque = fields.Selection(CORES_DESTAQUE, string="Cor de destaque", default="roxo", required=True)

    @property
    def SELF_READABLE_FIELDS(self):
        return super().SELF_READABLE_FIELDS + ["boteco_perfil_id", "boteco_perfil_codigo", "boteco_tem_pin", "boteco_tour_visto"] + CAMPOS_APARENCIA

    @property
    def SELF_WRITEABLE_FIELDS(self):
        return super().SELF_WRITEABLE_FIELDS + ["boteco_tour_visto"] + CAMPOS_APARENCIA

    def boteco_aparencia(self):
        """Preferências de aparência que a tela aplica ao abrir."""
        self.ensure_one()
        return {
            "tema": self.boteco_tema or "claro",
            "alto_contraste": self.boteco_alto_contraste,
            "fonte": self.boteco_tamanho_fonte or "normal",
            "cor": self.boteco_cor_destaque or "roxo",
        }

    # ------------------------------------------------------------------
    # Campos calculados
    # ------------------------------------------------------------------
    def _compute_boteco_pin(self):
        for user in self:
            user.boteco_pin = False

    def _compute_boteco_tem_pin(self):
        com_pin = set(
            self.sudo().filtered(lambda u: u.boteco_pin_hash).ids
        )
        for user in self:
            user.boteco_tem_pin = user.id in com_pin

    def _compute_boteco_bloqueado(self):
        Tentativa = self.env["boteco.pin.tentativa"]
        for user in self:
            user.boteco_bloqueado = bool(user.id) and Tentativa._bloqueado(user.id, "login")

    def _inverse_boteco_pin(self):
        for user in self:
            if user.boteco_pin:
                user._boteco_definir_pin(user.boteco_pin)

    # ------------------------------------------------------------------
    # PIN
    # ------------------------------------------------------------------
    def _boteco_definir_pin(self, pin):
        self.ensure_one()
        pin = (pin or "").strip()
        if not PIN_RE.match(pin):
            raise ValidationError(_("O PIN precisa ter de 4 a 6 números."))
        if pin_trivial(pin):
            raise ValidationError(_("PIN fácil demais (ex.: 1111 ou 1234). Escolha outro."))
        # PIN único: o PIN do gerente identifica quem autorizou
        outros = self.sudo().search([("id", "!=", self.id), ("boteco_pin_hash", "!=", False)])
        for outro in outros:
            if PIN_CRYPT.verify(pin, outro.boteco_pin_hash):
                raise ValidationError(_("Este PIN já é usado por outra pessoa. Escolha outro."))
        self.sudo().boteco_pin_hash = PIN_CRYPT.hash(pin)
        self.env["boteco.auditoria"].registrar(
            "pin_alterado", registro=self, descricao=_("PIN definido para %s", self.name)
        )

    def _boteco_pin_confere(self, pin):
        self.ensure_one()
        hash_ = self.sudo().boteco_pin_hash
        if not hash_ or not pin:
            return False
        try:
            return PIN_CRYPT.verify(str(pin), hash_)
        except (ValueError, TypeError):
            return False

    def action_boteco_desbloquear_pin(self):
        """Gerente/dono libera a pessoa bloqueada por erros de PIN."""
        Tentativa = self.env["boteco.pin.tentativa"].sudo()
        for user in self:
            Tentativa.create({"user_id": user.id, "tipo": "login", "sucesso": True, "ip": "desbloqueio"})
            Tentativa.create({"user_id": user.id, "tipo": "autorizacao", "sucesso": True, "ip": "desbloqueio"})
            self.env["boteco.auditoria"].registrar(
                "pin_desbloqueado", registro=user, descricao=_("PIN desbloqueado: %s", user.name)
            )
        return True

    @api.model
    def _boteco_ip(self):
        try:
            return request.httprequest.remote_addr if request else None
        except RuntimeError:
            return None

    def _check_credentials(self, credential, env):
        if credential.get("type") != "boteco_pin":
            return super()._check_credentials(credential, env)
        user = self.env.user
        Tentativa = self.env["boteco.pin.tentativa"]
        ip = self._boteco_ip()
        if not user.boteco_perfil_id or not user.boteco_perfil_id.permite_login_pin:
            raise AccessDenied(_("Esta pessoa entra com senha, não com PIN."))
        if Tentativa._bloqueado(user.id, "login"):
            raise AccessDenied(
                _("PIN bloqueado por %s minutos depois de %s erros. Chame o gerente.")
                % (JANELA_BLOQUEIO_MIN, MAX_TENTATIVAS)
            )
        if not user._boteco_pin_confere(credential.get("pin")):
            # Conta antes de gravar: a gravação é num cursor separado, que esta transação não enxerga
            restantes = MAX_TENTATIVAS - Tentativa._falhas_recentes(user.id, "login") - 1
            Tentativa._registrar_isolado(user.id, "login", False, ip)
            if restantes <= 0:
                raise AccessDenied(_("PIN bloqueado por %s minutos. Chame o gerente.") % JANELA_BLOQUEIO_MIN)
            raise AccessDenied(_("PIN errado. Restam %s tentativas.") % restantes)
        Tentativa._registrar_isolado(user.id, "login", True, ip)
        return {"uid": user.id, "auth_method": "boteco_pin", "mfa": "skip"}

    # ------------------------------------------------------------------
    # Perfil
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        users = super().create(vals_list)
        users.filtered("boteco_perfil_id")._boteco_aplicar_perfil()
        return users

    def write(self, vals):
        res = super().write(vals)
        if "boteco_perfil_id" in vals:
            self._boteco_aplicar_perfil()
            for user in self:
                self.env["boteco.auditoria"].registrar(
                    "perfil_alterado",
                    registro=user,
                    descricao=_("Perfil de %s", user.name),
                    valor_novo=user.boteco_perfil_id.name or "",
                )
        return res

    def _boteco_aplicar_perfil(self):
        """O perfil define TODOS os acessos da pessoa (grupos e tela inicial)."""
        acao_inicio = self.env.ref("boteco_base.action_boteco_inicio", raise_if_not_found=False)
        grupo_interno = self.env.ref("base.group_user")
        for user in self:
            if user._is_superuser() or user.share or not user.boteco_perfil_id:
                continue
            perfil = user.boteco_perfil_id
            vals = {"groups_id": [fields.Command.set([grupo_interno.id, perfil.group_id.id])]}
            if acao_inicio:
                vals["action_id"] = acao_inicio.id
            super(ResUsers, user.sudo()).write(vals)
        self.env.registry.clear_cache()

    def boteco_pode(self, permissao):
        """True se a pessoa tem a permissão pelo perfil. Superusuário pode tudo."""
        self.ensure_one()
        if permissao not in PERMISSOES_DICT:
            raise UserError(_("Permissão desconhecida: %s", permissao))
        if self._is_superuser() or self.has_group("boteco_base.group_dono"):
            return True
        return bool(self.boteco_perfil_id and self.boteco_perfil_id.pode(permissao))

    def _boteco_url_inicio(self):
        """URL da tela de trabalho da pessoa. Outros módulos boteco_* completam por perfil."""
        self.ensure_one()
        codigo = self.boteco_perfil_id.codigo
        if codigo in ("garcom", "caixa") and self.boteco_pdv_config_id:
            return "/pos/ui?config_id=%s" % self.boteco_pdv_config_id.id
        if codigo in ("garcom", "caixa"):
            config = self.env["pos.config"].search([("company_id", "=", self.env.company.id)], limit=1)
            if config:
                return "/pos/ui?config_id=%s" % config.id
        if codigo == "gerente":
            return "/odoo/action-point_of_sale.action_pos_config_kanban"
        if codigo == "cozinheiro":
            return "/odoo/action-mrp.mrp_production_action"
        if codigo == "comercial":
            return "/odoo/action-sale.action_orders"
        if codigo == "dono":
            return "/odoo/action-boteco_base.action_boteco_auditoria"
        return "/odoo/action-point_of_sale.action_pos_config_kanban"

    @api.model
    def boteco_usuarios_pin(self):
        """Pessoas que aparecem na tela de PIN (nome, iniciais, perfil). Sem dados sensíveis."""
        users = self.sudo().search(
            [
                ("share", "=", False),
                ("boteco_perfil_id.permite_login_pin", "=", True),
                ("boteco_pin_hash", "!=", False),
            ],
            order="name",
        )
        return [
            {
                "id": u.id,
                "nome": u.name,
                "iniciais": "".join(p[0] for p in (u.name or "?").split()[:2]).upper(),
                "perfil": u.boteco_perfil_id.name,
                "codigo_perfil": u.boteco_perfil_id.codigo,
                "login": u.login,
            }
            for u in users
        ]
