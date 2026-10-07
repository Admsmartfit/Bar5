"""Importa o retorno do sistema emissor: número e chave de cada nota emitida."""

import base64
import csv
import io

import openpyxl

from odoo import _, fields, models
from odoo.exceptions import UserError

NOMES_REFERENCIA = {"referencia", "referência", "venda", "pedido", "registro_id", "id do registro", "id"}
NOMES_NUMERO = {"numero", "número", "numero da nota", "número da nota", "nnf"}
NOMES_CHAVE = {"chave", "chave da nota", "chave de acesso", "chnfe"}


class BotecoFiscalRetorno(models.TransientModel):
    _name = "boteco.fiscal.retorno"
    _description = "Importar notas emitidas"

    arquivo = fields.Binary("Planilha de retorno (CSV ou Excel)", required=True)
    nome_arquivo = fields.Char()
    resultado = fields.Text(readonly=True)

    def _linhas(self):
        conteudo = base64.b64decode(self.arquivo)
        if (self.nome_arquivo or "").lower().endswith(".xlsx") or conteudo[:2] == b"PK":
            livro = openpyxl.load_workbook(io.BytesIO(conteudo), read_only=True, data_only=True)
            linhas = [[("" if c is None else str(c)).strip() for c in linha] for linha in livro.worksheets[0].iter_rows(values_only=True)]
        else:
            texto = conteudo.decode("utf-8-sig", errors="replace")
            dialeto = csv.Sniffer().sniff(texto.splitlines()[0], delimiters=";,\t")
            linhas = [[c.strip() for c in linha] for linha in csv.reader(io.StringIO(texto), dialeto)]
        if not linhas:
            raise UserError(_("A planilha está vazia."))
        cabecalho = [c.lower() for c in linhas[0]]

        def coluna(nomes):
            for i, nome in enumerate(cabecalho):
                if nome in nomes:
                    return i
            return None

        ref, num, chave = coluna(NOMES_REFERENCIA), coluna(NOMES_NUMERO), coluna(NOMES_CHAVE)
        if ref is None or num is None:
            raise UserError(_("A planilha precisa das colunas 'referencia' (ou 'registro_id') e 'numero' (e de preferência 'chave')."))
        id_por_registro = cabecalho[ref] in ("registro_id", "id do registro", "id")
        for linha in linhas[1:]:
            if not any(linha):
                continue
            yield {
                "referencia": linha[ref] if ref < len(linha) else "",
                "por_id": id_por_registro,
                "numero": linha[num] if num < len(linha) else "",
                "chave": linha[chave] if chave is not None and chave < len(linha) else "",
            }

    def action_importar(self):
        self.ensure_one()
        Registro = self.env["boteco.fiscal.registro"]
        marcados, avisos = 0, []
        for item in self._linhas():
            if item["por_id"]:
                registro = Registro.browse(int(float(item["referencia"] or 0))).exists()
            else:
                registro = Registro.search([("referencia", "=", item["referencia"])], limit=1)
            if not registro:
                avisos.append(_("Não encontrei a venda %s", item["referencia"]))
                continue
            if registro.estado == "emitido":
                continue
            try:
                registro.marcar_emitido(item["numero"], item["chave"])
                marcados += 1
            except UserError as erro:
                avisos.append(erro.args[0])
        self.resultado = "\n".join([_("%s nota(s) marcada(s) como emitida(s).", marcados)] + avisos)
        return {"type": "ir.actions.act_window", "res_model": self._name, "res_id": self.id, "view_mode": "form",
                "target": "new"}
