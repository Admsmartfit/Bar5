import base64
import io
import logging

from PIL import Image

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from .fiscal import ORIGENS, UNIDADES, formatar_ncm, pendencias_fiscais, so_digitos

_logger = logging.getLogger(__name__)

TAMANHO_FOTO = 1024

# Taxonomia semântica de consumo (Etapa 12): base do motor N+X e das regras de utensílios
TIPOS_CONSUMO = [
    ("prato_individual", "Prato individual"),
    ("prato_compartilhado", "Prato compartilhado (porção/tábua)"),
    ("sobremesa", "Sobremesa"),
    ("bebida_giro", "Bebida de giro (chope, lata, dose)"),
    ("garrafa", "Garrafa compartilhada (vinho, destilado)"),
    ("agua", "Água mineral"),
    ("outro", "Outro (sem regra)"),
]
REGRAS_UTENSILIO = [
    ("copo_cerveja", "Copo de cerveja (1ª cerveja da mesa)"),
    ("taca_vinho", "Taça de vinho + saca-rolhas"),
    ("taca_vinho_gelo", "Taça de vinho + balde com gelo (branco/rosé/espumante)"),
    ("pratos_compartilhados", "Pratos rasos + talheres + pegador"),
    ("guardanapo_reforcado", "Cesta de guardanapos reforçada (lanches/finger food)"),
]


def recortar_quadrado(imagem_b64):
    """Recorta a foto no centro, em quadrado, e limita a 1024 px (cardápio carrega rápido)."""
    if not imagem_b64:
        return imagem_b64
    try:
        dados = base64.b64decode(imagem_b64)
        img = Image.open(io.BytesIO(dados))
        if img.format == "SVG":
            return imagem_b64
        largura, altura = img.size
        lado = min(largura, altura)
        if largura == altura and lado <= TAMANHO_FOTO:
            return imagem_b64
        esquerda = (largura - lado) // 2
        topo = (altura - lado) // 2
        img = img.crop((esquerda, topo, esquerda + lado, topo + lado))
        if lado > TAMANHO_FOTO:
            img = img.resize((TAMANHO_FOTO, TAMANHO_FOTO), Image.LANCZOS)
        saida = io.BytesIO()
        if img.mode in ("RGBA", "LA", "P"):
            img.save(saida, format="PNG", optimize=True)
        else:
            img.convert("RGB").save(saida, format="JPEG", quality=85, optimize=True)
        return base64.b64encode(saida.getvalue())
    except Exception:  # noqa: BLE001 — foto ruim não pode impedir o cadastro
        _logger.warning("Não consegui recortar a foto do produto; mantendo a original", exc_info=True)
        return imagem_b64


