import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.boteco_base.models.boteco_perfil import PERMISSOES

_logger = logging.getLogger(__name__)


class PosSession(models.Model):
    _inherit = "pos.session"

    boteco_fechamento_ids = fields.One2many("boteco.fechamento.caixa", "session_id", string="Contagens de fechamento")

    # ------------------------------------------------------------------
    # Dados enviados ao PDV ao abrir
    # ------------------------------------------------------------------
    def _boteco_dados_pdv(self):
        """Tudo o que as telas do boteco precisam: permissões, motivos, couvert, taxa..."""
        self.ensure_one()
        user = self.env.user
        config = self.config_id
        couvert = self.env["boteco.agenda.musica"]._couvert_do_dia(config.company_id)
        motivos = self.env["boteco.motivo"].sudo().search([])
        funcionarios = self.env["res.users"].sudo().search(
            [("share", "=", False), ("boteco_perfil_id", "!=", False)], order="name"
        )
        return {
            "permissoes": {campo: user.boteco_pode(campo) for campo, _rotulo in PERMISSOES},
            "perfil": user.boteco_perfil_id.codigo or ("dono" if user._is_superuser() else False),
            "motivos": [
                {"id": m.id, "nome": m.name, "tipo": m.tipo, "pede_detalhe": m.pede_detalhe} for m in motivos
            ],
            # Central de Recursos: a tela confere as flags antes de cada regra nova
            "recursos": {
                nome[len("boteco_flag_"):]: bool(config.company_id[nome])
                for nome in config.company_id._fields if nome.startswith("boteco_flag_")
            },
            "taxa_pct": config.boteco_taxa_servico_pct,
            "taxa_no_balcao": config.boteco_taxa_no_balcao,
            "produto_taxa_id": config.boteco_produto_taxa_id.id,
            "produto_couvert_id": config.boteco_produto_couvert_id.id,
            "couvert_valor": couvert.valor_couvert if couvert else 0.0,
            "couvert_artista": couvert.artista if couvert else "",
            "minutos_atraso": config.boteco_minutos_atraso or 30,
            "contagem_cega": config.boteco_contagem_cega,
            "funcionarios": [{"id": u.id, "nome": u.name} for u in funcionarios],
        }

    def _load_pos_data(self, data):
        resultado = super()._load_pos_data(data)
        if resultado.get("data"):
            sessao = self.browse(resultado["data"][0]["id"])
            resultado["data"][0]["_boteco"] = sessao._boteco_dados_pdv()
            # Sangria/reforço aparece para quem opera caixa; o servidor confere permissão ou PIN
            resultado["data"][0]["_has_cash_move_perm"] = True
        return resultado

    # ------------------------------------------------------------------
    # Autorização genérica (permissão própria ou PIN do gerente já validado)
    # ------------------------------------------------------------------
    def _boteco_exigir(self, permissao, autorizacao_id=None, referencia=None):
        """Retorna quem autorizou. Levanta erro se não tem permissão nem autorização válida."""
        user = self.env.user
        if user.boteco_pode(permissao):
            return user
        autorizacao = self.env["boteco.autorizacao"].consumir(
            permissao, referencia=referencia, autorizacao_id=autorizacao_id
        )
        if not autorizacao:
            raise UserError(_("Esta ação precisa do PIN do gerente. Peça para ele digitar o PIN e tente de novo."))
        return autorizacao.autorizado_por_id

    @api.model
    def boteco_registrar_acao(self, acao, dados):
        """Registra na auditoria ações feitas na tela (ex.: tirar a taxa de serviço).

        dados: {permissao, autorizacao_id, referencia, valor, motivo, descricao}
        """
        permissao = dados.get("permissao")
        autorizado_por = None
        if permissao:
            autorizado_por = self._boteco_exigir(permissao, dados.get("autorizacao_id"))
        self.env["boteco.auditoria"].registrar(
            acao,
            descricao=dados.get("descricao"),
            valor=dados.get("valor") or 0.0,
            motivo=dados.get("motivo"),
            referencia=dados.get("referencia"),
            autorizado_por=autorizado_por,
        )
        return True

    # ------------------------------------------------------------------
    # Abertura, sangria e reforço
    # ------------------------------------------------------------------
    def set_opening_control(self, cashbox_value, notes):
        if not self.env.user.boteco_pode("pode_abrir_fechar_caixa") and not self.env.context.get("boteco_autorizado"):
            # A abertura do caixa no PDV é feita por quem tem permissão; garçom não abre caixa.
            if self.env.user.has_group("boteco_base.group_garcom") and not self.env.user.has_group("boteco_base.group_caixa"):
                raise UserError(_("Garçom não abre o caixa. Chame o caixa ou o gerente."))
        res = super().set_opening_control(cashbox_value, notes)
        for sessao in self:
            self.env["boteco.auditoria"].registrar(
                "abrir_caixa", registro=sessao, descricao=_("Caixa aberto: %s", sessao.name),
                valor=cashbox_value, motivo=notes or None,
            )
        return res

    def try_cash_in_out(self, _type, amount, reason, extras):
        acao = "reforco" if _type == "in" else "sangria"
        if not (reason or "").strip():
            raise UserError(_("Escreva o motivo da %s.", _("entrada") if _type == "in" else _("retirada")))
        autorizado_por = self._boteco_exigir("pode_sangria_reforco", (extras or {}).get("boteco_autorizacao_id"))
        # O lançamento contábil exige acesso de faturamento, que o caixa não tem: a permissão já foi conferida.
        res = super(PosSession, self.sudo()).try_cash_in_out(_type, amount, reason, extras)
        for sessao in self:
            self.env["boteco.auditoria"].registrar(
                acao, registro=sessao,
                descricao=_("%(acao)s no caixa %(caixa)s", acao=_("Reforço") if _type == "in" else _("Sangria"), caixa=sessao.name),
                valor=amount, motivo=reason, autorizado_por=autorizado_por,
            )
        return res

    # ------------------------------------------------------------------
    # Fechamento
    # ------------------------------------------------------------------
    def _boteco_mesas_abertas(self):
        self.ensure_one()
        abertas = self.get_session_orders().filtered(lambda o: o.state == "draft" and o.lines)
        nomes = []
        for pedido in abertas:
            if pedido.table_id:
                nomes.append(_("Mesa %s", pedido.table_id.table_number))
            else:
                nomes.append(pedido.floating_order_name or pedido.pos_reference or pedido.name)
        return nomes

    def boteco_registrar_contagem(self, contagens, autorizacao_id=None, observacao=None):
        """Contagem cega: grava o que foi contado e só então devolve o esperado e a diferença.

        contagens: {payment_method_id: valor contado}
        """
        self.ensure_one()
        autorizado_por = self._boteco_exigir("pode_abrir_fechar_caixa", autorizacao_id)
        abertas = self._boteco_mesas_abertas()
        if abertas:
            raise UserError(_("Ainda tem conta aberta: %s. Feche todas antes de fechar o caixa.", ", ".join(abertas)))
        dados = self.get_closing_control_data()
        contagens = {int(k): float(v or 0.0) for k, v in (contagens or {}).items()}
        linhas = []
        dinheiro = dados.get("default_cash_details") or {}
        if dinheiro.get("id"):
            linhas.append({
                "payment_method_id": dinheiro["id"], "nome": dinheiro.get("name"), "sequence": 1,
                "esperado": dinheiro.get("amount", 0.0), "contado": contagens.get(dinheiro["id"], 0.0),
            })
        for pm in dados.get("non_cash_payment_methods", []):
            linhas.append({
                "payment_method_id": pm["id"], "nome": pm["name"], "sequence": 10,
                "esperado": pm.get("amount", 0.0), "quantidade": pm.get("number", 0),
                # Cartão/PIX sem contagem digitada: considera o relatório da maquininha igual ao esperado? Não:
                # contagem cega exige digitar; vazio conta como zero para aparecer a diferença.
                "contado": contagens.get(pm["id"], 0.0),
            })
        fechamento = self.env["boteco.fechamento.caixa"].sudo().create({
            "session_id": self.id,
            "dia_operacao": self.config_id.company_id.boteco_dia_operacao(self.start_at or fields.Datetime.now()),
            "operador_id": self.env.user.id,
            "autorizado_por_id": autorizado_por.id,
            "observacao": observacao,
            "linha_ids": [fields.Command.create(v) for v in linhas],
        })
        self.env["boteco.auditoria"].registrar(
            "fechar_caixa", registro=self, descricao=_("Contagem do caixa %s", self.name),
            valor=fechamento.diferenca, valor_antigo="%.2f" % fechamento.total_esperado,
            valor_novo="%.2f" % fechamento.total_contado, autorizado_por=autorizado_por,
            detalhe=[{"forma": l.nome, "esperado": l.esperado, "contado": l.contado, "diferenca": l.diferenca}
                     for l in fechamento.linha_ids],
        )
        return {
            "fechamento_id": fechamento.id,
            "linhas": [
                {"payment_method_id": l.payment_method_id.id, "nome": l.nome, "esperado": l.esperado,
                 "contado": l.contado, "diferenca": l.diferenca}
                for l in fechamento.linha_ids
            ],
            "total_esperado": fechamento.total_esperado,
            "total_contado": fechamento.total_contado,
            "diferenca": fechamento.diferenca,
        }

    def close_session_from_ui(self, bank_payment_method_diff_pairs=None):
        self.ensure_one()
        abertas = self._boteco_mesas_abertas()
        if abertas:
            return {
                "successful": False,
                "message": _("Ainda tem conta aberta: %s. Feche todas antes de fechar o caixa.", ", ".join(abertas)),
                "redirect": False,
            }
        if self.config_id.boteco_contagem_cega and not self.boteco_fechamento_ids and self.order_ids:
            return {
                "successful": False,
                "message": _("Faça a contagem do caixa (contagem cega) antes de fechar."),
                "redirect": False,
            }
        return super().close_session_from_ui(bank_payment_method_diff_pairs)
