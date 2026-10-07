"""Importa o XML da NF-e do fornecedor e dá entrada no estoque sem digitação."""

import base64
import re

from lxml import etree

from odoo import _, api, fields, models
from odoo.exceptions import UserError

NS = {"n": "http://www.portalfiscal.inf.br/nfe"}


def _txt(no, caminho):
    if no is None:
        return ""
    achado = no.find(caminho, NS)
    return (achado.text or "").strip() if achado is not None and achado.text else ""


def _num(no, caminho):
    valor = _txt(no, caminho)
    try:
        return float(valor) if valor else 0.0
    except ValueError:
        return 0.0


def ler_nfe(conteudo):
    """Lê o XML (nfeProc ou NFe) e devolve um dicionário com cabeçalho e itens."""
    try:
        raiz = etree.fromstring(conteudo, parser=etree.XMLParser(resolve_entities=False, no_network=True))
    except etree.XMLSyntaxError as erro:
        raise UserError(_("Arquivo não é um XML válido de NF-e: %s", erro)) from erro
    inf = raiz.find(".//n:infNFe", NS)
    if inf is None:
        raise UserError(_("Não encontrei a nota (infNFe) neste XML. Use o XML da NF-e enviado pelo fornecedor."))
    chave = re.sub(r"\D", "", inf.get("Id") or "")
    emit = inf.find("n:emit", NS)
    ide = inf.find("n:ide", NS)
    itens = []
    for det in inf.findall("n:det", NS):
        prod = det.find("n:prod", NS)
        ean = _txt(prod, "n:cEAN")
        itens.append({
            "item": int(det.get("nItem") or len(itens) + 1),
            "codigo": _txt(prod, "n:cProd"),
            "descricao": _txt(prod, "n:xProd"),
            "ean": ean if ean and ean.upper() != "SEM GTIN" else "",
            "ncm": _txt(prod, "n:NCM"),
            "cfop": _txt(prod, "n:CFOP"),
            "unidade": _txt(prod, "n:uCom"),
            "quantidade": _num(prod, "n:qCom"),
            "valor_unitario": _num(prod, "n:vUnCom"),
            "valor_total": _num(prod, "n:vProd") - _num(prod, "n:vDesc"),
        })
    if not itens:
        raise UserError(_("A nota não tem itens."))
    return {
        "chave": chave,
        "numero": _txt(ide, "n:nNF"),
        "serie": _txt(ide, "n:serie"),
        "emissao": (_txt(ide, "n:dhEmi") or _txt(ide, "n:dEmi"))[:10],
        "cnpj": _txt(emit, "n:CNPJ") or _txt(emit, "n:CPF"),
        "fornecedor": _txt(emit, "n:xNome"),
        "fantasia": _txt(emit, "n:xFant"),
        "total": _num(inf, "n:total/n:ICMSTot/n:vNF"),
        "itens": itens,
    }