class ProductTemplate(models.Model):
    _inherit = "product.template"

    # --- Cardápio / produção -------------------------------------------------
    boteco_setor_id = fields.Many2one(
        "boteco.setor",
        string="Setor de produção",
        help="Para onde vai o pedido deste item: bar, chapa... Vazio = não vai para produção.",
    )
    boteco_setor_codigo = fields.Char(related="boteco_setor_id.codigo", string="Código do setor")
    boteco_tempo_preparo = fields.Integer("Tempo de preparo (min)", help="Usado para o alerta de atraso.")
    boteco_descricao_curta = fields.Char("Descrição curta", size=90, translate=True,
                                         help="Aparece embaixo do nome no tablet. Até 90 letras.")
    boteco_maior_18 = fields.Boolean("+18", help="Bebida alcoólica: o primeiro pedido da mesa passa pelo garçom.")
    boteco_esgotado = fields.Boolean("Acabou", copy=False, tracking=True,
                                     help="Some do tablet e do QR na hora, sem apagar o produto.")
    boteco_esgotado_em = fields.Datetime("Acabou em", copy=False, readonly=True)
    boteco_preco_happy = fields.Float(
        "Preço happy hour", digits="Product Price",
        help="Preço durante o happy hour. Vazio ou zero = o produto não entra no happy hour.",
    )
    boteco_destaque = fields.Boolean("Destaque no tablet", help="Aparece na tela inicial do tablet.")

    # --- Consumo e utensílios (Etapa 12) --------------------------------------
    boteco_tipo_consumo = fields.Selection(
        TIPOS_CONSUMO, string="Tipo de consumo",
        help="Usado para conferir se o pedido do tablet faz sentido para o número de pessoas da mesa. "
        "Vazio = o item não entra nas regras.",
    )
    boteco_serve_pessoas = fields.Integer(
        "Serve quantas pessoas", default=1,
        help="Rendimento do item. Ex.: tábua para 3 pessoas = 3. Aparece no tablet ('Serve até 3 pessoas').",
    )
    boteco_max_por_rodada_sku = fields.Integer(
        "Máximo por rodada", default=0,
        help="Quantas unidades deste item podem ir num mesmo envio do tablet sem conferência. 0 = automático (N+1).",
    )
    boteco_regra_utensilio = fields.Selection(
        REGRAS_UTENSILIO, string="Utensílios a enviar",
        help="O que o ticket de produção manda separar junto com o item.",
    )

    @api.constrains("boteco_serve_pessoas", "boteco_max_por_rodada_sku")
    def _check_boteco_consumo(self):
        for produto in self:
            if produto.boteco_serve_pessoas < 0 or produto.boteco_max_por_rodada_sku < 0:
                raise ValidationError(_("Rendimento e máximo por rodada não podem ser negativos."))

    # --- Fiscal (para a emissão posterior) -----------------------------------
    boteco_ncm = fields.Char("NCM", help="8 números. Ex.: 2203.00.00 (cerveja de malte).")
    boteco_cest = fields.Char("CEST", help="7 números, quando houver substituição tributária.")
    boteco_cfop = fields.Char("CFOP", help="4 números. Ex.: 5102 (revenda) ou 5101 (produção própria).")
    boteco_cst_csosn = fields.Char("CST/CSOSN", help="Simples Nacional usa CSOSN (ex.: 102, 500).")
    boteco_origem = fields.Selection(ORIGENS, string="Origem da mercadoria", default="0")
    boteco_unidade_fiscal = fields.Selection(UNIDADES, string="Unidade fiscal", default="UN")
    boteco_fiscal_ok = fields.Boolean("Dados fiscais completos", compute="_compute_boteco_fiscal", store=True)
    boteco_fiscal_pendencias = fields.Char("Pendências fiscais", compute="_compute_boteco_fiscal", store=True)

    @api.depends("boteco_ncm", "boteco_cfop", "boteco_cst_csosn", "boteco_origem", "boteco_cest")
    def _compute_boteco_fiscal(self):
        for produto in self:
            erros = pendencias_fiscais(
                produto.boteco_ncm, produto.boteco_cfop, produto.boteco_cst_csosn,
                produto.boteco_origem, produto.boteco_cest,
            )
            produto.boteco_fiscal_ok = not erros
            produto.boteco_fiscal_pendencias = ", ".join(erros) if erros else False

    @api.constrains("boteco_ncm", "boteco_cfop", "boteco_cest", "boteco_cst_csosn")
    def _check_boteco_fiscal_formato(self):
        for produto in self:
            if produto.boteco_ncm and len(so_digitos(produto.boteco_ncm)) != 8:
                raise ValidationError(_("NCM de %s precisa ter 8 números.", produto.name))
            if produto.boteco_cfop and len(so_digitos(produto.boteco_cfop)) != 4:
                raise ValidationError(_("CFOP de %s precisa ter 4 números.", produto.name))
            if produto.boteco_cest and len(so_digitos(produto.boteco_cest)) != 7:
                raise ValidationError(_("CEST de %s precisa ter 7 números.", produto.name))
            if produto.boteco_cst_csosn and len(so_digitos(produto.boteco_cst_csosn)) not in (2, 3):
                raise ValidationError(_("CST/CSOSN de %s precisa ter 2 ou 3 números.", produto.name))

    @api.constrains("boteco_preco_happy", "list_price")
    def _check_boteco_preco_happy(self):
        for produto in self:
            if produto.boteco_preco_happy < 0:
                raise ValidationError(_("Preço de happy hour não pode ser negativo."))

    @api.onchange("categ_id")
    def _onchange_categ_id_boteco(self):
        """Preenche o que estiver vazio com o padrão da categoria."""
        categoria = self.categ_id
        if not categoria:
            return
        padroes = {
            "boteco_ncm": categoria.boteco_ncm_padrao,
            "boteco_cfop": categoria.boteco_cfop_padrao,
            "boteco_cst_csosn": categoria.boteco_cst_csosn_padrao,
            "boteco_setor_id": categoria.boteco_setor_padrao_id,
        }
        for campo, valor in padroes.items():
            if valor and not self[campo]:
                self[campo] = valor
        if categoria.boteco_maior_18_padrao:
            self.boteco_maior_18 = True

    # ------------------------------------------------------------------
    @api.model
    def _boteco_normalizar_vals(self, vals):
        if vals.get("image_1920"):
            vals["image_1920"] = recortar_quadrado(vals["image_1920"])
        if vals.get("boteco_ncm"):
            vals["boteco_ncm"] = formatar_ncm(vals["boteco_ncm"].strip())
        for campo in ("boteco_cfop", "boteco_cest", "boteco_cst_csosn"):
            if vals.get(campo):
                vals[campo] = so_digitos(vals[campo])
        return vals

    @api.model
    def _boteco_padroes_categoria(self, vals):
        """No create, aplica os padrões da categoria nos campos não informados."""
        categoria = self.env["product.category"].browse(vals.get("categ_id")) if vals.get("categ_id") else None
        if not categoria:
            return vals
        padroes = {
            "boteco_ncm": categoria.boteco_ncm_padrao,
            "boteco_cfop": categoria.boteco_cfop_padrao,
            "boteco_cst_csosn": categoria.boteco_cst_csosn_padrao,
            "boteco_origem": categoria.boteco_origem_padrao,
            "boteco_unidade_fiscal": categoria.boteco_unidade_fiscal_padrao,
            "boteco_setor_id": categoria.boteco_setor_padrao_id.id,
            "boteco_maior_18": categoria.boteco_maior_18_padrao,
        }
        for campo, valor in padroes.items():
            if valor and not vals.get(campo):
                vals[campo] = valor
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [self._boteco_padroes_categoria(self._boteco_normalizar_vals(dict(v))) for v in vals_list]
        return super().create(vals_list)

    def write(self, vals):
        vals = self._boteco_normalizar_vals(dict(vals))
        if "boteco_esgotado" in vals:
            vals["boteco_esgotado_em"] = fields.Datetime.now() if vals["boteco_esgotado"] else False
            # "Acabou" usa o mecanismo nativo do autoatendimento, que já avisa os tablets em tempo real
            vals["self_order_available"] = not vals["boteco_esgotado"]
        res = super().write(vals)
        if {"boteco_esgotado", "boteco_preco_happy", "list_price"} & set(vals):
            self.env["pos.config"]._boteco_avisar_cardapio()
        return res

    def _boteco_campos_preco_auditados(self):
        campos = super()._boteco_campos_preco_auditados()
        campos["boteco_preco_happy"] = "Preço happy hour"
        return campos

    # ------------------------------------------------------------------
    def action_boteco_acabou(self):
        self.write({"boteco_esgotado": True})
        return True

    def action_boteco_voltou(self):
        self.write({"boteco_esgotado": False})
        return True


class ProductProduct(models.Model):
    _inherit = "product.product"

    @api.model
    def _load_pos_data_fields(self, config_id):
        campos = super()._load_pos_data_fields(config_id)
        return campos + [
            "boteco_preco_happy",
            "boteco_esgotado",
            "boteco_maior_18",
            "boteco_setor_codigo",
            "boteco_descricao_curta",
            "boteco_destaque",
            "boteco_tempo_preparo",
            "boteco_tipo_consumo",
            "boteco_serve_pessoas",
            "boteco_max_por_rodada_sku",
            "boteco_regra_utensilio",
        ]

    def _boteco_preco_promocional(self, momento=None, qtd=1.0):
        """Preço promocional vigente: (preço, origem, oferta) ou None.

        Prioridade: oferta relâmpago com saldo > happy hour > nenhum.
        """
        self.ensure_one()
        oferta = self.env["boteco.oferta.relampago"].sudo()._oferta_ativa(self, momento=momento)
        if oferta and oferta.restante >= qtd:
            return oferta.preco, "oferta", oferta
        if self.boteco_preco_happy and self.env["boteco.happy.hour"].sudo()._ativo_em(momento):
            return self.boteco_preco_happy, "happy", None
        return None
