"""Radar de preços -> oportunidade de compra, sugestão de reposição e alerta de marketing (19/11/2026).

Regra: preço cotado X% (padrão 10%) abaixo do PREÇO MÉDIO PONDERADO DAS ÚLTIMAS 3 COMPRAS do insumo
(sem compras, vale o custo médio atual). Disparou:
* aviso no Painel do dono e pendência para os gerentes;
* sugestão de compra maior na Lista de compras (consumo de N dias de estoque);
* "alerta de marketing": itens do cardápio que usam o insumo ficam mais baratos de fazer;
  o sistema calcula o preço de uma Oferta relâmpago que mantém a margem % de hoje.
"""

import math
import re
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.boteco_pos.models.boteco_crm import link_whatsapp

COMPRAS_PMP = 3
VALIDADE_DIAS = 3


class ResCompany(models.Model):
    _inherit = "res.company"

    boteco_radar_queda_pct = fields.Float("Oportunidade a partir de (% abaixo)", default=10.0)
    boteco_radar_so_chave = fields.Boolean(
        "Só insumos chave", help="Ligado: só os insumos marcados como chave (cerveja, carne…) geram oportunidade.")
    boteco_estoque_dias_cobertura = fields.Integer(
        "Comprar para quantos dias na oportunidade", default=21,
        help="Na oportunidade, a lista de compras sugere estoque para esses dias de consumo.")


class ProductTemplate(models.Model):
    _inherit = "product.template"

    boteco_insumo_chave = fields.Boolean(
        "Insumo chave", help="Pesa no custo (cerveja, carne, óleo…): o radar avisa quando o preço cai.")


