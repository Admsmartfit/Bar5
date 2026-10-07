from odoo import _, fields, models


class BotecoRastreio(models.TransientModel):
    """Busca por código de lote: de quais insumos veio e quem recebeu (recolhimento)."""

    _name = "boteco.rastreio"
    _description = "Rastreio de lote"

    codigo = fields.Char("Código do lote", required=True, help="Digite ou leia o QR da etiqueta.")
    lot_id = fields.Many2one("stock.lot", string="Lote", readonly=True)
    produto = fields.Char(readonly=True)
    fabricacao = fields.Char(readonly=True)
    validade = fields.Char(readonly=True)
    clientes = fields.Text("Quem recebeu", readonly=True)
    insumos = fields.Text("Feito com", readonly=True)
    destinos = fields.Text("Para onde foi", readonly=True)
    erro = fields.Char(readonly=True)

    def action_buscar(self):
        self.ensure_one()
        dados = self.env["stock.lot"].boteco_buscar_rastreio(self.codigo)
        if dados.get("erro"):
            self.write({"erro": dados["erro"], "lot_id": False, "clientes": False, "insumos": False, "destinos": False})
        else:
            lote = self.env["stock.lot"].search([("name", "=", dados["lote"])], limit=1)
            self.write({
                "erro": False,
                "lot_id": lote.id,
                "produto": dados["produto"],
                "fabricacao": dados["fabricacao"],
                "validade": dados["validade"],
                "clientes": "\n".join(dados["clientes"]) or _("Ninguém fora da empresa recebeu este lote."),
                "insumos": "\n".join("%s – lote %s – %s %s" % (i["produto"], i["lote"] or "-", i["quantidade"], i["unidade"])
                                     for i in dados["insumos"]) or "-",
                "destinos": "\n".join("%s: %s (%s) – %s" % (d["data"][:10], d["destino"], d["quantidade"], d["documento"] or "")
                                      for d in dados["destinos"]) or "-",
            })
        return {"type": "ir.actions.act_window", "res_model": self._name, "res_id": self.id, "view_mode": "form",
                "target": "new"}
