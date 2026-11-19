"""Assistente de primeira configuração em 5 etapas (PRD de onboarding, 19/11/2026).

Meta: do primeiro login ao primeiro pedido de teste em menos de 15 minutos, sem abrir as telas
completas do ERP. Cada etapa grava só o essencial e pode ser pulada (o passo fica pendente na lista).
"""

import logging
import re
import unicodedata

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

TEMPO_API = 4  # segundos: API fora do ar não pode congelar a tela (campos manuais aparecem na hora)
FUSOS = [
    ("America/Sao_Paulo", "Brasília (SP, RJ, MG, ES, Sul, NE, GO, DF)"),
    ("America/Manaus", "Amazonas (-1h)"),
    ("America/Cuiaba", "Mato Grosso / MS (-1h)"),
    ("America/Porto_Velho", "Rondônia (-1h)"),
    ("America/Boa_Vista", "Roraima (-1h)"),
    ("America/Rio_Branco", "Acre (-2h)"),
    ("America/Noronha", "Fernando de Noronha (+1h)"),
]
CATEGORIAS_BASICAS = ["Bebidas", "Porções", "Sobremesas"]


def so_digitos(texto):
    return re.sub(r"\D", "", texto or "")


def login_de(nome):
    base = unicodedata.normalize("NFKD", nome or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", ".", base).strip(".") or "pessoa"


class ResCompany(models.Model):
    _inherit = "res.company"

    boteco_razao_social = fields.Char("Razão social")
    boteco_modo_atendimento = fields.Char("Como os clientes pedem", help="garcom, qr, balcao (separados por vírgula)")
    boteco_flag_autoatendimento_qr = fields.Boolean(
        "Autoatendimento: QR Code e tablets nas mesas", default=True,
        help="Desligado, os menus de tablets e celulares do QR somem (os dados ficam guardados).")


class BotecoImplantacao(models.AbstractModel):
    _inherit = "boteco.implantacao"

    # ------------------------------------------------------------------ etapa 1: identidade
    @api.model
    def buscar_cnpj(self, cnpj):
        """Dados públicos do CNPJ (BrasilAPI). Falhou? Devolve erro e a tela segue com os campos manuais."""
        self._exigir_dono()
        numero = so_digitos(cnpj)
        if len(numero) != 14:
            return {"erro": _("O CNPJ tem 14 números.")}
        try:
            r = requests.get("https://brasilapi.com.br/api/cnpj/v1/%s" % numero, timeout=TEMPO_API)
            if r.status_code != 200:
                return {"erro": _("Não achei esse CNPJ. Preencha os campos à mão.")}
            d = r.json()
        except (requests.RequestException, ValueError):
            _logger.info("Busca de CNPJ indisponível", exc_info=True)
            return {"erro": _("A busca do CNPJ está fora do ar agora. Preencha os campos à mão.")}
        rua = " ".join(p for p in [d.get("descricao_tipo_de_logradouro"), d.get("logradouro")] if p)
        return {
            "razao_social": (d.get("razao_social") or "").title(),
            "nome": (d.get("nome_fantasia") or d.get("razao_social") or "").title(),
            "rua": ("%s, %s" % (rua.title(), d.get("numero"))) if d.get("numero") else rua.title(),
            "bairro": (d.get("bairro") or "").title(),
            "cep": so_digitos(d.get("cep")),
            "cidade": (d.get("municipio") or "").title(),
            "uf": d.get("uf") or "",
            "telefone": d.get("ddd_telefone_1") or "",
        }

    @api.model
    def buscar_cep(self, cep):
        self._exigir_dono()
        numero = so_digitos(cep)
        if len(numero) != 8:
            return {"erro": _("O CEP tem 8 números.")}
        try:
            r = requests.get("https://brasilapi.com.br/api/cep/v1/%s" % numero, timeout=TEMPO_API)
            if r.status_code != 200:
                return {"erro": _("Não achei esse CEP. Preencha o endereço à mão.")}
            d = r.json()
        except (requests.RequestException, ValueError):
            return {"erro": _("A busca do CEP está fora do ar agora. Preencha o endereço à mão.")}
        return {"rua": d.get("street") or "", "bairro": d.get("neighborhood") or "", "cidade": d.get("city") or "",
                "uf": d.get("state") or ""}

    @api.model
    def salvar_identidade(self, dados):
        self._exigir_dono()
        company = self.env.company.sudo()
        if not (dados.get("nome") or "").strip():
            raise UserError(_("Digite o nome do boteco."))
        estado = self.env["res.country.state"].search(
            [("code", "=", (dados.get("uf") or "").upper()), ("country_id.code", "=", "BR")], limit=1)
        vals = {
            "name": dados["nome"].strip(), "boteco_razao_social": (dados.get("razao_social") or "").strip() or False,
            "vat": dados.get("cnpj") or False, "street": dados.get("rua") or False,
            "street2": dados.get("bairro") or False, "zip": dados.get("cep") or False,
            "city": dados.get("cidade") or False, "state_id": estado.id or False,
            "country_id": self.env.ref("base.br").id, "phone": dados.get("telefone") or False,
        }
        if dados.get("logo"):
            vals["logo"] = dados["logo"].split(",", 1)[-1]  # aceita "data:image/png;base64,..."
        company.write(vals)
        fuso = dados.get("fuso") or "America/Sao_Paulo"
        if fuso in dict(FUSOS):
            company.partner_id.tz = fuso
            self.env.user.sudo().tz = fuso
        return self.assistente_dados()

    # ------------------------------------------------------------------ etapa 2: entrevista
    @api.model
    def salvar_operacao(self, dados):
        """Como pedem, se produz em lote e os ambientes: liga/esconde módulos e monta o mapa de mesas."""
        self._exigir_dono()
        company = self.env.company.sudo()
        modos = [m for m in (dados.get("atendimento") or []) if m in ("garcom", "qr", "balcao")] or ["garcom"]
        company.write({
            "boteco_modo_atendimento": ",".join(modos),
            "boteco_flag_autoatendimento_qr": "qr" in modos,
            "boteco_tipo_unidade": "bar_e_cozinha" if dados.get("producao_lote") else "bar",
        })
        criadas = self._criar_ambientes(dados.get("ambientes") or [])
        return {**self.assistente_dados(), "mesas_criadas": criadas}

    @api.model
    def _criar_ambientes(self, ambientes):
        config = self.env["pos.config"].sudo().search(
            [("module_pos_restaurant", "=", True), ("company_id", "=", self.env.company.id)], limit=1)
        if not config:
            return 0
        Planta = self.env["restaurant.floor"].sudo()
        Mesa = self.env["restaurant.table"].sudo()
        numero = max(Mesa.search([]).mapped("table_number") or [0])
        criadas = 0
        for amb in ambientes:
            nome = (amb.get("nome") or "").strip()
            qtd = min(max(int(amb.get("mesas") or 0), 0), 80)
            lugares = min(max(int(amb.get("lugares") or 4), 1), 30)
            if not nome or not qtd:
                continue
            planta = Planta.search([("name", "=ilike", nome)], limit=1)
            if planta and planta.table_ids:
                continue  # já existe com mesas: não mexe no que o dono montou
            planta = planta or Planta.create({"name": nome, "pos_config_ids": [fields.Command.link(config.id)]})
            for i in range(qtd):
                numero += 1
                Mesa.create({"floor_id": planta.id, "table_number": numero, "seats": lugares, "shape": "square",
                             "position_h": 30 + (i % 6) * 140, "position_v": 30 + (i // 6) * 140,
                             "width": 110, "height": 110})
                criadas += 1
        return criadas

    # ------------------------------------------------------------------ etapa 3: cardápio
    @api.model
    def preparar_cardapio(self):
        """Cria as categorias básicas (se faltarem) e diz como está o cardápio."""
        self._exigir_dono()
        Categoria = self.env["pos.category"].sudo()
        for nome in CATEGORIAS_BASICAS:
            if not Categoria.search_count([("name", "=ilike", nome)]):
                Categoria.create({"name": nome})
        return self.assistente_dados()

    @api.model
    def ligar_happy_hour(self, ligar):
        self._exigir_dono()
        happy = self.env.ref("boteco_cardapio.happy_hour_padrao", raise_if_not_found=False)
        if happy:
            happy.sudo().active = bool(ligar)
        return self.assistente_dados()

    # ------------------------------------------------------------------ etapa 4: impressoras
    @api.model
    def salvar_impressora(self, setor_id, ip):
        """IP da impressora de um setor (Bar, Chapa…). Cria a impressora se for nova e liga a rota."""
        self._exigir_dono()
        setor = self.env["boteco.setor"].sudo().browse(int(setor_id)).exists()
        ip = (ip or "").strip()
        if not setor or not re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", ip):
            raise UserError(_("Digite o IP da impressora (ex.: 192.168.0.50). Ele sai no papel de teste da própria impressora."))
        Impressora = self.env["boteco.impressora"].sudo()
        impressora = Impressora.search([("ip", "=", ip)], limit=1) or Impressora.create(
            {"name": _("Impressora %s", setor.name), "ip": ip, "linguagem": "escpos"})
        setor.impressora_id = impressora
        impressora.action_verificar()
        return self.assistente_dados()

    @api.model
    def testar_impressora(self, impressora_id):
        self._exigir_dono()
        impressora = self.env["boteco.impressora"].sudo().browse(int(impressora_id)).exists()
        if not impressora:
            return {"ok": False, "mensagem": _("Impressora não encontrada.")}
        try:
            impressora.action_imprimir_teste()
            impressora.action_verificar()
        except Exception as erro:  # noqa: BLE001 — mostra o problema em vez de travar
            return {"ok": False, "mensagem": _("Não imprimiu: %s. Confira se está ligada e no mesmo Wi-Fi.", erro)}
        if impressora.estado != "ok":
            return {"ok": False, "mensagem": impressora.ultimo_erro or _("A impressora não respondeu.")}
        return {"ok": True, "mensagem": _("Papel de teste enviado. Saiu? Então está pronta.")}

    # ------------------------------------------------------------------ etapa 5: equipe e treino
    @api.model
    def criar_equipe(self, pessoas):
        """Linhas {nome, perfil (gerente|caixa|garcom), pin}. Devolve os erros por linha (o resto é gravado)."""
        self._exigir_dono()
        Users = self.env["res.users"].sudo()
        erros = []
        for i, p in enumerate(pessoas or []):
            nome = (p.get("nome") or "").strip()
            if not nome:
                continue
            perfil = self.env["boteco.perfil"].sudo().search([("codigo", "=", p.get("perfil") or "garcom")], limit=1)
            login = login_de(nome)
            sufixo = 1
            while Users.with_context(active_test=False).search_count([("login", "=", login)]):
                sufixo += 1
                login = "%s%s" % (login_de(nome), sufixo)
            try:
                with self.env.cr.savepoint():
                    user = Users.create({"name": nome, "login": login, "boteco_perfil_id": perfil.id})
                    user._boteco_definir_pin(str(p.get("pin") or ""))
            except (UserError, ValidationError) as erro:
                erros.append({"linha": i, "erro": str(erro.args[0])})
        return {**self.assistente_dados(), "erros": erros}

    @api.model
    def ligar_treino(self):
        """Pede ao servidor para (re)criar o banco de treino (cópia de agora) e ligar o https://…:8443."""
        self._exigir_dono()
        self.env["boteco.atualizacao"].sudo()._gravar_pedido("treino")
        return {"ok": True, "mensagem": _("Pedido enviado. Em 1 a 2 minutos o treino abre na porta 8443 (faixa vermelha). "
                                          "Lá, faça a venda de teste: nada entra no caixa nem no estoque de verdade.")}

    @api.model
    def pular_etapa(self, etapa):
        """'Pular por enquanto': segue para a próxima etapa; o passo da lista continua pendente."""
        self._exigir_dono()
        return self.assistente_dados()

    # ------------------------------------------------------------------ dados da tela
    @api.model
    def assistente_dados(self):
        company = self.env.company
        setores = self.env["boteco.setor"].sudo().search([("company_id", "in", [company.id, False])])
        happy = self.env.ref("boteco_cardapio.happy_hour_padrao", raise_if_not_found=False)
        itens = self.env["product.template"].sudo().search_count([("available_in_pos", "=", True), ("sale_ok", "=", True)])
        return {
            "empresa": {
                "nome": company.name or "", "razao_social": company.boteco_razao_social or "", "cnpj": company.vat or "",
                "rua": company.street or "", "bairro": company.street2 or "", "cep": company.zip or "",
                "cidade": company.city or "", "uf": company.state_id.code or "", "telefone": company.phone or "",
                "fuso": company.partner_id.tz or "America/Sao_Paulo", "tem_logo": bool(company.logo),
            },
            "fusos": FUSOS,
            "operacao": {
                "atendimento": (company.boteco_modo_atendimento or "garcom").split(","),
                "producao_lote": company.boteco_tipo_unidade in ("bar_e_cozinha", "cozinha_central"),
                "ambientes": [{"nome": f.name, "mesas": len(f.table_ids)}
                              for f in self.env["restaurant.floor"].sudo().search([])],
            },
            "cardapio": {"itens": itens, "happy_hour": bool(happy and happy.active),
                         "categorias": self.env["pos.category"].sudo().search_count([])},
            "setores": [{"id": s.id, "nome": s.name, "impressora_id": s.impressora_id.id,
                         "ip": s.impressora_id.ip or "", "estado": s.impressora_id.estado or ""} for s in setores],
            "equipe": [{"nome": u.name, "perfil": u.boteco_perfil_id.name}
                       for u in self.env["res.users"].sudo().search(
                           [("boteco_perfil_id", "!=", False), ("share", "=", False), ("boteco_pin_hash", "!=", False)])],
        }

    @api.model
    def resumo(self):
        """Caixa da barra de cima: além da contagem, o próximo passo obrigatório ('Falta: Impressoras')."""
        dados = super().resumo()
        if dados.get("mostrar"):
            estado = self.estado()
            proximo = next((p for f in estado["fases"] if f["codigo"] != "depois" for p in f["passos"]
                            if p["obrigatorio"] and p["situacao"] != "feito"), None)
            dados["proximo"] = proximo["titulo"] if proximo else ""
        return dados

    @api.model
    def reabrir_assistente(self):
        self._exigir_dono()
        self.env.company.sudo().boteco_assistente_visto = False
        return True
