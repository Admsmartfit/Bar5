from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class BotecoOfertaRelampago(models.Model):
    """Oferta relâmpago: preço especial para uma quantidade limitada, por pouco tempo.

    Aparece no topo do tablet enquanto houver saldo; some sozinha ao vender a última unidade.
    """

    _name = "boteco.oferta.relampago"
    _description = "Oferta relâmpago"
    _order = "inicio desc, id desc"

    name = fields.Char("Chamada", required=True, help="Texto do destaque. Ex.: 'Balde de 6 long necks'.")
    product_id = fields.Many2one(
        "product.product", string="Produto", required=True,
        domain="[('available_in_pos', '=', True)]",
    )
    preco = fields.Float("Preço da oferta", digits=(16, 2), required=True)
    preco_normal = fields.Float(related="product_id.lst_price", string="Preço normal")
    limite = fields.Float("Quantidade limite", required=True, default=20)
    duracao_min = fields.Integer("Duração (min)", default=60, help="Usada pelo botão 'Lançar agora'.")
    inicio = fields.Datetime("Começa")
    fim = fields.Datetime("Termina")
    estado = fields.Selection(
        [("rascunho", "Preparada"), ("ativa", "No ar"), ("esgotada", "Esgotou"), ("encerrada", "Encerrada")],
        default="rascunho", required=True, readonly=True, copy=False, index=True,
    )
    linha_ids = fields.One2many("pos.order.line", "boteco_oferta_id", string="Vendas", readonly=True)
    vendidos = fields.Float("Vendidos", compute="_compute_vendidos")
    restante = fields.Float("Restante", compute="_compute_vendidos")
    company_id = fields.Many2one("res.company", default=lambda s: s.env.company, required=True)

    @api.depends("linha_ids.qty", "linha_ids.order_id.state", "limite")
    def _compute_vendidos(self):
        for oferta in self:
            linhas = oferta.linha_ids.filtered(lambda l: l.order_id.state != "cancel")
            oferta.vendidos = sum(linhas.mapped("qty"))
            oferta.restante = max(oferta.limite - oferta.vendidos, 0.0)

    @api.constrains("preco", "limite")
    def _check_valores(self):
        for oferta in self:
            if oferta.preco < 0:
                raise ValidationError(_("O preço da oferta não pode ser negativo."))
            if oferta.limite <= 0:
                raise ValidationError(_("A quantidade limite precisa ser maior que zero."))

    @api.onchange("product_id")
    def _onchange_product_id(self):
        if self.product_id and not self.name:
            self.name = self.product_id.name

    # ------------------------------------------------------------------
    def action_lancar_agora(self):
        """Coloca a oferta no ar agora, no topo do tablet."""
        agora = fields.Datetime.now()
        for oferta in self:
            if oferta.estado in ("esgotada", "encerrada"):
                raise UserError(_("Esta oferta já terminou. Duplique para lançar de novo."))
            outras = self.search([("id", "!=", oferta.id), ("product_id", "=", oferta.product_id.id), ("estado", "=", "ativa")])
            if outras:
                raise UserError(_("Já existe uma oferta no ar para %s.", oferta.product_id.display_name))
            oferta.write({
                "estado": "ativa",
                "inicio": agora,
                "fim": agora + timedelta(minutes=oferta.duracao_min or 60),
            })
        self.env["pos.config"]._boteco_avisar_cardapio()
        return True

    def action_encerrar(self):
        self.filtered(lambda o: o.estado in ("rascunho", "ativa")).write({"estado": "encerrada", "fim": fields.Datetime.now()})
        self.env["pos.config"]._boteco_avisar_cardapio()
        return True

    @api.model
    def _oferta_ativa(self, produto, momento=None):
        momento = momento or fields.Datetime.now()
        return self.search(
            [
                ("product_id", "=", produto.id),
                ("estado", "=", "ativa"),
                ("inicio", "<=", momento),
                "|", ("fim", "=", False), ("fim", ">", momento),
            ],
            limit=1,
        )

    @api.model
    def _ofertas_no_ar(self, company=None):
        company = company or self.env.company
        agora = fields.Datetime.now()
        ofertas = self.search(
            [("estado", "=", "ativa"), ("company_id", "=", company.id), ("inicio", "<=", agora),
             "|", ("fim", "=", False), ("fim", ">", agora)]
        )
        return ofertas.filtered(lambda o: o.restante > 0)

    def _atualizar_estado(self):
        """Marca esgotada quem vendeu tudo e avisa os tablets."""
        mudou = False
        for oferta in self.filtered(lambda o: o.estado == "ativa"):
            if oferta.restante <= 0:
                oferta.estado = "esgotada"
                mudou = True
        if mudou:
            self.env["pos.config"]._boteco_avisar_cardapio()
        return mudou

    @api.model
    def _cron_encerrar_vencidas(self):
        vencidas = self.search([("estado", "=", "ativa"), ("fim", "!=", False), ("fim", "<=", fields.Datetime.now())])
        if vencidas:
            vencidas.write({"estado": "encerrada"})
            self.env["pos.config"]._boteco_avisar_cardapio()
        # Avisa as telas na virada do happy hour (elas também trocam sozinhas pelo relógio)
        for company in self.env["res.company"].search([]):
            proxima = self.env["boteco.happy.hour"]._proxima_troca(company=company)
            if proxima and proxima - fields.Datetime.now() <= timedelta(minutes=1):
                self.env["pos.config"]._boteco_avisar_cardapio()
                break
