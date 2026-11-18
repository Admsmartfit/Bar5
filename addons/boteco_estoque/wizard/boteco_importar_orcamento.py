"""Leitor de orçamento do fornecedor: PDF, foto (encarte/tabela) ou texto colado do WhatsApp (Etapa 18)."""

import base64
import logging
import mimetypes
import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..tools import orcamento

_logger = logging.getLogger(__name__)

PARAM_CHAVE = "boteco.visao_gemini_chave"
PARAM_MODELO = "boteco.visao_gemini_modelo"


class BotecoImportarOrcamento(models.TransientModel):
    _name = "boteco.importar.orcamento"
    _description = "Ler orçamento de fornecedor (PDF, foto ou texto)"

    partner_id = fields.Many2one("res.partner", string="Fornecedor", required=True)
    arquivo = fields.Binary("PDF ou foto")
    nome_arquivo = fields.Char()
    texto = fields.Text("Ou cole o texto", help="Ex.: a lista de preços que o fornecedor mandou no WhatsApp.")
    data = fields.Date("Data da cotação", default=fields.Date.context_today, required=True)
    origem = fields.Selection([("orcamento_pdf", "PDF"), ("orcamento_imagem", "Foto"), ("orcamento_texto", "Texto")],
                              readonly=True)
    linha_ids = fields.One2many("boteco.importar.orcamento.linha", "importacao_id", string="Itens encontrados")
    lido = fields.Boolean()
    registrados = fields.Integer(readonly=True)

    # ------------------------------------------------------------------
    @api.model
    def _achar_insumo(self, descricao, fornecedor=None):
        """Descrição do fornecedor -> insumo cadastrado (de-para, código do fornecedor ou nome)."""
        Produto = self.env["product.product"]
        if fornecedor:
            mapa = self.env["boteco.nfe.produto"].search(
                [("partner_id", "=", fornecedor.id), ("descricao", "=ilike", descricao)], limit=1)
            if mapa:
                return mapa.product_id
            info = self.env["product.supplierinfo"].search(
                [("partner_id", "=", fornecedor.id), ("product_name", "=ilike", descricao)], limit=1)
            if info:
                return info.product_id or info.product_tmpl_id.product_variant_id
        dominio = [("purchase_ok", "=", True)]
        produto = Produto.search(dominio + [("name", "=ilike", descricao)], limit=1)
        if produto:
            return produto
        produto = Produto.search(dominio + [("name", "ilike", descricao)], limit=2)
        if len(produto) == 1:
            return produto
        # Palavra significativa que aponte para um insumo só ("Oferta! Cebola nacional" -> "Cebola")
        for palavra in re.findall(r"[A-Za-zÀ-ú]{4,}", descricao):
            produto = Produto.search(dominio + [("name", "ilike", palavra)], limit=2)
            if len(produto) == 1:
                return produto
        return Produto

    def _tipo_arquivo(self):
        nome = (self.nome_arquivo or "").lower()
        conteudo = base64.b64decode(self.arquivo)
        if nome.endswith(".pdf") or conteudo[:4] == b"%PDF":
            return "pdf", conteudo, "application/pdf"
        mimetype = mimetypes.guess_type(nome)[0] or "image/jpeg"
        return "imagem", conteudo, mimetype

    def _ler_imagem(self, conteudo, mimetype):
        Param = self.env["ir.config_parameter"].sudo()
        chave = Param.get_param(PARAM_CHAVE)
        if not chave:
            raise UserError(_(
                "Para ler fotos, o dono precisa configurar a chave da API de visão (parâmetro %s). "
                "Enquanto isso, envie o orçamento em PDF ou cole o texto.", PARAM_CHAVE))
        try:
            return orcamento.ler_imagem_gemini(conteudo, mimetype, chave, Param.get_param(PARAM_MODELO) or "gemini-2.5-flash")
        except Exception as erro:  # noqa: BLE001
            _logger.warning("Leitura de imagem falhou", exc_info=True)
            raise UserError(_("Não consegui ler a foto agora (%s). Tente de novo ou cole o texto.", erro)) from erro

    def action_ler(self):
        self.ensure_one()
        if not self.env.company.boteco_recurso_ativo("leitor_orcamento_pdf_imagem"):
            raise UserError(_("O leitor de orçamentos está desligado na Central de Recursos."))
        if self.arquivo:
            tipo, conteudo, mimetype = self._tipo_arquivo()
            if tipo == "pdf":
                texto = orcamento.texto_do_pdf(conteudo)
                itens = orcamento.ler_texto(texto)
                if not itens:
                    raise UserError(_("Não achei preços no texto deste PDF. Se for PDF escaneado, envie como foto."))
                origem = "orcamento_pdf"
            else:
                itens = self._ler_imagem(conteudo, mimetype)
                origem = "orcamento_imagem"
        elif self.texto:
            itens = orcamento.ler_texto(self.texto)
            origem = "orcamento_texto"
        else:
            raise UserError(_("Envie um PDF, uma foto ou cole o texto do orçamento."))
        linhas = [fields.Command.clear()]
        De = self.env["boteco.nfe.produto"]
        for item in itens:
            produto = self._achar_insumo(item["descricao"], self.partner_id)
            mapa = De.search([("partner_id", "=", self.partner_id.id), ("descricao", "=ilike", item["descricao"])], limit=1)
            linhas.append(fields.Command.create({
                "descricao": item["descricao"], "unidade": item["unidade"], "preco": item["preco"],
                "product_id": produto.id, "fator": mapa.fator if mapa else 1.0,
            }))
        self.write({"linha_ids": linhas, "lido": True, "origem": origem})
        return self._reabrir()

    def _reabrir(self):
        return {"type": "ir.actions.act_window", "res_model": self._name, "res_id": self.id, "view_mode": "form",
                "target": "new"}

    def action_registrar(self):
        """Grava as cotações no histórico (radar de preços) e aprende o de-para do fornecedor."""
        self.ensure_one()
        if not self.lido:
            self.action_ler()
        Historico = self.env["boteco.historico.preco"]
        De = self.env["boteco.nfe.produto"]
        registrados = 0
        referencia = self.nome_arquivo or _("Orçamento %s", self.data)
        for linha in self.linha_ids.filtered("product_id"):
            preco = linha.preco / (linha.fator or 1.0)
            if Historico.registrar(linha.product_id, preco, fornecedor=self.partner_id, origem=self.origem or "manual",
                                   referencia=referencia, data=self.data, descricao=linha.descricao):
                registrados += 1
            codigo = "orc:" + re.sub(r"\s+", " ", linha.descricao.lower()).strip()[:60]
            if not De.search_count([("partner_id", "=", self.partner_id.id), ("codigo", "=", codigo)]):
                De.create({"partner_id": self.partner_id.id, "codigo": codigo, "descricao": linha.descricao,
                           "product_id": linha.product_id.id, "fator": linha.fator or 1.0})
        self.registrados = registrados
        return {
            "type": "ir.actions.act_window", "res_model": "boteco.historico.preco", "view_mode": "list,form",
            "name": _("Cotações registradas"),
            "domain": [("partner_id", "=", self.partner_id.id), ("data", "=", self.data)],
        }


class BotecoImportarOrcamentoLinha(models.TransientModel):
    _name = "boteco.importar.orcamento.linha"
    _description = "Item do orçamento lido"

    importacao_id = fields.Many2one("boteco.importar.orcamento", required=True, ondelete="cascade")
    descricao = fields.Char("Como veio escrito")
    unidade = fields.Char("Un.")
    preco = fields.Float("Preço", digits="Product Price")
    product_id = fields.Many2one("product.product", string="Insumo")
    fator = fields.Float("Fator", default=1.0, help="Unidades do estoque por unidade do orçamento (ex.: caixa com 20 kg = 20).")
