import logging
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

ESTADOS = [
    ("aguardando", "Na fila"),
    ("preparando", "Preparando"),
    ("pronto", "Pronto"),
    ("entregue", "Entregue"),
    ("cancelado", "Cancelado"),
]
PROXIMO = {"aguardando": "preparando", "preparando": "pronto", "pronto": "entregue"}
ANTERIOR = {"preparando": "aguardando", "pronto": "preparando", "entregue": "pronto"}
ROTULO_ORIGEM = {"garcom": "GARÇOM", "caixa": "CAIXA", "tablet": "TABLET", "qr": "QR CODE", "qr_bebidas": "QR BEBIDAS"}

MINUTOS_ALERTA_GERENTE = 30


def canal_kds(company_id):
    return "boteco_kds_%s" % company_id


class BotecoKdsPedido(models.Model):
    """Ticket de produção: um envio de uma conta para um setor (bar ou chapa)."""

    _name = "boteco.kds.pedido"
    _description = "Ticket de produção (KDS)"
    _order = "prioridade desc, criado_em asc, id asc"
    _rec_name = "titulo"

    titulo = fields.Char(compute="_compute_titulo", store=True)
    order_id = fields.Many2one("pos.order", string="Conta", required=True, ondelete="cascade", index=True)
    setor_id = fields.Many2one("boteco.setor", string="Setor", required=True, index=True)
    tipo = fields.Selection([("novo", "Pedido"), ("cancelamento", "Cancelamento")], default="novo", required=True)
    mesa = fields.Char("Mesa")
    origem = fields.Selection(related="order_id.boteco_origem", store=True)
    garcom_id = fields.Many2one("res.users", string="Garçom")
    estado = fields.Selection(ESTADOS, default="aguardando", required=True, index=True)
    criado_em = fields.Datetime(default=fields.Datetime.now, required=True, index=True)
    preparando_em = fields.Datetime()
    pronto_em = fields.Datetime()
    entregue_em = fields.Datetime()
    nota_geral = fields.Char("Observação da conta")
    item_ids = fields.One2many("boteco.kds.item", "pedido_id", string="Itens")
    alerta_enviado = fields.Boolean(copy=False)
    impressoes = fields.Integer(default=0)
    company_id = fields.Many2one(related="order_id.company_id", store=True, index=True)
    minutos_preparo = fields.Float("Minutos até ficar pronto", compute="_compute_minutos", store=True)
    minutos_entrega = fields.Float("Minutos até entregar", compute="_compute_minutos", store=True)
    # Etapa 15: avisos de utensílios (copos, taças, pratos) e Hold & Fire de sobremesa
    avisos = fields.Text("Avisos no ticket", help="Um aviso por linha, impresso em destaque.")
    segundo_tempo = fields.Boolean("2º tempo", help="Sobremesa pedida junto com prato principal: "
                                   "só preparar quando o prato principal sair.")
    segundo_tempo_liberado = fields.Boolean("2º tempo liberado", copy=False)
    # Etapa 21 (pacing): prato rápido espera para sair junto com o demorado da mesma mesa
    iniciar_apos = fields.Datetime("Começar a partir de")
    # Auditoria (KDS "Fire"): caixa/gerente passa um pedido na frente da fila, com motivo registrado
    prioridade = fields.Boolean("Prioridade", copy=False, index=True)
    prioridade_motivo = fields.Char("Por que passou na frente", copy=False)
    prioridade_por_id = fields.Many2one("res.users", string="Priorizado por", copy=False)

    @api.depends("mesa", "setor_id", "order_id")
    def _compute_titulo(self):
        for t in self:
            t.titulo = "%s – %s" % (t.setor_id.name or "", t.mesa or t.order_id.pos_reference or "")

    @api.depends("criado_em", "pronto_em", "entregue_em")
    def _compute_minutos(self):
        for t in self:
            t.minutos_preparo = (t.pronto_em - t.criado_em).total_seconds() / 60 if t.pronto_em and t.criado_em else 0.0
            t.minutos_entrega = (t.entregue_em - t.criado_em).total_seconds() / 60 if t.entregue_em and t.criado_em else 0.0

    # ------------------------------------------------------------------
    # Criação a partir do envio do PDV
    # ------------------------------------------------------------------
    @api.model
    def _criar_dos_envios(self, pedido, mudancas):
        """Agrupa as mudanças por setor e cria um ticket para cada (pedido e cancelamento)."""
        Produto = self.env["product.product"].sudo()
        company = pedido.company_id
        produtos = {m.get("produto_id"): Produto.browse(m.get("produto_id")).exists() for m in mudancas}
        segurar = company.boteco_recurso_ativo("hold_fire_sobremesa_2_tempo") and self._tem_prato_principal(pedido, mudancas, produtos)
        grupos = {}
        for mudanca in mudancas:
            produto = produtos[mudanca.get("produto_id")]
            setor = produto.boteco_setor_id
            if not setor:
                continue
            tipo = "novo" if mudanca["quantidade"] > 0 else "cancelamento"
            segundo = tipo == "novo" and segurar and produto.boteco_tipo_consumo == "sobremesa"
            grupos.setdefault((setor, tipo, segundo), []).append((produto, mudanca))
        mesa = (_("Mesa %s", pedido.table_id.table_number) if pedido.table_id
                else pedido.floating_order_name or _("Balcão"))
        tickets = self.browse()
        for (setor, tipo, segundo), itens in grupos.items():
            avisos = self._avisos_utensilios(pedido, [p for p, _m in itens]) if tipo == "novo" else []
            if segundo:
                avisos.insert(0, _("*** 2º TEMPO: SÓ PREPARAR QUANDO O PRATO PRINCIPAL SAIR ***"))
            ticket = self.sudo().create({
                "order_id": pedido.id,
                "setor_id": setor.id,
                "tipo": tipo,
                "mesa": mesa,
                "garcom_id": pedido.user_id.id,
                "nota_geral": pedido.general_note or False,
                "avisos": "\n".join(avisos) or False,
                "segundo_tempo": segundo,
                "estado": "aguardando" if tipo == "novo" else "pronto",
                "item_ids": [
                    fields.Command.create({
                        "product_id": produto.id,
                        # Com adicionais, o nome vem "Batata (Cheddar)": usa o nome puro e mostra os adicionais à parte
                        "nome": (produto.name if mudanca.get("atributos") else mudanca.get("nome")) or produto.name,
                        "quantidade": abs(mudanca["quantidade"]),
                        "nota": mudanca.get("nota") or False,
                        "atributos": ", ".join(a for a in mudanca.get("atributos") or [] if a) or False,
                        "line_uuid": mudanca.get("uuid"),
                        "maior_18": produto.boteco_maior_18,
                    })
                    for produto, mudanca in itens
                ],
            })
            tickets |= ticket
        if company.boteco_recurso_ativo("kds_totalizador_pacing"):
            tickets._aplicar_pacing()
        for ticket in tickets:
            ticket._imprimir()
        if tickets:
            tickets._avisar_telas("novo")
        return tickets

    # ------------------------------------------------------------------
    # Etapa 21: pacing entre praças e totalizador de grelha
    # ------------------------------------------------------------------
    def _tempo_preparo(self):
        self.ensure_one()
        return max([i.product_id.boteco_tempo_preparo or 0 for i in self.item_ids] or [0])

    def _aplicar_pacing(self):
        """No mesmo envio, cada praça começa de modo que tudo fique pronto junto com o item mais demorado."""
        novos = self.filtered(lambda t: t.tipo == "novo" and not t.segundo_tempo)
        if len(novos) < 2:
            return
        tempos = {t: t._tempo_preparo() for t in novos}
        maior = max(tempos.values())
        for ticket, tempo in tempos.items():
            if tempo and tempo < maior:
                ticket.iniciar_apos = ticket.criado_em + timedelta(minutes=maior - tempo)
                aviso = _("PACING: começar às %s", self._hora_local(ticket.iniciar_apos))
                ticket.avisos = "\n".join(filter(None, [aviso, ticket.avisos]))

    @api.model
    def _hora_local(self, momento):
        tz = self.env.company._boteco_tz()
        return fields.Datetime.context_timestamp(self.with_context(tz=tz.zone), momento).strftime("%H:%M")

    # ------------------------------------------------------------------
    # Etapa 15: utensílios na impressão e Hold & Fire
    # ------------------------------------------------------------------
    @api.model
    def _n_clientes(self, pedido):
        if pedido.table_id:
            return pedido.table_id.boteco_n_clientes()
        return max(pedido.customer_count or 1, 1)

    @api.model
    def _tem_prato_principal(self, pedido, mudancas, produtos):
        """Prato principal no mesmo envio ou ainda sendo preparado para a mesa/conta."""
        pratos = ("prato_individual", "prato_compartilhado")
        if any(m["quantidade"] > 0 and produtos[m.get("produto_id")].boteco_tipo_consumo in pratos for m in mudancas):
            return True
        dominio = [("pedido_id.tipo", "=", "novo"), ("estado", "in", ("aguardando", "preparando")),
                   ("pedido_id.segundo_tempo", "=", False), ("product_id.boteco_tipo_consumo", "in", pratos)]
        if pedido.table_id:
            dominio.append(("pedido_id.order_id.table_id", "in", pedido.table_id._boteco_grupo().ids))
        else:
            dominio.append(("pedido_id.order_id", "=", pedido.id))
        return bool(self.env["boteco.kds.item"].sudo().search_count(dominio, limit=1))

    @api.model
    def _avisos_utensilios(self, pedido, produtos):
        """Avisos impressos em destaque no ticket, conforme a Central de Recursos."""
        company = pedido.company_id
        mesa = pedido.table_id.sudo()
        regras = {p.boteco_regra_utensilio for p in produtos if p.boteco_regra_utensilio}
        if not regras:
            return []
        n = self._n_clientes(pedido)
        avisos = []
        if "copo_cerveja" in regras and company.boteco_recurso_ativo("insumo_copos_primeira_cerveja"):
            levados = mesa.boteco_copos_enviados if mesa else 0
            if not levados:
                avisos.append(_(">>> 1º PEDIDO DE CERVEJA DA MESA - LEVAR %s COPOS / TULIPAS <<<", n))
            elif n > levados:
                avisos.append(_(">>> CHEGARAM +%(d)s CLIENTES NA MESA - LEVAR +%(d)s COPOS EXTRAS <<<", d=n - levados))
            if mesa and n > levados:
                mesa.boteco_copos_enviados = n
        vinho = regras & {"taca_vinho", "taca_vinho_gelo"}
        if vinho and company.boteco_recurso_ativo("correlacao_vinho_agua"):
            levadas = mesa.boteco_tacas_enviadas if mesa else 0
            if not levadas:
                texto = _(">>> ENVIAR %s TAÇAS DE VINHO + SACA-ROLHAS", n)
            elif n > levadas:
                texto = _(">>> ENVIAR +%s TAÇAS DE VINHO + SACA-ROLHAS", n - levadas)
            else:
                texto = _(">>> ENVIAR SACA-ROLHAS")
            if "taca_vinho_gelo" in vinho:
                texto += _(" + BALDE COM GELO E ÁGUA")
            avisos.append(texto + " <<<")
            if mesa and n > levadas:
                mesa.boteco_tacas_enviadas = n
            self._alertar_vinho_sem_agua(pedido)
        if "pratos_compartilhados" in regras and company.boteco_recurso_ativo("insumo_pratos_compartilhados"):
            avisos.append(_(">>> MONTAR C/ %(n)s PRATOS RASOS QUENTES + %(n)s KITS TALHERES + PEGADOR <<<", n=n))
        if "guardanapo_reforcado" in regras and company.boteco_recurso_ativo("insumo_pratos_compartilhados"):
            avisos.append(_(">>> ENVIAR CESTA DE GUARDANAPOS REFORÇADA + SACHÊS p/ %s PESSOAS <<<", n))
        return avisos

    @api.model
    def _alertar_vinho_sem_agua(self, pedido):
        """Mesa pediu vinho e não tem água mineral na conta: o garçom recebe o aviso para oferecer."""
        if pedido.table_id:
            contas = self.env["pos.order"].sudo().search([("table_id", "in", pedido.table_id._boteco_grupo().ids),
                                                          ("state", "=", "draft")])
        else:
            contas = pedido
        if any(l.qty > 0 and l.product_id.boteco_tipo_consumo == "agua" for l in contas.lines):
            return False
        local = _("Mesa %s", pedido.table_id.table_number) if pedido.table_id else (pedido.floating_order_name or _("Balcão"))
        mensagem = _("🍷 %s pediu vinho e está sem água. Ofereça água mineral!", local)
        configs = pedido.table_id.floor_id.pos_config_ids if pedido.table_id else pedido.config_id
        for config in configs:
            if config.current_session_id:
                config._notify("BOTECO_ALERTA", {"mensagem": mensagem, "tipo": "vinho_sem_agua"})
        return True

    def _liberar_segundo_tempo(self):
        """Prato principal ficou pronto: libera as sobremesas seguradas da mesma mesa."""
        for ticket in self.filtered(lambda t: not t.segundo_tempo and t.tipo == "novo"):
            pedido = ticket.order_id
            dominio = [("segundo_tempo", "=", True), ("segundo_tempo_liberado", "=", False),
                       ("estado", "=", "aguardando")]
            if pedido.table_id:
                dominio.append(("order_id.table_id", "in", pedido.table_id._boteco_grupo().ids))
            else:
                dominio.append(("order_id", "=", pedido.id))
            segurados = self.search(dominio)
            if not segurados:
                continue
            # Só libera quando não sobrou prato principal em preparo
            if self._tem_prato_principal(pedido, [], {}):
                continue
            segurados.write({"segundo_tempo_liberado": True})
            segurados._avisar_telas("segundo_tempo")

    # ------------------------------------------------------------------
    # Ticket impresso (ESC/POS)
    # ------------------------------------------------------------------
    def _montar_ticket(self, impressora):
        self.ensure_one()
        agora_local = self.env["res.company"].boteco_agora_local()
        t = impressora.novo_ticket()
        if self.tipo == "cancelamento":
            t.texto("*** CANCELAMENTO ***", tamanho=2, negrito=True, alinhar="centro", inverso=True)
        t.texto(self.setor_id.name.upper(), tamanho=1, negrito=True, alinhar="centro")
        t.texto(self.mesa or "", tamanho=3, negrito=True, alinhar="centro")
        t.colunas_texto(agora_local.strftime("%H:%M"), ROTULO_ORIGEM.get(self.origem or "garcom", ""), negrito=True)
        if self.garcom_id:
            t.texto(_("Garçom: %s", self.garcom_id.name.split(" ")[0]))
        t.separador("=")
        for aviso in (self.avisos or "").splitlines():
            t.texto(aviso, negrito=True, inverso=True)
        if self.avisos:
            t.separador("=")
        for item in self.item_ids:
            quantidade = int(item.quantidade) if item.quantidade == int(item.quantidade) else item.quantidade
            t.texto("%s x %s" % (quantidade, item.nome), tamanho=2, negrito=True)
            if item.atributos:
                t.texto("   + " + item.atributos, tamanho=1)
            if item.nota:
                t.destaque(">> " + item.nota.upper())
            t.separador("-")
        if self.nota_geral:
            t.destaque("OBS: " + self.nota_geral.upper())
        t.texto(self.order_id.pos_reference or "", alinhar="centro")
        if impressora.bip:
            t.bip(2)
        t.corte()
        return t.bytes()

    def _imprimir(self, reimpressao=False):
        Job = self.env["boteco.impressao.job"]
        for ticket in self:
            impressora = ticket.setor_id.impressora_id
            if not impressora or not impressora.active:
                continue
            descricao = "%s%s" % (ticket.titulo, _(" (reimpressão)") if reimpressao else "")
            Job.enfileirar(impressora, descricao, ticket._montar_ticket(impressora), ticket)
            ticket.sudo().impressoes += 1
        return True

    # ------------------------------------------------------------------
    # Tempo real
    # ------------------------------------------------------------------
    def _dados_tela(self):
        agora = fields.Datetime.now()
        resultado = []
        for t in self:
            resultado.append({
                "id": t.id,
                "mesa": t.mesa,
                "setor": t.setor_id.codigo,
                "tipo": t.tipo,
                "estado": t.estado,
                "origem": t.origem or "garcom",
                "garcom": (t.garcom_id.name or "").split(" ")[0],
                "nota_geral": t.nota_geral or "",
                "criado_em": fields.Datetime.to_string(t.criado_em),
                "segundos": int((agora - t.criado_em).total_seconds()),
                "pronto_em": fields.Datetime.to_string(t.pronto_em) if t.pronto_em else False,
                "avisos": (t.avisos or "").splitlines(),
                "segundo_tempo": t.segundo_tempo and not t.segundo_tempo_liberado,
                "prioridade": t.prioridade,
                "prioridade_motivo": t.prioridade_motivo or "",
                "iniciar_em_segundos": max(int((t.iniciar_apos - agora).total_seconds()), 0) if t.iniciar_apos else 0,
                "itens": [
                    {"id": i.id, "nome": i.nome, "quantidade": i.quantidade, "nota": i.nota or "",
                     "atributos": i.atributos or "", "maior_18": i.maior_18}
                    for i in t.item_ids
                ],
            })
        return resultado

    def _avisar_telas(self, evento):
        Bus = self.env["bus.bus"].sudo()
        for company in self.company_id:
            tickets = self.filtered(lambda t: t.company_id == company)
            Bus._sendone(canal_kds(company.id), "boteco_kds/atualizar",
                         {"evento": evento, "tickets": tickets._dados_tela()})
        if evento == "pronto":
            self._avisar_garcom()

    def _avisar_garcom(self):
        """O PDV do garçom toca e mostra 'pronto para entregar'."""
        for ticket in self:
            config = ticket.order_id.config_id
            if config.current_session_id:
                config._notify("BOTECO_PRONTO", {
                    "ticket_id": ticket.id,
                    "mesa": ticket.mesa,
                    "setor": ticket.setor_id.name,
                    "itens": ["%s x %s" % (i.quantidade, i.nome) for i in ticket.item_ids],
                    "garcom_id": ticket.garcom_id.id,
                })

    @api.model
    def _avisar_impressora(self, impressoras, voltou=False):
        Bus = self.env["bus.bus"].sudo()
        for impressora in impressoras:
            Bus._sendone(canal_kds(impressora.company_id.id or self.env.company.id), "boteco_kds/impressora", {
                "id": impressora.id,
                "nome": impressora.name,
                "ok": voltou,
                "mensagem": (_("%s voltou. Os tickets que estavam esperando foram impressos.", impressora.name)
                             if voltou else impressora._mensagem_erro()),
            })

    # ------------------------------------------------------------------
    # Ações da tela (toque)
    # ------------------------------------------------------------------
    def _mudar_estado(self, novo):
        agora = fields.Datetime.now()
        carimbo = {"preparando": "preparando_em", "pronto": "pronto_em", "entregue": "entregue_em"}
        for ticket in self:
            vals = {"estado": novo}
            if novo in carimbo and not ticket[carimbo[novo]]:
                vals[carimbo[novo]] = agora
            if novo == "aguardando":
                vals.update(preparando_em=False)
            if novo == "preparando":
                vals.update(pronto_em=False)
            ticket.write(vals)
        self._avisar_telas(novo)
        if novo in ("pronto", "entregue"):
            self._liberar_segundo_tempo()
        return True

    def kds_avancar(self):
        """Toque no cartão: na fila -> preparando -> pronto (-> entregue, pelo garçom)."""
        for ticket in self:
            if ticket.estado in PROXIMO:
                ticket._mudar_estado(PROXIMO[ticket.estado])
        return self._dados_tela()

    def kds_priorizar(self, motivo=None):
        """Passa o ticket na frente da fila (todas as telas do setor). Só caixa e gerente; fica na auditoria."""
        user = self.env.user
        if not (user.has_group("boteco_base.group_gerente") or user.has_group("boteco_base.group_caixa")):
            raise UserError(_("Só o caixa ou o gerente passa um pedido na frente."))
        motivo = (motivo or "").strip() or _("Sem motivo")
        for ticket in self.filtered(lambda t: t.estado in ("aguardando", "preparando")):
            ticket.sudo().write({"prioridade": not ticket.prioridade, "prioridade_motivo": motivo,
                                 "prioridade_por_id": user.id})
            self.env["boteco.auditoria"].registrar(
                "outro", registro=ticket.order_id,
                descricao=_("KDS: %(m)s %(acao)s (%(mot)s)", m=ticket.mesa,
                            acao=_("passou na frente") if ticket.prioridade else _("voltou à ordem normal"), mot=motivo))
        self._avisar_telas("prioridade")
        return self._dados_tela()

    def kds_voltar(self):
        """'Desfazer' de 5 segundos na tela."""
        for ticket in self:
            if ticket.estado in ANTERIOR:
                ticket.with_context(boteco_desfazer=True)._mudar_estado(ANTERIOR[ticket.estado])
        return self._dados_tela()

    def kds_entregar(self):
        self.filtered(lambda t: t.estado in ("aguardando", "preparando", "pronto"))._mudar_estado("entregue")
        return True

    def kds_reimprimir(self):
        if not any(t.setor_id.impressora_id for t in self):
            raise UserError(_("Este setor não tem impressora cadastrada."))
        self._imprimir(reimpressao=True)
        return True

    @api.model
    def kds_dados(self, setor_codigo=None, incluir_prontos_min=3):
        """Tickets abertos de um setor (ou de todos) para montar a tela."""
        domain = [("company_id", "in", self.env.companies.ids), ("tipo", "=", "novo")]
        limite_prontos = fields.Datetime.now() - timedelta(minutes=incluir_prontos_min)
        domain += ["|", ("estado", "in", ("aguardando", "preparando")),
                   "&", ("estado", "=", "pronto"), ("pronto_em", ">=", limite_prontos)]
        if setor_codigo and setor_codigo != "todos":
            domain.append(("setor_id.codigo", "=", setor_codigo))
        tickets = self.search(domain)
        cancelamentos = self.search([("company_id", "in", self.env.companies.ids), ("tipo", "=", "cancelamento"),
                                     ("criado_em", ">=", fields.Datetime.now() - timedelta(minutes=10))]
                                    + ([("setor_id.codigo", "=", setor_codigo)] if setor_codigo and setor_codigo != "todos" else []))
        impressoras_paradas = self.env["boteco.impressora"].search([("estado", "=", "erro")])
        pendentes = self.env["boteco.impressao.job"].search_count([("estado", "=", "esperando")])
        return {
            # Etapa 21: totalizador de grelha, pacing e bump bar (a tela calcula e mostra)
            "avancado": self.env.company.boteco_recurso_ativo("kds_totalizador_pacing"),
            "tickets": tickets._dados_tela(),
            "cancelamentos": cancelamentos._dados_tela(),
            "canal": canal_kds(self.env.company.id),
            "impressoras_paradas": [{"id": i.id, "nome": i.name, "mensagem": i._mensagem_erro()} for i in impressoras_paradas],
            "tickets_esperando_impressao": pendentes,
            "agora": fields.Datetime.to_string(fields.Datetime.now()),
        }

    @api.model
    def kds_prontos_para_entregar(self):
        """Lista do garçom: o que está pronto e ainda não foi entregue."""
        tickets = self.search([("company_id", "in", self.env.companies.ids), ("tipo", "=", "novo"), ("estado", "=", "pronto")],
                              order="pronto_em asc")
        return tickets._dados_tela()

    # ------------------------------------------------------------------
    # Alerta de atraso ao gerente
    # ------------------------------------------------------------------
    @api.model
    def _cron_alertar_atrasos(self):
        limite = fields.Datetime.now() - timedelta(minutes=MINUTOS_ALERTA_GERENTE)
        atrasados = self.search([("tipo", "=", "novo"), ("estado", "in", ("aguardando", "preparando")),
                                 ("criado_em", "<=", limite), ("alerta_enviado", "=", False)])
        if not atrasados:
            return True
        gerentes = self.env.ref("boteco_base.group_gerente")
        Bus = self.env["bus.bus"].sudo()
        for ticket in atrasados:
            minutos = int((fields.Datetime.now() - ticket.criado_em).total_seconds() // 60)
            mensagem = _("%(mesa)s esperando há %(min)s min no %(setor)s",
                         mesa=ticket.mesa, min=minutos, setor=ticket.setor_id.name)
            Bus._sendone(gerentes, "simple_notification", {
                "title": _("Pedido atrasado"), "message": mensagem, "type": "danger", "sticky": True,
            })
            Bus._sendone(canal_kds(ticket.company_id.id), "boteco_kds/alerta", {"ticket_id": ticket.id, "mensagem": mensagem})
            config = ticket.order_id.config_id
            if config.current_session_id:
                config._notify("BOTECO_ALERTA", {"mensagem": mensagem})
        atrasados.write({"alerta_enviado": True})
        return True


class BotecoKdsItem(models.Model):
    _name = "boteco.kds.item"
    _description = "Item do ticket de produção"
    _order = "id"

    pedido_id = fields.Many2one("boteco.kds.pedido", required=True, ondelete="cascade", index=True)
    product_id = fields.Many2one("product.product", string="Produto")
    nome = fields.Char(required=True)
    quantidade = fields.Float(default=1.0)
    nota = fields.Char("Observação")
    atributos = fields.Char("Adicionais")
    line_uuid = fields.Char(index=True)
    maior_18 = fields.Boolean("+18")
    estado = fields.Selection(related="pedido_id.estado", store=True)
    setor_id = fields.Many2one(related="pedido_id.setor_id", store=True)