class BotecoOportunidadeCompra(models.Model):
    _name = "boteco.oportunidade.compra"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = "Oportunidade de compra (radar de preços)"
    _order = "estado, queda_pct desc, id desc"

    name = fields.Char(compute="_compute_name", store=True)
    product_id = fields.Many2one("product.product", string="Insumo", required=True, index=True)
    partner_id = fields.Many2one("res.partner", string="Fornecedor", required=True)
    preco_cotado = fields.Float("Preço cotado", digits="Product Price", required=True)
    preco_medio = fields.Float("Preço médio (últimas compras)", digits="Product Price", required=True)
    base_calculo = fields.Char("Base do preço médio")
    queda_pct = fields.Float("Abaixo do médio (%)", digits=(5, 1))
    economia_unidade = fields.Float("Economia por unidade", digits="Product Price")
    uom_id = fields.Many2one(related="product_id.uom_id", string="Unidade")
    estoque_atual = fields.Float("Em estoque", digits="Product Unit of Measure")
    consumo_diario = fields.Float("Consumo por dia", digits="Product Unit of Measure")
    sugestao_qtd = fields.Float("Sugestão de compra", digits="Product Unit of Measure")
    economia_total = fields.Float("Economia na sugestão (R$)", digits=(16, 2))
    valida_ate = fields.Date(required=True)
    estado = fields.Selection([("nova", "Nova"), ("comprada", "Comprada"), ("ignorada", "Ignorada"),
                               ("expirada", "Expirada")], default="nova", required=True, index=True)
    marketing_ids = fields.One2many("boteco.alerta.marketing", "oportunidade_id", string="Ideias de promoção")
    company_id = fields.Many2one("res.company", required=True, default=lambda s: s.env.company)

    @api.depends("product_id", "queda_pct")
    def _compute_name(self):
        for o in self:
            o.name = _("%(p)s %(q).0f%% abaixo do médio", p=o.product_id.display_name or "", q=o.queda_pct or 0)

    # ------------------------------------------------------------------ cálculo
    @api.model
    def _preco_medio_ponderado(self, produto):
        """PMP das últimas 3 compras confirmadas (na unidade do insumo). Sem compras: custo médio atual."""
        linhas = self.env["purchase.order.line"].sudo().search([
            ("product_id", "=", produto.id), ("order_id.state", "in", ("purchase", "done")), ("product_qty", ">", 0),
        ], order="date_order desc, id desc", limit=COMPRAS_PMP)
        total_qtd = total_valor = 0.0
        for linha in linhas:
            qtd = linha.product_uom._compute_quantity(linha.product_qty, produto.uom_id)
            preco = linha.product_uom._compute_price(linha.price_unit, produto.uom_id)
            total_qtd += qtd
            total_valor += qtd * preco
        if total_qtd:
            return total_valor / total_qtd, _("%s última(s) compra(s)", len(linhas))
        if produto.standard_price > 0:
            return produto.standard_price, _("custo médio atual (sem compras registradas)")
        return 0.0, ""

    @api.model
    def _consumo_diario(self, produto, dias=30):
        desde = fields.Datetime.now() - timedelta(days=dias)
        moves = self.env["stock.move"].sudo().search([
            ("product_id", "=", produto.id), ("state", "=", "done"), ("date", ">=", desde),
            ("location_id.usage", "=", "internal"),
            ("location_dest_id.usage", "in", ("customer", "production", "inventory")),
        ])
        return sum(m.product_uom._compute_quantity(m.quantity, produto.uom_id) for m in moves) / dias

    @api.model
    def _avaliar(self, produto, fornecedor, preco):
        """Chamado a cada cotação que chega (gatilho na hora, não espera cron)."""
        company = self.env.company
        if not company.boteco_recurso_ativo("radar_precos_oportunidade"):
            return self.browse()
        if company.boteco_radar_so_chave and not produto.boteco_insumo_chave:
            return self.browse()
        medio, base = self._preco_medio_ponderado(produto)
        if medio <= 0:
            return self.browse()
        queda = (medio - preco) * 100.0 / medio
        if queda < (company.boteco_radar_queda_pct or 10.0):
            return self.browse()
        estoque = produto.sudo().qty_available
        consumo = self._consumo_diario(produto)
        regra = self.env["stock.warehouse.orderpoint"].sudo().search([("product_id", "=", produto.id)], limit=1)
        alvo = max(consumo * (company.boteco_estoque_dias_cobertura or 21), regra.product_max_qty if regra else 0.0)
        sugestao = max(math.ceil(alvo - estoque), 0) if alvo else 0.0
        vals = {
            "product_id": produto.id, "partner_id": fornecedor.id, "preco_cotado": preco, "preco_medio": medio,
            "base_calculo": base, "queda_pct": round(queda, 1), "economia_unidade": medio - preco,
            "estoque_atual": estoque, "consumo_diario": round(consumo, 3), "sugestao_qtd": sugestao,
            "economia_total": round((medio - preco) * sugestao, 2),
            "valida_ate": fields.Date.context_today(self) + timedelta(days=VALIDADE_DIAS), "company_id": company.id,
        }
        aberta = self.sudo().search([("product_id", "=", produto.id), ("estado", "=", "nova")], limit=1)
        if aberta:
            if preco >= aberta.preco_cotado:
                return aberta  # já existe uma oportunidade melhor ou igual
            aberta.write(vals)
            oportunidade = aberta
        else:
            oportunidade = self.sudo().create(vals)
            oportunidade._avisar_gerentes()
        oportunidade.marketing_ids.unlink()
        self.env["boteco.alerta.marketing"].sudo()._gerar(oportunidade)
        return oportunidade

    def _avisar_gerentes(self):
        tipo = self.env.ref("mail.mail_activity_data_todo", raise_if_not_found=False)
        gerentes = self.env.ref("boteco_base.group_gerente").sudo().users.filtered(lambda u: u.active and not u.share)
        for o in self:
            for gerente in gerentes[:5]:
                gerente.partner_id._bus_send("simple_notification", {
                    "title": _("Oportunidade de compra"), "type": "success", "sticky": False,
                    "message": _("%(p)s a R$ %(v).2f (%(q).0f%% abaixo do médio) em %(f)s",
                                 p=o.product_id.display_name, v=o.preco_cotado, q=o.queda_pct, f=o.partner_id.name)})
                if tipo:
                    o.activity_schedule(activity_type_id=tipo.id, user_id=gerente.id, date_deadline=o.valida_ate,
                                        summary=_("Comprar %s?", o.product_id.display_name)[:100])

    def action_comprada(self):
        self.write({"estado": "comprada"})
        self.activity_ids.unlink()

    def action_ignorar(self):
        self.write({"estado": "ignorada"})
        self.activity_ids.unlink()

    @api.model
    def _cron_expirar(self):
        vencidas = self.sudo().search([("estado", "=", "nova"), ("valida_ate", "<", fields.Date.context_today(self))])
        vencidas.write({"estado": "expirada"})
        vencidas.activity_ids.unlink()
        return True


