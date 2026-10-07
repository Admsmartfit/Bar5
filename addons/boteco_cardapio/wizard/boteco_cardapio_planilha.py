import base64
import io

import openpyxl
import xlsxwriter

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

# (cabeçalho na planilha, campo, tipo)
COLUNAS = [
    ("Código", "default_code", "texto"),
    ("Nome", "name", "texto"),
    ("Categoria no tablet", "pos_categ_ids", "categoria"),
    ("Preço", "list_price", "numero"),
    ("Preço happy hour", "boteco_preco_happy", "numero"),
    ("Setor (bar/chapa)", "boteco_setor_id", "setor"),
    ("+18 (sim/não)", "boteco_maior_18", "booleano"),
    ("Descrição curta", "boteco_descricao_curta", "texto"),
    ("Tempo de preparo (min)", "boteco_tempo_preparo", "inteiro"),
    ("NCM", "boteco_ncm", "texto"),
    ("CFOP", "boteco_cfop", "texto"),
    ("CST/CSOSN", "boteco_cst_csosn", "texto"),
    ("Origem (0-8)", "boteco_origem", "texto"),
    ("Unidade fiscal", "boteco_unidade_fiscal", "texto"),
    ("CEST", "boteco_cest", "texto"),
]

SIM = {"sim", "s", "x", "1", "true", "verdadeiro", "yes"}


