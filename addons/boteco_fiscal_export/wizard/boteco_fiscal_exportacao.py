"""Exporta os registros fiscais de um período para o sistema que vai emitir as notas."""

import base64
import csv
import io
import json

import xlsxwriter

from odoo import _, fields, models
from odoo.exceptions import UserError


def _formatar(valor, decimal_virgula):
    if isinstance(valor, float):
        texto = "%.4f" % valor if abs(valor - round(valor, 2)) > 1e-9 else "%.2f" % valor
        return texto.replace(".", ",") if decimal_virgula else texto
    return "" if valor is None else str(valor)


def linhas_planas(dados):
    """Uma linha por item, com os dados da venda repetidos (formato que os emissores importam)."""
    for venda in dados:
        pagamentos = " | ".join("%s: %.2f" % (p["forma"], p["valor"]) for p in venda["pagamentos"])
        for item in venda["itens"]:
            yield {
                "registro_id": venda["registro_id"], "tipo": venda["tipo"], "referencia": venda["referencia"],
                "data_hora": venda["data_hora"], "emitente_cnpj": venda["emitente"]["cnpj"],
                "emitente_razao": venda["emitente"]["razao_social"], "emitente_ie": venda["emitente"]["ie"],
                "cliente_documento": venda["cliente_documento"], "cliente_nome": venda["cliente_nome"],
                "item_codigo": item["codigo"], "item_descricao": item["descricao"], "item_ncm": item["ncm"],
                "item_cest": item["cest"], "item_cfop": item["cfop"], "item_cst_csosn": item["cst_csosn"],
                "item_origem": item["origem"], "item_unidade": item["unidade"], "item_quantidade": item["quantidade"],
                "item_valor_unitario": item["valor_unitario"], "item_desconto": item["desconto"],
                "item_valor_total": item["valor_total"], "taxa_servico": venda["taxa_servico"],
                "pagamentos": pagamentos, "troco": venda["troco"], "valor_total": venda["valor_total"],
            }


class BotecoFiscalExportacao(models.TransientModel):
    _name = "boteco.fiscal.exportacao"
    _description = "Exportar registros fiscais"

    data_inicio = fields.Date("De", required=True, default=fields.Date.context_today)
    data_fim = fields.Date("Até", required=True, default=fields.Date.context_today)
    tipo = fields.Selection([("todos", "NFC-e e NF-e"), ("nfce", "Só NFC-e"), ("nfe", "Só NF-e")], default="todos", required=True)
    formato = fields.Selection([("csv", "CSV"), ("xlsx", "Excel"), ("json", "JSON")], default="csv", required=True)
    layout_id = fields.Many2one("boteco.fiscal.layout", string="Layout",
                                default=lambda s: s.env.ref("boteco_fiscal_export.layout_padrao", raise_if_not_found=False))
    reexportar = fields.Boolean("Exportar de novo os já exportados",
                                help="Só marque se o sistema emissor perdeu o arquivo. Os registros entram num lote novo.")
    pendencias = fields.Text("O que corrigir antes", readonly=True)
    lote_id = fields.Many2one("boteco.fiscal.lote", readonly=True)

    def _registros(self):
        estados = ["pendente", "exportado"] if self.reexportar else ["pendente"]
        dominio = [("company_id", "=", self.env.company.id), ("estado", "in", estados),
                   ("dia", ">=", self.data_inicio), ("dia", "<=", self.data_fim)]
        if self.tipo != "todos":
            dominio.append(("tipo", "=", self.tipo))
        return self.env["boteco.fiscal.registro"].search(dominio, order="data_venda, id")

    def _gerar_arquivo(self, dados):
        layout = self.layout_id
        colunas = layout.colunas() if layout else []
        if self.formato == "json":
            return json.dumps(dados, ensure_ascii=False, indent=2).encode("utf-8"), "json"
        if not colunas:
            raise UserError(_("Escolha um layout de exportação."))
        linhas = list(linhas_planas(dados))
        if self.formato == "csv":
            saida = io.StringIO()
            escritor = csv.writer(saida, delimiter=layout.separador or ";", lineterminator="\r\n")
            escritor.writerow([titulo for _c, titulo in colunas])
            for linha in linhas:
                escritor.writerow([_formatar(linha[c], layout.decimal_virgula) for c, _t in colunas])
            return saida.getvalue().encode("utf-8-sig"), "csv"
        saida = io.BytesIO()
        livro = xlsxwriter.Workbook(saida, {"in_memory": True})
        aba = livro.add_worksheet("Notas")
        negrito = livro.add_format({"bold": True})
        for col, (_c, titulo) in enumerate(colunas):
            aba.write(0, col, titulo, negrito)
        for lin, linha in enumerate(linhas, start=1):
            for col, (campo, _t) in enumerate(colunas):
                valor = linha[campo]
                if isinstance(valor, (int, float)) and campo not in ("registro_id",):
                    aba.write_number(lin, col, valor)
                else:
                    aba.write_string(lin, col, "" if valor is None else str(valor))
        livro.close()
        return saida.getvalue(), "xlsx"

    def action_exportar(self):
        self.ensure_one()
        registros = self._registros()
        if not registros:
            raise UserError(_("Nada para exportar neste período."))
        faltando = registros.pendencias_cadastro()
        if faltando:
            self.pendencias = "\n".join("%s: falta %s" % (produto, ", ".join(p)) for produto, p in sorted(faltando.items()))
            return {"type": "ir.actions.act_window", "res_model": self._name, "res_id": self.id, "view_mode": "form",
                    "target": "new"}
        dados = registros.dados_exportacao()
        conteudo, extensao = self._gerar_arquivo(dados)
        lote = self.env["boteco.fiscal.lote"].create({
            "periodo_inicio": self.data_inicio, "periodo_fim": self.data_fim, "formato": self.formato,
            "reexportacao": self.reexportar, "registro_ids": [fields.Command.set(registros.ids)],
        })
        lote.write({"arquivo": base64.b64encode(conteudo),
                    "nome_arquivo": "notas-%s.%s" % (lote.name.replace("/", "-"), extensao)})
        for registro in registros:
            registro.write({"estado": "exportado", "lote_ids": [fields.Command.link(lote.id)]})
        self.env["boteco.auditoria"].registrar(
            "fiscal", registro=lote, descricao=_("Exportação fiscal %(lote)s (%(n)s vendas)", lote=lote.name, n=len(registros)),
            valor=lote.valor_total)
        self.write({"lote_id": lote.id, "pendencias": False})
        return lote.action_baixar()