class BotecoAlertaMarketing(models.Model):
    """O custo de um item do cardápio caiu: sugere a Oferta relâmpago e mostra a margem promocional."""

    _name = "boteco.alerta.marketing"
    _description = "Alerta de marketing (ideia de promoção)"
    _order = "economia_unidade desc, id"

    oportunidade_id = fields.Many2one("boteco.oportunidade.compra", required=True, ondelete="cascade", index=True)
    product_id = fields.Many2one("product.product", string="Item do cardápio", required=True)
    preco_venda = fields.Float("Preço hoje", digits=(16, 2))
    custo_atual = fields.Float("Custo hoje", digits="Product Price")
    custo_novo = fields.Float("Custo com a oportunidade", digits="Product Price")
    economia_unidade = fields.Float("Fica mais barato fazer", digits="Product Price")
    margem_atual_pct = fields.Float("Margem hoje (%)", digits=(5, 1))
    preco_promocional = fields.Float("Preço da oferta sugerido", digits=(16, 2))
    margem_promocional_pct = fields.Float("Margem na oferta (%)", digits=(5, 1))
    oferta_id = fields.Many2one("boteco.oferta.relampago", string="Oferta criada", readonly=True)
    estado = fields.Selection(related="oportunidade_id.estado")

    @api.model
    def _gerar(self, oportunidade):
        """Itens vendidos que levam o insumo (receita) ou que são o próprio insumo (revenda: long neck)."""
        insumo = oportunidade.product_id
        economia = oportunidade.preco_medio - oportunidade.preco_cotado
        itens = {}
        if insumo.available_in_pos and insumo.sale_ok:
            itens[insumo] = 1.0
        for linha in self.env["mrp.bom.line"].sudo().search([("product_id", "=", insumo.id), ("bom_id.active", "=", True)]):
            bom = linha.bom_id
            por_unidade = linha.product_uom_id._compute_quantity(linha.product_qty, insumo.uom_id) / (bom.product_qty or 1.0)
            for variante in bom.product_tmpl_id.product_variant_ids.filtered(lambda p: p.available_in_pos and p.sale_ok):
                itens[variante] = itens.get(variante, 0.0) + por_unidade
        for produto, quantidade in itens.items():
            preco = produto.lst_price
            custo = produto.standard_price
            if preco <= 0 or custo <= 0:
                continue
            reducao = economia * quantidade
            custo_novo = max(custo - reducao, 0.0)
            margem = (preco - custo) / preco
            # Mantém a margem % de hoje com o custo novo (repassa a economia ao cliente sem perder rentabilidade)
            promo = math.floor(custo_novo / (1 - margem) * 10) / 10.0 if margem < 1 else preco
            if promo >= preco * 0.97 or promo <= custo_novo:
                continue  # mudança pequena demais para valer uma oferta
            self.create({
                "oportunidade_id": oportunidade.id, "product_id": produto.id, "preco_venda": preco,
                "custo_atual": custo, "custo_novo": round(custo_novo, 4), "economia_unidade": round(reducao, 4),
                "margem_atual_pct": round(margem * 100, 1), "preco_promocional": promo,
                "margem_promocional_pct": round((promo - custo_novo) * 100 / promo, 1),
            })

    def action_criar_oferta(self):
        """Prepara a Oferta relâmpago (o gerente confere e toca em 'Lançar agora' no PDV/autoatendimento)."""
        self.ensure_one()
        if self.oferta_id:
            raise UserError(_("A oferta já foi criada."))
        limite = self.oportunidade_id.sugestao_qtd or 20
        self.oferta_id = self.env["boteco.oferta.relampago"].create({
            "name": _("%(p)s por R$ %(v).2f", p=self.product_id.name, v=self.preco_promocional),
            "product_id": self.product_id.id, "preco": self.preco_promocional, "limite": limite, "duracao_min": 120,
        })
        return {"type": "ir.actions.act_window", "res_model": "boteco.oferta.relampago", "res_id": self.oferta_id.id,
                "view_mode": "form", "target": "current"}


