import json
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.boteco_pos.models.pos_order import CAMPOS_SERVIDOR_PEDIDO

from . import quarentena

STATUS_APROVACAO = [
    ("aguardando", "Aguardando liberação"),
    ("aprovado", "Liberado"),
    ("rejeitado", "Recusado"),
]
# Quarentena é decidida só pelo servidor: o que a tela devolver é ignorado
CAMPOS_SERVIDOR_PEDIDO.update({
    "boteco_status_aprovacao", "boteco_motivos_retencao", "boteco_retido_em", "boteco_aprovado_por_id",
})


class PosOrder(models.Model):
    _inherit = "pos.order"

    boteco_aguardando_garcom = fields.Boolean("Esperando o garçom (+18)", copy=False, index=True,
                                              help="Primeiro pedido com álcool da mesa: só vai para a produção depois que o "
                                              "garçom conferir a idade.")
    # Inteiro (não Many2one): o PDV carrega todos os campos do pedido e não conhece este modelo
    boteco_dispositivo_ref = fields.Integer("Aparelho (id)", copy=False, readonly=True)
    # Etapa 14: quarentena de pedidos fora do padrão (nunca vão à produção sem liberação humana)
    boteco_status_aprovacao = fields.Selection(STATUS_APROVACAO, string="Conferência do pedido", copy=False,
                                               index=True, readonly=True)
    boteco_motivos_retencao = fields.Text("Por que foi retido", copy=False, readonly=True)
    boteco_retido_em = fields.Datetime("Retido em", copy=False, readonly=True)
    boteco_aprovado_por_id = fields.Many2one("res.users", string="Resolvido por", copy=False, readonly=True)

    def _boteco_tem_alcool(self):
        self.ensure_one()
        return any(l.product_id.boteco_maior_18 and l.qty > 0 for l in self.lines)

    def _boteco_pos_autoatendimento(self, dispositivo):
        """Depois que o pedido do tablet/QR é gravado: origem, quarentena, +18 e envio à produção."""
        for pedido in self.sudo():
            mesa = pedido.table_id
            pedido.write({"boteco_origem": "tablet" if dispositivo.tipo == "tablet" else "qr",
                          "boteco_dispositivo_ref": dispositivo.id})
            if mesa:
                mesa._boteco_garantir_sessao()
            motivos = pedido._boteco_avaliar_quarentena()
            if motivos:
                pedido._boteco_reter(motivos)
                continue
            if pedido.boteco_status_aprovacao == "aguardando":
                continue  # já retido num envio anterior: espera a liberação
            pedido._boteco_seguir_para_producao()
        return True

    def _boteco_seguir_para_producao(self):
        """Fluxo normal depois da conferência: +18 (se for o caso) ou direto para a produção."""
        for pedido in self:
            mesa = pedido.table_id
            reter = bool(mesa) and pedido._boteco_tem_alcool() and not mesa.boteco_maior18_confirmado
            pedido.write({"boteco_aguardando_garcom": reter})
            if reter:
                for config in mesa.floor_id.pos_config_ids:
                    if config.current_session_id:
                        config._notify("BOTECO_MAIOR18", {"mesa_id": mesa.id, "mesa": mesa.table_number, "pedido_id": pedido.id})
            else:
                pedido.boteco_marcar_enviado()

    # ------------------------------------------------------------------
    # Motor N+X (Etapa 14)
    # ------------------------------------------------------------------
    def _boteco_itens_novos(self):
        """O que este envio acrescenta (ainda não foi para a produção), agrupado por produto."""
        self.ensure_one()
        itens = {}
        for linha in self.lines:
            delta = linha.qty - (linha.boteco_qtd_enviada or 0.0)
            if delta <= 0:
                continue
            produto = linha.product_id
            item = itens.setdefault(produto.id, {
                "produto_id": produto.id, "nome": produto.name, "tipo": produto.boteco_tipo_consumo or "outro",
                "serve": produto.boteco_serve_pessoas or 1, "max_rodada": produto.boteco_max_por_rodada_sku or 0,
                "qtd": 0.0, "valor": 0.0, "linhas": [],
            })
            item["qtd"] += delta
            item["valor"] += linha.price_subtotal_incl * delta / linha.qty if linha.qty else 0.0
            item["linhas"].append({"id": linha.id, "qtd": linha.qty, "enviada": linha.boteco_qtd_enviada or 0.0})
        return list(itens.values())

    def _boteco_pratos_recentes(self, mesa):
        """Equivalente em pratos já enviado à produção na mesa (e mesas juntadas) nos últimos 45 min."""
        desde = fields.Datetime.now() - timedelta(minutes=quarentena.MINUTOS_SATURACAO)
        linhas = self.env["pos.order.line"].sudo().search([
            ("order_id.table_id", "in", mesa._boteco_grupo().ids), ("order_id.state", "=", "draft"),
            ("boteco_qtd_enviada", ">", 0), ("create_date", ">=", desde),
            ("product_id.boteco_tipo_consumo", "in", quarentena.PRATOS),
        ])
        return sum(quarentena.peso_prato({"tipo": l.product_id.boteco_tipo_consumo, "qtd": l.boteco_qtd_enviada,
                                          "serve": l.product_id.boteco_serve_pessoas}) for l in linhas)

    @api.model
    def _boteco_tickets_historicos(self, company):
        """R$ por pessoa das contas fechadas nos últimos 90 dias (base do Z-Score)."""
        desde = fields.Datetime.now() - timedelta(days=90)
        self.env.cr.execute(
            """
            SELECT amount_total / GREATEST(customer_count, 1)
              FROM pos_order
             WHERE company_id = %s AND state IN ('paid', 'done', 'invoiced')
               AND date_order >= %s AND amount_total > 0
            """,
            (company.id, desde),
        )
        return [float(r[0]) for r in self.env.cr.fetchall()]

    def _boteco_avaliar_quarentena(self):
        """Lista de motivos para reter o envio (vazia = segue normal). Respeita a Central de Recursos."""
        self.ensure_one()
        company = self.company_id
        mesa = self.table_id
        if not mesa or not company.boteco_recurso_ativo("quarentena_pedidos_anomalos"):
            return []
        itens = self._boteco_itens_novos()
        if not itens:
            return []
        n = mesa.boteco_n_clientes()
        motivos = quarentena.avaliar_regras_volume(itens, n, self._boteco_pratos_recentes(mesa))
        if company.boteco_recurso_ativo("validacao_zscore_ticket"):
            motivo = quarentena.avaliar_ticket(sum(i["valor"] for i in itens), n,
                                               self._boteco_tickets_historicos(company))
            if motivo:
                motivos.append(motivo)
        return motivos

    def _boteco_dados_quarentena(self):
        self.ensure_one()
        mesa = self.table_id
        return {
            "pedido_id": self.id,
            "mesa_id": mesa.id,
            "mesa": mesa.table_number,
            "clientes": mesa.boteco_n_clientes() if mesa else 1,
            "motivos": (self.boteco_motivos_retencao or "").splitlines(),
            "itens": [
                {"produto_id": i["produto_id"], "nome": i["nome"], "qtd": i["qtd"], "linhas": i["linhas"]}
                for i in self._boteco_itens_novos()
            ],
        }

    def _boteco_avisar_quarentena(self, evento, extra=None):
        """Avisa todos os PDVs abertos do salão (garçons e caixas) em tempo real."""
        for pedido in self:
            configs = pedido.table_id.floor_id.pos_config_ids or pedido.config_id
            for config in configs:
                if config.current_session_id:
                    config._notify(evento, {**pedido._boteco_dados_quarentena(), **(extra or {})})

    def _boteco_reter(self, motivos):
        for pedido in self:
            pedido.write({
                "boteco_status_aprovacao": "aguardando",
                "boteco_motivos_retencao": "\n".join(motivos),
                "boteco_retido_em": fields.Datetime.now(),
                "boteco_aprovado_por_id": False,
            })
            pedido._boteco_avisar_quarentena("BOTECO_PEDIDO_RETIDO")

    def _boteco_processar_envio(self):
        # Pedido em quarentena nunca vai para a produção, mesmo que algum PDV tente mandar
        return super(PosOrder, self.filtered(lambda p: p.boteco_status_aprovacao != "aguardando"))._boteco_processar_envio()

    # ------------------------------------------------------------------
    # Resolução pelo garçom/caixa (o primeiro que tocar resolve; os outros alertas fecham)
    # ------------------------------------------------------------------
    def _boteco_travar_retido(self):
        """Trava a linha do pedido no banco: dois garçons tocando ao mesmo tempo não liberam duas vezes."""
        self.ensure_one()
        if not self.env.user.boteco_pode("pode_aprovar_qr"):
            raise UserError(_("Você não pode liberar pedidos do tablet. Chame o gerente."))
        self.env.cr.execute("SELECT id FROM pos_order WHERE id = %s FOR UPDATE", (self.id,))
        self.invalidate_recordset(["boteco_status_aprovacao", "boteco_aprovado_por_id"])
        if self.boteco_status_aprovacao != "aguardando":
            quem = self.boteco_aprovado_por_id.name or _("outra pessoa")
            raise UserError(_("Este pedido já foi resolvido por %s.", quem))
        return self.sudo()

    def _boteco_finalizar_resolucao(self, status, descricao, detalhe=None):
        pedido = self.sudo()
        pedido.write({"boteco_status_aprovacao": status, "boteco_aprovado_por_id": self.env.user.id})
        self.env["boteco.auditoria"].registrar(
            "aprovacao_qr", registro=pedido, descricao=descricao, referencia=pedido.uuid,
            motivo=pedido.boteco_motivos_retencao, detalhe=detalhe)
        if status == "aprovado":
            pedido._boteco_seguir_para_producao()
        pedido._boteco_avisar_quarentena("BOTECO_ANOMALIA_RESOLVIDA",
                                         {"status": status, "resolvido_por": self.env.user.name})
        return True

    def action_boteco_ajustar_clientes_e_aprovar(self, nova_qtd_clientes):
        pedido = self._boteco_travar_retido()
        antes = pedido.table_id.boteco_n_clientes() if pedido.table_id else 0
        if pedido.table_id:
            pedido.table_id.boteco_definir_clientes(nova_qtd_clientes)
        return self._boteco_finalizar_resolucao(
            "aprovado", _("Pedido do tablet liberado: mesa ajustada de %(a)s para %(d)s pessoa(s)",
                          a=antes, d=nova_qtd_clientes),
            detalhe={"clientes_antes": antes, "clientes_depois": nova_qtd_clientes})

    def action_boteco_corrigir_item_e_aprovar(self, ajustes_linhas):
        """ajustes_linhas: {id_da_linha: nova_quantidade_total}. Só mexe no que ainda não foi enviado."""
        pedido = self._boteco_travar_retido()
        if isinstance(ajustes_linhas, str):
            ajustes_linhas = json.loads(ajustes_linhas)
        mudancas = []
        for linha_id, nova in (ajustes_linhas or {}).items():
            linha = pedido.lines.filtered(lambda l, i=int(linha_id): l.id == i)
            if not linha:
                continue
            nova = float(nova)
            enviada = linha.boteco_qtd_enviada or 0.0
            if nova < enviada:
                raise UserError(_("%s: não dá para baixar abaixo do que já foi para a produção (%s).",
                                  linha.product_id.name, enviada))
            mudancas.append({"produto": linha.product_id.name, "antes": linha.qty, "depois": nova})
            if nova == 0:
                linha.unlink()
            else:
                linha.write({"qty": nova})
                linha.write(linha._compute_amount_line_all())
        pedido._compute_prices()
        if not pedido.lines:
            pedido._boteco_finalizar_resolucao("rejeitado", _("Pedido do tablet zerado na conferência"),
                                               detalhe={"mudancas": mudancas})
            pedido.write({"state": "cancel"})
            return True
        resumo = ", ".join("%s %g→%g" % (m["produto"], m["antes"], m["depois"]) for m in mudancas)
        return self._boteco_finalizar_resolucao(
            "aprovado", _("Pedido do tablet liberado com correção: %s", resumo or "-"), detalhe={"mudancas": mudancas})

    def action_boteco_aprovar_pedido(self):
        self._boteco_travar_retido()
        return self._boteco_finalizar_resolucao("aprovado", _("Pedido do tablet liberado como exceção"))

    def action_boteco_rejeitar_pedido(self):
        """Recusa: tira o que não foi enviado. O que já estava na produção continua na conta."""
        pedido = self._boteco_travar_retido()
        for linha in pedido.lines:
            enviada = linha.boteco_qtd_enviada or 0.0
            if linha.qty <= enviada:
                continue
            if enviada == 0:
                linha.unlink()
            else:
                linha.write({"qty": enviada})
                linha.write(linha._compute_amount_line_all())
        pedido._compute_prices()
        self._boteco_finalizar_resolucao("rejeitado", _("Pedido do tablet recusado na conferência"))
        if not pedido.lines:
            pedido.write({"state": "cancel"})
        return True

    @api.model
    def boteco_pedidos_retidos(self):
        """Para o PDV que abriu depois: alertas ainda pendentes."""
        retidos = self.sudo().search([("boteco_status_aprovacao", "=", "aguardando"), ("state", "=", "draft"),
                                      ("company_id", "in", self.env.companies.ids)])
        return [p._boteco_dados_quarentena() for p in retidos]

    def _boteco_resumo_mesa(self, mesa):
        """'Minha conta': todas as contas abertas da mesa, com status de cada item."""
        pedidos = self.sudo().search([("table_id", "=", mesa.id), ("state", "=", "draft")])
        status_por_linha = {}
        for pedido in pedidos:
            status_por_linha.update(self.boteco_status_itens(pedido.uuid))
        rotulo = {"aguardando": _("na fila"), "preparando": _("preparando"), "pronto": _("a caminho"),
                  "entregue": _("entregue")}
        config = pedidos[:1].config_id
        taxa_prod = config.boteco_produto_taxa_id
        couvert_prod = config.boteco_produto_couvert_id
        itens, consumo, couvert = [], 0.0, 0.0
        for linha in pedidos.lines.filtered(lambda l: l.qty > 0):
            if linha.product_id == taxa_prod:
                continue
            if linha.product_id == couvert_prod:
                couvert += linha.price_subtotal_incl
                continue
            consumo += linha.price_subtotal_incl
            estado = status_por_linha.get(linha.uuid)
            if linha.order_id.boteco_status_aprovacao == "aguardando" and linha.qty > (linha.boteco_qtd_enviada or 0.0):
                estado_rotulo = _("conferindo com o garçom")
            elif linha.order_id.boteco_aguardando_garcom:
                estado_rotulo = _("esperando o garçom")
            elif estado:
                estado_rotulo = rotulo.get(estado, estado)
            elif linha.product_id.boteco_setor_id:
                estado_rotulo = _("enviado")
            else:
                estado_rotulo = ""
            itens.append({
                "nome": linha.full_product_name or linha.product_id.display_name,
                "quantidade": linha.qty,
                "total": linha.price_subtotal_incl,
                "status": estado_rotulo,
                "product_id": linha.product_id.id,
                "setor": linha.product_id.boteco_setor_id.codigo or "",
            })
        pct = config.boteco_taxa_servico_pct if config else 0.0
        taxa = round(consumo * pct / 100, 2) if pedidos and not all(pedidos.mapped("boteco_taxa_removida")) else 0.0
        if not couvert and config:
            agenda = self.env["boteco.agenda.musica"]._couvert_do_dia(config.company_id)
            pessoas = max(pedidos.mapped("customer_count") or [0]) or 1
            couvert = agenda.valor_couvert * pessoas if agenda else 0.0
        return {
            "itens": itens,
            "em_conferencia": any(p.boteco_status_aprovacao == "aguardando" for p in pedidos),
            "consumo": consumo,
            "taxa": taxa,
            "taxa_pct": pct,
            "couvert": couvert,
            "total": consumo + taxa + couvert,
        }

    @api.model
    def _boteco_bebidas_da_mesa(self, mesa):
        """'Pedir de novo': bebidas (setor bar) já pedidas na mesa, sem repetir."""
        pedidos = self.sudo().search([("table_id", "=", mesa.id), ("state", "=", "draft")])
        vistos, resultado = set(), []
        for linha in pedidos.lines.sorted("id", reverse=True):
            produto = linha.product_id
            if produto.id in vistos or produto.boteco_setor_id.codigo != "bar" or not produto.self_order_available:
                continue
            vistos.add(produto.id)
            resultado.append({"product_id": produto.id, "nome": produto.name})
        return resultado
