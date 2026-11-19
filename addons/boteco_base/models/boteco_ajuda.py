"""Ajuda rápida pesquisável (Etapa 26): "como faço…?" com passo a passo, caminho no menu e tela.

* O caminho é gerado do menu real (se o menu mudar de lugar, a ajuda muda sozinha).
* Só mostra caminho de menu que a pessoa enxerga; senão diz "peça ao gerente".
* A busca roda no navegador sobre um índice pequeno (artigos + telas + chaves da Central),
  então responde na hora mesmo com Wi-Fi ruim.
* Buscas sem resultado e avaliações 👍/👎 ficam registradas para escrever o próximo artigo.
"""

import os

from odoo import api, fields, models
from odoo.modules.module import get_module_path

PERFIS_AJUDA = [
    ("garcom", "Garçom"), ("caixa", "Caixa"), ("chapeiro", "Cozinha / chapa"), ("gerente", "Gerente"),
    ("cozinheiro", "Cozinha central"), ("comercial", "Comercial"), ("dono", "Dono"),
]
SEPARADOR = " › "


class BotecoAjudaArtigo(models.Model):
    _name = "boteco.ajuda.artigo"
    _description = "Artigo da ajuda rápida"
    _order = "sequencia, titulo"
    _rec_name = "titulo"

    codigo = fields.Char(required=True, index=True, help="Também é o nome da foto: static/ajuda/<codigo>.png")
    titulo = fields.Char("Título", required=True, translate=True)
    resumo = fields.Char("Para que serve", translate=True)
    sinonimos = fields.Char("Outras palavras", help="Separadas por vírgula. Ex.: zap, celular, telefone")
    passos = fields.Html("Passo a passo", sanitize=True, translate=True)
    menu_id = fields.Many2one("ir.ui.menu", string="Tela (menu)", ondelete="set null",
                              help="O caminho mostrado na ajuda é gerado deste menu.")
    caminho_manual = fields.Char("Caminho (quando não há menu)",
                                 help="Ex.: Barra de cima › botão ☀️. Usado só se não houver menu.")
    acao_xmlid = fields.Char("Abrir esta tela (ação)", help="Identificador da ação. Ex.: boteco_estoque.action_boteco_fornecedores")
    destacar_campo = fields.Char("Campo a destacar", help="Nome técnico do campo que pisca ao abrir a tela.")
    perfis = fields.Char("Perfis", help="Códigos separados por vírgula (garcom, caixa…). Vazio = todos.")
    telas = fields.Char("Aparece como ajuda das telas",
                        help="Ações (xmlid) ou modelos onde o artigo aparece em 'Ajuda desta tela'.")
    relacionados_ids = fields.Many2many("boteco.ajuda.artigo", "boteco_ajuda_artigo_rel", "artigo_id", "relacionado_id",
                                        string="Relacionados")
    imagem = fields.Image("Foto da tela", max_width=1600, max_height=1000)
    sequencia = fields.Integer(default=50)
    padrao = fields.Boolean("Veio com o sistema", default=False, readonly=True)
    active = fields.Boolean(default=True)
    uteis = fields.Integer("👍", readonly=True)
    nao_uteis = fields.Integer("👎", readonly=True)

    _sql_constraints = [("codigo_unico", "unique(codigo)", "Já existe um artigo com este código.")]

    # ------------------------------------------------------------------
    def _caminho_menu(self, menu):
        nomes = []
        while menu:
            nomes.append(menu.name)
            menu = menu.parent_id
        nomes.reverse()
        if nomes and nomes[0] == "Boteco":
            nomes = nomes[1:]
        return SEPARADOR.join(nomes)

    def _foto_url(self):
        self.ensure_one()
        if self.imagem:
            return "/web/image/boteco.ajuda.artigo/%s/imagem" % self.id
        caminho = get_module_path("boteco_base")
        if caminho and os.path.exists(os.path.join(caminho, "static", "ajuda", "%s.png" % self.codigo)):
            return "/boteco_base/static/ajuda/%s.png" % self.codigo
        return False

    @api.model
    def _perfil_atual(self):
        user = self.env.user
        if user._is_superuser() or user.has_group("boteco_base.group_dono"):
            return "dono"
        return user.boteco_perfil_id.codigo or False

    @api.model
    def indice(self):
        """Tudo o que a busca precisa, já filtrado pelo que a pessoa pode ver."""
        perfil = self._perfil_atual()
        visiveis = self.env["ir.ui.menu"]._visible_menu_ids()
        artigos = []
        for art in self.sudo().search([]):
            perfis = [p.strip() for p in (art.perfis or "").split(",") if p.strip()]
            if perfis and perfil != "dono" and perfil not in perfis:
                continue
            if art.menu_id:
                caminho = self._caminho_menu(art.menu_id) if art.menu_id.id in visiveis else False
                pode_abrir = art.menu_id.id in visiveis
            else:
                caminho = art.caminho_manual or False
                pode_abrir = bool(art.acao_xmlid)
            artigos.append({
                "id": art.id,
                "codigo": art.codigo,
                "titulo": art.titulo,
                "resumo": art.resumo or "",
                "sinonimos": art.sinonimos or "",
                "passos": art.passos or "",
                "caminho": caminho,
                "sem_acesso": bool(art.menu_id) and not pode_abrir,
                "acao": art.acao_xmlid if pode_abrir else False,
                "destacar": art.destacar_campo or False,
                "telas": [t.strip() for t in (art.telas or "").split(",") if t.strip()],
                "relacionados": art.relacionados_ids.ids,
                "foto": art._foto_url(),
            })
        # Telas: todo menu com ação que a pessoa enxerga (achar a tela mesmo sem artigo)
        telas = []
        raiz = self.env.ref("boteco_base.menu_boteco_root", raise_if_not_found=False)
        prefixo = "%s/" % raiz.id if raiz else ""
        for menu in self.env["ir.ui.menu"].sudo().browse(sorted(visiveis)):
            if menu.action and (menu.parent_path or "").startswith(prefixo):
                telas.append({"id": menu.id, "nome": menu.name, "caminho": self._caminho_menu(menu),
                              "acao": "%s,%s" % (menu.action._name, menu.action.id)})
        # Configurações: chaves da Central de Recursos (só o dono liga/desliga)
        chaves = []
        if perfil == "dono":
            empresa = self.env.company
            for nome, campo in empresa._fields.items():
                if nome.startswith("boteco_flag_"):
                    chaves.append({"campo": nome, "nome": campo.string, "ligado": bool(empresa[nome])})
        return {"artigos": artigos, "telas": telas, "chaves": chaves, "perfil": perfil}

    @api.model
    def registrar_busca(self, termo, achou, artigo_id=False, tela=False):
        termo = (termo or "").strip()[:120]
        if termo:
            self.env["boteco.ajuda.busca"].sudo().create({
                "termo": termo, "achou": bool(achou), "artigo_id": artigo_id or False, "tela": (tela or "")[:120],
            })
        return True

    @api.model
    def avaliar(self, artigo_id, util):
        artigo = self.sudo().browse(int(artigo_id)).exists()
        if artigo:
            campo = "uteis" if util else "nao_uteis"
            artigo[campo] += 1
            if not util:
                self.env["boteco.ajuda.busca"].sudo().create({"termo": artigo.titulo, "achou": True,
                                                              "artigo_id": artigo.id, "nao_ajudou": True})
        return True


class BotecoAjudaBusca(models.Model):
    _name = "boteco.ajuda.busca"
    _description = "O que estão procurando na ajuda"
    _order = "create_date desc"
    _rec_name = "termo"

    termo = fields.Char("Busca", required=True)
    usuario_id = fields.Many2one("res.users", string="Quem", default=lambda s: s.env.user, readonly=True)
    perfil = fields.Char(default=lambda s: s.env["boteco.ajuda.artigo"]._perfil_atual(), readonly=True)
    tela = fields.Char("Em qual tela")
    achou = fields.Boolean("Achou resposta")
    nao_ajudou = fields.Boolean("Disse que não ajudou")
    artigo_id = fields.Many2one("boteco.ajuda.artigo", string="Artigo", ondelete="set null")