class BotecoPainel(models.AbstractModel):
    _inherit = "boteco.painel"

    @api.model
    def _oportunidades_compra(self, company):
        """Painel do dono: as oportunidades da API vêm primeiro (com a sugestão de compra e a ideia de promoção)."""
        resultado = super()._oportunidades_compra(company)
        if not company.boteco_recurso_ativo("radar_precos_oportunidade"):
            return resultado
        novas = self.env["boteco.oportunidade.compra"].sudo().search(
            [("company_id", "=", company.id), ("estado", "=", "nova")], limit=8)
        ja = {r["insumo"] for r in resultado}
        extras = []
        for o in novas:
            if o.product_id.display_name in ja:
                continue
            extras.append({
                "insumo": o.product_id.display_name, "fornecedor": o.partner_id.name, "preco": o.preco_cotado,
                "media": round(o.preco_medio, 2), "queda_pct": o.queda_pct,
                "origem": _("Serviço de cotações"),
                "receitas": [{"produto": _("Comprar %(q)g %(u)s (estoque de %(d)s dias)", q=o.sugestao_qtd,
                                           u=o.uom_id.name, d=company.boteco_estoque_dias_cobertura),
                              "economia_receita": o.economia_total}] if o.sugestao_qtd else [],
                "economia_total_receita": o.economia_total, "freezer_livre_litros": None,
            })
        return (extras + resultado)[:8]

    @api.model
    def _alertas_extras(self, company):
        alertas = super()._alertas_extras(company)
        ideias = self.env["boteco.alerta.marketing"].sudo().search(
            [("oportunidade_id.company_id", "=", company.id), ("oportunidade_id.estado", "=", "nova"),
             ("oferta_id", "=", False)], limit=3)
        for ideia in ideias:
            alertas.append(_("Promoção: %(p)s pode sair a R$ %(n).2f (hoje R$ %(h).2f) mantendo %(m).0f%% de margem, "
                             "porque %(i)s caiu. Compras › Oportunidades.", p=ideia.product_id.name,
                             n=ideia.preco_promocional, h=ideia.preco_venda, m=ideia.margem_promocional_pct,
                             i=ideia.oportunidade_id.product_id.name))
        revisar = self.env["boteco.cotacao.revisar"].sudo().search_count([("estado", "=", "revisar")])
        if revisar:
            alertas.append(_("%s cotação(ões) esperando você ligar ao insumo (Compras › Cotações para revisar).", revisar))
        return alertas


class BotecoListaCompras(models.TransientModel):
    _inherit = "boteco.lista.compras"

    def action_gerar(self):
        """Além do estoque mínimo, entra a sugestão maior das oportunidades (composição de estoque)."""
        resultado = super().action_gerar()
        oportunidades = self.env["boteco.oportunidade.compra"].sudo().search(
            [("estado", "=", "nova"), ("company_id", "=", self.env.company.id), ("sugestao_qtd", ">", 0)])
        for o in oportunidades:
            produto = o.product_id
            texto = "• %s: %g %s 🔥 oportunidade −%.0f%% (R$ %.2f; economia ~R$ %.2f)" % (
                produto.name, o.sugestao_qtd, produto.uom_po_id.name or produto.uom_id.name, o.queda_pct,
                o.preco_cotado, o.economia_total)
            linha = self.linha_ids.filtered(lambda l, f=o.partner_id: l.partner_id == f)[:1]
            if linha:
                # Já tinha o item por estar abaixo do mínimo: troca pela quantidade maior da oportunidade
                itens = [i for i in (linha.itens or "").split("\n") if not i.startswith("• %s:" % produto.name)]
                linha.write({"itens": "\n".join(itens + [texto]), "quantidade_itens": len(itens) + 1})
            else:
                mensagem = _("Olá! Pedido do %(e)s:\n%(i)s\nObrigado!", e=self.env.company.name, i=texto.split(" 🔥")[0])
                self.linha_ids = [fields.Command.create({
                    "partner_id": o.partner_id.id, "itens": texto, "quantidade_itens": 1, "mensagem": mensagem,
                    "link_whatsapp": link_whatsapp(o.partner_id.mobile or o.partner_id.phone, mensagem) or False})]
        self._boteco_melhor_preco()
        return resultado

    def _boteco_melhor_preco(self):
        """Para cada item da linha: o menor preço dos últimos 30 dias e de onde veio."""
        Historico = self.env["boteco.historico.preco"].sudo()
        rotulos = dict(Historico._fields["origem"]._description_selection(self.env))
        for linha in self.linha_ids:
            partes = []
            for nome in re.findall(r"^• (.+?): ", linha.itens or "", re.M):
                produto = self.env["product.product"].search([("name", "=", nome)], limit=1)
                melhor = Historico.search([("product_id", "=", produto.id), ("company_id", "=", self.env.company.id),
                                           ("data", ">=", fields.Date.context_today(self) - timedelta(days=30))],
                                          order="preco_unitario asc, data desc", limit=1) if produto else Historico
                if melhor:
                    partes.append("%s: R$ %.2f – %s (%s, %s)" % (
                        nome, melhor.preco_unitario, melhor.partner_id.name or "?", rotulos.get(melhor.origem, ""),
                        melhor.data.strftime("%d/%m")))
            linha.melhor_preco = "\n".join(partes) or False


class BotecoListaComprasLinha(models.TransientModel):
    _inherit = "boteco.lista.compras.linha"

    melhor_preco = fields.Text("Melhor preço encontrado (onde)")