class BotecoCardapioPlanilha(models.TransientModel):
    _name = "boteco.cardapio.planilha"
    _description = "Importar/exportar cardápio por planilha"

    arquivo = fields.Binary("Planilha (.xlsx)")
    nome_arquivo = fields.Char()
    resultado = fields.Text(readonly=True)
    so_cardapio = fields.Boolean("Só itens do cardápio (vendidos no salão)", default=True)

    # ------------------------------------------------------------------ exportar
    def action_exportar(self):
        self.ensure_one()
        domain = [("sale_ok", "=", True)]
        if self.so_cardapio:
            domain.append(("available_in_pos", "=", True))
        produtos = self.env["product.template"].search(domain, order="name")
        saida = io.BytesIO()
        livro = xlsxwriter.Workbook(saida, {"in_memory": True})
        aba = livro.add_worksheet("Cardápio")
        cab = livro.add_format({"bold": True, "bg_color": "#f59e0b", "border": 1})
        dinheiro = livro.add_format({"num_format": "#,##0.00"})
        for col, (titulo, _campo, _tipo) in enumerate(COLUNAS):
            aba.write(0, col, titulo, cab)
            aba.set_column(col, col, max(14, len(titulo) + 2))
        for lin, produto in enumerate(produtos, start=1):
            for col, (_titulo, campo, tipo) in enumerate(COLUNAS):
                valor = produto[campo]
                if tipo == "categoria":
                    valor = ", ".join(valor.mapped("name"))
                elif tipo == "setor":
                    valor = valor.codigo or ""
                elif tipo == "booleano":
                    valor = "sim" if valor else "não"
                elif tipo == "numero":
                    aba.write_number(lin, col, valor or 0.0, dinheiro)
                    continue
                aba.write(lin, col, valor if valor not in (False, None) else "")
        aba.freeze_panes(1, 2)
        livro.close()
        self.write({"arquivo": base64.b64encode(saida.getvalue()), "nome_arquivo": "cardapio.xlsx"})
        return {
            "type": "ir.actions.act_url",
            "url": "/web/content/%s/%s/arquivo/cardapio.xlsx?download=true" % (self._name, self.id),
            "target": "self",
        }

    # ------------------------------------------------------------------ importar
    @api.model
    def _ler_linhas(self, conteudo):
        try:
            livro = openpyxl.load_workbook(io.BytesIO(conteudo), read_only=True, data_only=True)
        except Exception as erro:  # noqa: BLE001
            raise UserError(_("Não consegui abrir a planilha. Salve como .xlsx e tente de novo. (%s)", erro)) from erro
        aba = livro.worksheets[0]
        linhas = list(aba.iter_rows(values_only=True))
        if not linhas:
            raise UserError(_("A planilha está vazia."))
        cabecalho = [str(c or "").strip() for c in linhas[0]]
        indice = {}
        for titulo, campo, tipo in COLUNAS:
            if titulo in cabecalho:
                indice[campo] = (cabecalho.index(titulo), tipo)
        if "name" not in indice:
            raise UserError(_("A planilha precisa da coluna 'Nome'. Use 'Exportar' para baixar o modelo."))
        return linhas[1:], indice

    def _converter(self, valor, tipo, avisos, numero_linha):
        if valor is None or (isinstance(valor, str) and not valor.strip()):
            return None
        if tipo == "numero":
            try:
                if not isinstance(valor, str):
                    return float(valor)
                texto = valor.replace("R$", "").strip()
                if "," in texto:  # formato brasileiro: 1.234,50
                    texto = texto.replace(".", "").replace(",", ".")
                return float(texto)
            except ValueError:
                avisos.append(_("Linha %(l)s: número inválido '%(v)s'", l=numero_linha, v=valor))
                return None
        if tipo == "inteiro":
            try:
                return int(float(valor))
            except ValueError:
                return None
        if tipo == "booleano":
            return str(valor).strip().lower() in SIM
        if tipo == "setor":
            setor = self.env["boteco.setor"].search([("codigo", "=", str(valor).strip().lower())], limit=1)
            if not setor:
                avisos.append(_("Linha %(l)s: setor '%(v)s' não existe", l=numero_linha, v=valor))
            return setor.id or None
        if tipo == "categoria":
            ids = []
            for nome in str(valor).split(","):
                nome = nome.strip()
                if not nome:
                    continue
                cat = self.env["pos.category"].search([("name", "=ilike", nome)], limit=1)
                if not cat:
                    cat = self.env["pos.category"].create({"name": nome})
                ids.append(cat.id)
            return [fields.Command.set(ids)]
        texto = str(valor).strip()
        if isinstance(valor, float) and valor.is_integer():
            texto = str(int(valor))
        return texto

    def action_importar(self):
        self.ensure_one()
        if not self.arquivo:
            raise UserError(_("Escolha a planilha primeiro."))
        linhas, indice = self._ler_linhas(base64.b64decode(self.arquivo))
        Produto = self.env["product.template"]
        criados = atualizados = 0
        avisos = []
        for numero, linha in enumerate(linhas, start=2):
            if not any(linha):
                continue
            vals = {}
            for campo, (col, tipo) in indice.items():
                valor = self._converter(linha[col] if col < len(linha) else None, tipo, avisos, numero)
                if valor is not None:
                    vals[campo] = valor
            if not vals.get("name"):
                avisos.append(_("Linha %s: sem nome, ignorada", numero))
                continue
            produto = Produto
            if vals.get("default_code"):
                produto = Produto.search([("default_code", "=", vals["default_code"])], limit=1)
            if not produto:
                produto = Produto.search([("name", "=ilike", vals["name"])], limit=1)
            try:
                with self.env.cr.savepoint():
                    if produto:
                        produto.write(vals)
                        atualizados += 1
                    else:
                        vals.setdefault("available_in_pos", True)
                        vals.setdefault("sale_ok", True)
                        vals.setdefault("type", "consu")
                        Produto.create(vals)
                        criados += 1
            except (ValidationError, UserError) as erro:
                avisos.append(_("Linha %(l)s (%(n)s): %(e)s", l=numero, n=vals.get("name"), e=erro.args[0]))
        resumo = [_("%(c)s itens criados, %(a)s atualizados.", c=criados, a=atualizados)]
        if avisos:
            resumo.append(_("Avisos:"))
            resumo.extend(avisos)
        self.resultado = "\n".join(resumo)
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }
