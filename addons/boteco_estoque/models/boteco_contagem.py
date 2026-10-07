from odoo import _, api, fields, models
from odoo.exceptions import UserError


class BotecoContagem(models.Model):
    """Contagem de estoque (inventário) feita pelo celular e aprovada pelo gerente."""

    _name = "boteco.contagem"
    _description = "Contagem de estoque"
    _order = "create_date desc"
    _inherit = ["mail.thread"]

    name = fields.Char("Contagem", required=True, default=lambda s: _("Contagem de %s", fields.Date.today().strftime("%d/%m/%Y")))
    location_id = fields.Many2one("stock.location", string="Local", required=True,
                                  domain="[('usage', '=', 'internal')]",
                                  default=lambda s: s.env["stock.warehouse"].search(
                                      [("company_id", "=", s.env.company.id)], limit=1).lot_stock_id)
    categ_ids = fields.Many2many("product.category", string="Só estas categorias",
                                 help="Vazio = todos os produtos com estoque controlado.")
    estado = fields.Selection(
        [("contando", "Contando"), ("contado", "Esperando o gerente"), ("aprovado", "Ajuste aplicado"),
         ("cancelado", "Cancelada")], default="contando", required=True, tracking=True,
    )
    responsavel_id = fields.Many2one("res.users", string="Quem contou", default=lambda s: s.env.user)
    aprovado_por_id = fields.Many2one("res.users", string="Aprovado por", readonly=True)
    linha_ids = fields.One2many("boteco.contagem.linha", "contagem_id", string="Itens")
    valor_diferenca = fields.Float("Diferença em R$", compute="_compute_totais", store=True)
    itens_contados = fields.Integer(compute="_compute_totais", store=True)
    company_id = fields.Many2one("res.company", default=lambda s: s.env.company)

    @api.depends("linha_ids.diferenca_valor", "linha_ids.contado")
    def _compute_totais(self):
        for c in self:
            c.valor_diferenca = sum(c.linha_ids.mapped("diferenca_valor"))
            c.itens_contados = len(c.linha_ids.filtered("contado"))

    def action_carregar_produtos(self):
        """Monta a lista com o que o sistema diz ter no local."""
        for contagem in self:
            dominio = [("is_storable", "=", True), ("active", "=", True)]
            if contagem.categ_ids:
                dominio.append(("categ_id", "child_of", contagem.categ_ids.ids))
            produtos = self.env["product.product"].search(dominio, order="categ_id, name")
            existentes = set(contagem.linha_ids.mapped("product_id").ids)
            contagem.linha_ids = [
                fields.Command.create({"product_id": p.id}) for p in produtos if p.id not in existentes
            ]
            contagem.linha_ids._compute_sistema()
        return True

    def action_abrir_celular(self):
        self.ensure_one()
        if not self.linha_ids:
            self.action_carregar_produtos()
        return {"type": "ir.actions.act_url", "url": "/boteco/contagem/%s" % self.id, "target": "self"}

    def action_terminar(self):
        self.write({"estado": "contado"})
        return True

    def action_aprovar(self):
        """Gerente aprova: o estoque passa a ser o contado (ajuste de inventário) e fica auditado."""
        if not self.env.user.boteco_pode("pode_ajustar_estoque"):
            raise UserError(_("Só o gerente aprova ajuste de estoque."))
        Quant = self.env["stock.quant"].sudo()
        for contagem in self:
            if contagem.estado not in ("contando", "contado"):
                continue
            linhas = contagem.linha_ids.filtered(lambda l: l.contado and l.diferenca)
            for linha in linhas:
                quant = Quant.with_context(inventory_mode=True).search(
                    [("product_id", "=", linha.product_id.id), ("location_id", "=", contagem.location_id.id)], limit=1)
                if quant:
                    quant.inventory_quantity = linha.quantidade_contada
                else:
                    quant = Quant.with_context(inventory_mode=True).create({
                        "product_id": linha.product_id.id, "location_id": contagem.location_id.id,
                        "inventory_quantity": linha.quantidade_contada,
                    })
                quant.action_apply_inventory()
                self.env["boteco.auditoria"].registrar(
                    "ajuste_estoque", registro=contagem,
                    descricao=_("Ajuste de inventário: %s", linha.product_id.display_name),
                    valor_antigo=linha.quantidade_sistema, valor_novo=linha.quantidade_contada,
                    valor=linha.diferenca_valor, motivo=contagem.name,
                )
            contagem.write({"estado": "aprovado", "aprovado_por_id": self.env.user.id})
        return True

    def boteco_dados_tela(self):
        """Dados para a tela de contagem do celular."""
        self.ensure_one()
        return {
            "id": self.id,
            "nome": self.name,
            "local": self.location_id.display_name,
            "estado": self.estado,
            "linhas": [
                {"id": l.id, "produto": l.product_id.display_name, "categoria": l.product_id.categ_id.name,
                 "unidade": l.product_id.uom_id.name, "contada": l.quantidade_contada if l.contado else None,
                 "barcode": l.product_id.barcode or ""}
                for l in self.linha_ids
            ],
        }

    def boteco_salvar(self, contagens):
        """contagens: {linha_id: quantidade}. A tela não mostra o que o sistema tem (contagem cega)."""
        self.ensure_one()
        if self.estado != "contando":
            raise UserError(_("Esta contagem já foi terminada."))
        for linha in self.linha_ids.filtered(lambda l: str(l.id) in contagens or l.id in contagens):
            valor = contagens.get(str(linha.id), contagens.get(linha.id))
            if valor in (None, ""):
                linha.write({"contado": False, "quantidade_contada": 0.0})
            else:
                linha.write({"contado": True, "quantidade_contada": float(valor)})
        return True


class BotecoContagemLinha(models.Model):
    _name = "boteco.contagem.linha"
    _description = "Item da contagem"
    _order = "id"

    contagem_id = fields.Many2one("boteco.contagem", required=True, ondelete="cascade", index=True)
    product_id = fields.Many2one("product.product", string="Produto", required=True)
    quantidade_sistema = fields.Float("No sistema", readonly=True)
    quantidade_contada = fields.Float("Contado")
    contado = fields.Boolean()
    diferenca = fields.Float(compute="_compute_diferenca", store=True)
    diferenca_valor = fields.Float("Diferença (R$)", compute="_compute_diferenca", store=True)

    def _compute_sistema(self):
        for linha in self:
            linha.quantidade_sistema = linha.product_id.with_context(
                location=linha.contagem_id.location_id.id).qty_available

    @api.depends("quantidade_sistema", "quantidade_contada", "contado")
    def _compute_diferenca(self):
        for linha in self:
            linha.diferenca = (linha.quantidade_contada - linha.quantidade_sistema) if linha.contado else 0.0
            linha.diferenca_valor = linha.diferenca * linha.product_id.standard_price
