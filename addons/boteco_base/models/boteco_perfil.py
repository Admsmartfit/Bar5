from odoo import api, fields, models

# Permissões "liga/desliga" de cada perfil (seção 3 do PRD).
# (campo, rótulo, precisa de PIN do gerente quando o perfil não tem a permissão)
PERMISSOES = [
    ("pode_cancelar_item", "Cancelar item já enviado"),
    ("pode_dar_desconto", "Dar desconto"),
    ("pode_dar_cortesia", "Dar cortesia"),
    ("pode_consumo_funcionario", "Lançar consumo de funcionário"),
    ("pode_remover_taxa", "Tirar taxa de serviço / couvert"),
    ("pode_sangria_reforco", "Sangria e reforço de caixa"),
    ("pode_abrir_fechar_caixa", "Abrir e fechar caixa"),
    ("pode_receber_pagamento", "Receber pagamento"),
    ("pode_aprovar_qr", "Aprovar celular do QR Code"),
    ("pode_ajustar_estoque", "Ajustar estoque / registrar perda"),
    ("pode_alterar_preco", "Alterar preço"),
    ("pode_ver_financeiro", "Ver relatórios financeiros"),
    ("pode_sair_quiosque", "Tirar o tablet da mesa do modo quiosque"),
]
PERMISSOES_DICT = dict(PERMISSOES)

CODIGOS_PERFIL = [
    ("garcom", "Garçom"),
    ("caixa", "Barman / caixa"),
    ("chapeiro", "Chapeiro"),
    ("gerente", "Gerente"),
    ("cozinheiro", "Cozinheiro (cozinha central)"),
    ("comercial", "Comercial B2B"),
    ("dono", "Dono / administrador"),
]


class BotecoPerfil(models.Model):
    _name = "boteco.perfil"
    _description = "Perfil de acesso do boteco"
    _order = "sequence, id"

    name = fields.Char("Perfil", required=True, translate=True)
    codigo = fields.Selection(CODIGOS_PERFIL, required=True)
    sequence = fields.Integer(default=10)
    descricao = fields.Text("O que faz")
    group_id = fields.Many2one(
        "res.groups",
        string="Grupo do Odoo",
        required=True,
        ondelete="restrict",
        help="Grupo que dá os acessos técnicos deste perfil.",
    )
    permite_login_pin = fields.Boolean(
        "Entra com PIN",
        default=True,
        help="Desligado para perfis com acesso total: esses entram com senha.",
    )
    menu_ids = fields.Many2many(
        "ir.ui.menu",
        string="Menus visíveis",
        domain=[("parent_id", "=", False)],
        help="Menus principais que este perfil enxerga. Vazio = todos os que o grupo permite.",
    )
    user_ids = fields.One2many("res.users", "boteco_perfil_id", string="Pessoas")
    usuarios_count = fields.Integer(compute="_compute_usuarios_count", string="Pessoas no perfil")
    active = fields.Boolean(default=True)

    pode_cancelar_item = fields.Boolean(PERMISSOES_DICT["pode_cancelar_item"])
    pode_dar_desconto = fields.Boolean(PERMISSOES_DICT["pode_dar_desconto"])
    pode_dar_cortesia = fields.Boolean(PERMISSOES_DICT["pode_dar_cortesia"])
    pode_consumo_funcionario = fields.Boolean(PERMISSOES_DICT["pode_consumo_funcionario"])
    pode_remover_taxa = fields.Boolean(PERMISSOES_DICT["pode_remover_taxa"])
    pode_sangria_reforco = fields.Boolean(PERMISSOES_DICT["pode_sangria_reforco"])
    pode_abrir_fechar_caixa = fields.Boolean(PERMISSOES_DICT["pode_abrir_fechar_caixa"])
    pode_receber_pagamento = fields.Boolean(PERMISSOES_DICT["pode_receber_pagamento"])
    pode_aprovar_qr = fields.Boolean(PERMISSOES_DICT["pode_aprovar_qr"])
    pode_ajustar_estoque = fields.Boolean(PERMISSOES_DICT["pode_ajustar_estoque"])
    pode_alterar_preco = fields.Boolean(PERMISSOES_DICT["pode_alterar_preco"])
    pode_ver_financeiro = fields.Boolean(PERMISSOES_DICT["pode_ver_financeiro"])
    pode_sair_quiosque = fields.Boolean(PERMISSOES_DICT["pode_sair_quiosque"])

    _sql_constraints = [
        ("codigo_unico", "unique(codigo)", "Já existe um perfil com este código."),
    ]

    @api.depends("user_ids")
    def _compute_usuarios_count(self):
        for perfil in self:
            perfil.usuarios_count = len(perfil.user_ids)

    def pode(self, permissao):
        """True se o perfil tem a permissão (nome do campo de PERMISSOES)."""
        self.ensure_one()
        if permissao not in PERMISSOES_DICT:
            raise ValueError("Permissão desconhecida: %s" % permissao)
        return bool(self[permissao])

    def write(self, vals):
        mudou_menus = "menu_ids" in vals
        mudou_grupo = "group_id" in vals
        auditar = {k: v for k, v in vals.items() if k in PERMISSOES_DICT}
        antes = {p.id: {k: p[k] for k in auditar} for p in self} if auditar else {}
        res = super().write(vals)
        if mudou_grupo:
            for perfil in self:
                perfil.user_ids._boteco_aplicar_perfil()
        if mudou_menus or mudou_grupo:
            self.env.registry.clear_cache()
        if auditar:
            Auditoria = self.env["boteco.auditoria"]
            for perfil in self:
                for campo, novo in auditar.items():
                    velho = antes[perfil.id][campo]
                    if bool(velho) != bool(novo):
                        Auditoria.registrar(
                            "permissao",
                            registro=perfil,
                            descricao="%s: %s" % (perfil.name, PERMISSOES_DICT[campo]),
                            valor_antigo="ligado" if velho else "desligado",
                            valor_novo="ligado" if novo else "desligado",
                        )
        return res

    def action_ver_pessoas(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.name,
            "res_model": "res.users",
            "view_mode": "list,form",
            "domain": [("boteco_perfil_id", "=", self.id)],
            "context": {"default_boteco_perfil_id": self.id},
        }