class BotecoNfeImportacao(models.TransientModel):
    _name = "boteco.nfe.importacao"
    _description = "Importar XML da NF-e do fornecedor"

    arquivo = fields.Binary("XML da nota", required=True)
    nome_arquivo = fields.Char()
    chave = fields.Char(readonly=True)
    numero = fields.Char("Número", readonly=True)
    emissao = fields.Date(readonly=True)
    partner_id = fields.Many2one("res.partner", string="Fornecedor")
    total = fields.Float("Total da nota", readonly=True)
    criar_produtos = fields.Boolean("Criar insumos que não existem", default=True)
    linha_ids = fields.One2many("boteco.nfe.importacao.linha", "importacao_id", string="Itens")
    lido = fields.Boolean()
    purchase_id = fields.Many2one("purchase.order", string="Entrada criada", readonly=True)

    def _fornecedor(self, dados):
        Parceiro = self.env["res.partner"]
        cnpj = re.sub(r"\D", "", dados["cnpj"] or "")
        if cnpj:
            for parceiro in Parceiro.search([("vat", "!=", False)]):
                if re.sub(r"\D", "", parceiro.vat or "") == cnpj:
                    return parceiro
        return Parceiro.create({"name": dados["fantasia"] or dados["fornecedor"] or _("Fornecedor"), "vat": cnpj or False,
                                "is_company": True, "supplier_rank": 1})

    def _sugerir_produto(self, fornecedor, item):
        De = self.env["boteco.nfe.produto"]
        mapa = De.search([("partner_id", "=", fornecedor.id), ("codigo", "=", item["codigo"])], limit=1)
        if mapa:
            return mapa.product_id, mapa.fator
        Produto = self.env["product.product"]
        if item["ean"]:
            produto = Produto.search([("barcode", "=", item["ean"])], limit=1)
            if produto:
                return produto, 1.0
        info = self.env["product.supplierinfo"].search(
            [("partner_id", "=", fornecedor.id), ("product_code", "=", item["codigo"])], limit=1)
        if info:
            return info.product_id or info.product_tmpl_id.product_variant_id, 1.0
        return Produto, 1.0

    def action_ler(self):
        self.ensure_one()
        dados = ler_nfe(base64.b64decode(self.arquivo))
        if dados["chave"] and self.env["purchase.order"].search_count([("boteco_chave_nfe", "=", dados["chave"])]):
            raise UserError(_("Esta nota (%s) já foi importada.", dados["numero"]))
        fornecedor = self._fornecedor(dados)
        linhas = []
        for item in dados["itens"]:
            produto, fator = self._sugerir_produto(fornecedor, item)
            linhas.append(fields.Command.create({
                "codigo": item["codigo"], "descricao": item["descricao"], "ean": item["ean"], "ncm": item["ncm"],
                "unidade": item["unidade"], "quantidade": item["quantidade"], "valor_total": item["valor_total"],
                "product_id": produto.id, "fator": fator,
            }))
        self.write({
            "chave": dados["chave"], "numero": dados["numero"], "emissao": dados["emissao"] or False,
            "partner_id": fornecedor.id, "total": dados["total"], "linha_ids": [fields.Command.clear()] + linhas,
            "lido": True,
        })
        return self._reabrir()

    def _reabrir(self):
        return {"type": "ir.actions.act_window", "res_model": self._name, "res_id": self.id, "view_mode": "form",
                "target": "new"}

    def _criar_produto(self, linha):
        vals = {
            "name": linha.descricao, "type": "consu", "is_storable": True, "sale_ok": False, "purchase_ok": True,
            "available_in_pos": False, "standard_price": linha.valor_total / max(linha.quantidade * (linha.fator or 1), 1e-9),
        }
        if linha.ean:
            vals["barcode"] = linha.ean
        if "boteco_ncm" in self.env["product.product"]._fields and linha.ncm and len(re.sub(r"\D", "", linha.ncm)) == 8:
            vals["boteco_ncm"] = linha.ncm
        return self.env["product.product"].create(vals)

    def action_criar_entrada(self):
        """Cria o pedido de compra, confirma e recebe: o estoque e o custo médio já ficam certos."""
        self.ensure_one()
        if not self.lido:
            self.action_ler()
        sem_produto = self.linha_ids.filtered(lambda l: not l.product_id)
        if sem_produto and not self.criar_produtos:
            raise UserError(_("Escolha o insumo dos itens: %s", ", ".join(sem_produto.mapped("descricao"))))
        for linha in sem_produto:
            linha.product_id = self._criar_produto(linha)
        De = self.env["boteco.nfe.produto"]
        linhas_compra = []
        for linha in self.linha_ids:
            if linha.codigo and not De.search_count([("partner_id", "=", self.partner_id.id), ("codigo", "=", linha.codigo)]):
                De.create({"partner_id": self.partner_id.id, "codigo": linha.codigo, "descricao": linha.descricao,
                           "product_id": linha.product_id.id, "fator": linha.fator or 1.0})
            quantidade = linha.quantidade * (linha.fator or 1.0)
            linhas_compra.append(fields.Command.create({
                "product_id": linha.product_id.id,
                "name": linha.descricao or linha.product_id.display_name,
                "product_qty": quantidade,
                "product_uom": linha.product_id.uom_po_id.id or linha.product_id.uom_id.id,
                "price_unit": linha.valor_total / quantidade if quantidade else 0.0,
                "taxes_id": [fields.Command.clear()],
            }))
        compra = self.env["purchase.order"].create({
            "partner_id": self.partner_id.id,
            "partner_ref": "NF %s" % self.numero if self.numero else False,
            "boteco_chave_nfe": self.chave or False,
            "date_order": fields.Datetime.to_datetime(self.emissao) if self.emissao else fields.Datetime.now(),
            "order_line": linhas_compra,
        })
        compra.button_confirm()
        for recebimento in compra.picking_ids.filtered(lambda p: p.state not in ("done", "cancel")):
            for move in recebimento.move_ids:
                move.quantity = move.product_uom_qty
            recebimento.move_ids.picked = True
            recebimento.button_validate()
        self.purchase_id = compra
        return {"type": "ir.actions.act_window", "res_model": "purchase.order", "res_id": compra.id, "view_mode": "form"}


class BotecoNfeImportacaoLinha(models.TransientModel):
    _name = "boteco.nfe.importacao.linha"
    _description = "Item da NF-e importada"

    importacao_id = fields.Many2one("boteco.nfe.importacao", required=True, ondelete="cascade")
    codigo = fields.Char("Código")
    descricao = fields.Char("Descrição")
    ean = fields.Char("Código de barras")
    ncm = fields.Char("NCM")
    unidade = fields.Char("Un. da nota")
    quantidade = fields.Float("Qtd. da nota")
    valor_total = fields.Float("Valor")
    product_id = fields.Many2one("product.product", string="Insumo")
    fator = fields.Float("Fator", default=1.0, help="Unidades do estoque por unidade da nota.")
