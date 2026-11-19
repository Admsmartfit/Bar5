"""Primeiros passos (Etapa 33): do sistema recém-instalado até "abrir a casa".

* Assistente curto (3 telas) na primeira entrada do dono: só o que bloqueia (empresa e tipo de negócio).
* Lista persistente em 4 fases, que se marca sozinha: cada passo tem uma verificação no banco.
* Banco que já está em uso: as verificações já passam e o assistente não abre.
"""

from odoo import _, api, fields, models
from odoo.exceptions import UserError

FASES = [
    ("empresa", "1. Sua empresa"),
    ("equipe", "2. Sua equipe"),
    ("salao", "3. Seu salão e cardápio"),
    ("abrir", "4. Testar e abrir"),
    ("depois", "Depois de abrir"),
]

# codigo, fase, titulo, explicacao, obrigatorio, tipo (auto|visita|manual), acao (xmlid ou método), artigo de ajuda, modelo exigido
PASSOS = [
    ("empresa_dados", "empresa", "Dados da empresa e logo",
     "Nome, CNPJ, endereço e logo: saem no ticket, no tablet e nas notas.", True, "auto", "_acao_empresa", None, None),
    ("redes", "empresa", "Wi-Fi dos clientes e da equipe",
     "Garante que só quem está no bar consegue pedir pelo QR Code.", False, "auto", "_acao_wifi", None, None),
    ("equipe_pin", "equipe", "Cadastrar a equipe com perfil e PIN",
     "Pelo menos um gerente ou caixa e um garçom, cada um com o seu PIN.", True, "auto",
     "boteco_base.action_boteco_pessoas", "cadastrar_pessoa_pin", None),
    ("permissoes", "equipe", "Revisar as permissões de cada perfil",
     "Decida o que o caixa e o garçom podem fazer sem chamar o gerente.", False, "visita",
     "boteco_base.action_boteco_perfil", "permissoes_perfil", None),
    ("mesas", "salao", "Mesas e lugares do salão",
     "Os lugares de cada mesa decidem os copos e a conferência dos pedidos do tablet.", True, "auto",
     "pos_restaurant.action_restaurant_floor_form", "mesas_plantas", "restaurant.table"),
    ("impressoras", "salao", "Impressoras do bar e da chapa (imprimir teste)",
     "Cada setor com a sua impressora, e o papel de teste saindo.", True, "auto",
     "boteco_base.action_boteco_impressora", "impressora_cadastrar", None),
    ("cardapio", "salao", "Cardápio: pelo menos 10 itens com setor",
     "Foto, preço e para onde vai (bar ou chapa). Dá para importar por planilha.", True, "auto",
     "boteco_cardapio.action_boteco_cardapio", "cardapio_item", "boteco.happy.hour"),
    ("consumo", "salao", "Tipo de consumo e utensílios dos itens",
     "Ensina o sistema a conferir os pedidos do tablet e a mandar copos e pratos.", False, "auto",
     "boteco_cardapio.action_boteco_cardapio", "tipo_consumo", "boteco.happy.hour"),
    ("fiscal", "salao", "Dados fiscais dos itens",
     "NCM, CFOP e CST para a nota ser emitida depois.", False, "auto",
     "boteco_cardapio.action_boteco_produtos_sem_fiscal", "dados_fiscais", "boteco.happy.hour"),
    ("pagamentos", "salao", "Formas de pagamento, taxa de serviço e couvert",
     "Cartão e Pix além do dinheiro, a taxa de 10% e o couvert dos dias de música.", True, "auto",
     "point_of_sale.action_pos_payment_method_form", "maquininha_link", "pos.payment.method"),
    ("qr_mesas", "salao", "Imprimir os QR Codes das mesas",
     "Cartões para plastificar e deixar em cada mesa.", False, "visita",
     "point_of_sale.action_pos_config_kanban", "qr_mesas", None),
    ("venda_teste", "abrir", "Venda de teste do começo ao fim",
     "Abrir caixa, pedir numa mesa, sair no bar e na chapa, pagar e fechar o caixa. "
     "Faça no modo treinamento (não entra no faturamento).", True, "manual", None, "abrir_caixa", None),
    ("treinar", "abrir", "Treinar a equipe por função",
     "Cada pessoa entra com o PIN e vê o passo a passo curto do seu perfil.", False, "auto", None, "ajuda_usar", None),
    ("fornecedores", "depois", "Fornecedores com WhatsApp",
     "Para a lista de compras e o radar de preços.", False, "auto",
     "boteco_estoque.action_boteco_fornecedores", "whatsapp_fornecedor", "boteco.historico.preco"),
    ("fichas", "depois", "Fichas técnicas e estoque inicial",
     "Com as fichas, cada venda baixa os insumos e o CMV fica certo.", False, "auto",
     "mrp.mrp_bom_form_action", "fichas_tecnicas", "boteco.contagem"),
    ("cozinha", "depois", "Cozinha central: receitas, capacidade e freezers",
     "Só se você tem cozinha central.", False, "auto",
     "boteco_cozinha_central.action_boteco_plano_producao", "plano_producao", "boteco.temperatura"),
    ("recursos", "depois", "Revisar a Central de Recursos",
     "Ligue só o que faz sentido para o seu boteco.", False, "visita",
     "boteco_base.action_boteco_central_recursos", "recursos_ligar", None),
    ("backup", "depois", "Backup funcionando",
     "Último backup com menos de 48 horas.", False, "auto", "boteco_base.action_boteco_saude_url", "saude_sistema", None),
]
PAGOS = ("paid", "done", "invoiced")


class ResCompany(models.Model):
    _inherit = "res.company"

    boteco_implantacao_concluida = fields.Boolean("Implantação concluída", copy=False)
    boteco_implantacao_concluida_em = fields.Datetime("Casa aberta em", copy=False, readonly=True)
    boteco_assistente_visto = fields.Boolean("Assistente inicial visto", copy=False)


class BotecoImplantacaoEstado(models.Model):
    _name = "boteco.implantacao.estado"
    _description = "Primeiros passos: situação de cada passo"
    _rec_name = "codigo"

    company_id = fields.Many2one("res.company", required=True, default=lambda s: s.env.company, ondelete="cascade")
    codigo = fields.Char(required=True)
    situacao = fields.Selection([("feito", "Feito"), ("pulado", "Pulado")], required=True)
    usuario_id = fields.Many2one("res.users", default=lambda s: s.env.user)

    _sql_constraints = [("passo_unico", "unique(company_id, codigo)", "Passo repetido.")]


class BotecoImplantacao(models.AbstractModel):
    _name = "boteco.implantacao"
    _description = "Primeiros passos (implantação)"

    # ------------------------------------------------------------------ verificações (True = feito)
    def _v_empresa_dados(self, c):
        return bool(c.vat and (c.street or c.city))

    def _v_redes(self, c):
        return bool(c.boteco_rede_clientes or c.boteco_rede_sistema)

    def _v_equipe_pin(self, c):
        com_pin = self.env["res.users"].sudo().search([("boteco_pin_hash", "!=", False), ("share", "=", False)])
        perfis = set(com_pin.mapped("boteco_perfil_id.codigo"))
        return bool(perfis & {"gerente", "caixa"}) and "garcom" in perfis

    def _v_mesas(self, c):
        return bool(self.env["restaurant.table"].sudo().search_count([("seats", ">", 0), ("active", "=", True)]))

    def _v_impressoras(self, c):
        setores = self.env["boteco.setor"].sudo().search([("company_id", "in", [c.id, False])])
        return bool(setores) and all(s.impressora_id and s.impressora_id.estado == "ok" for s in setores)

    def _itens_venda(self):
        return self.env["product.template"].sudo().search([("available_in_pos", "=", True), ("sale_ok", "=", True),
                                                           ("boteco_setor_id", "!=", False)])

    def _v_cardapio(self, c):
        return len(self._itens_venda()) >= 10

    def _v_consumo(self, c):
        itens = self._itens_venda()
        return bool(itens) and len(itens.filtered("boteco_tipo_consumo")) >= 0.8 * len(itens)

    def _v_fiscal(self, c):
        return not self.env["product.template"].sudo().search_count(
            [("available_in_pos", "=", True), ("sale_ok", "=", True), ("boteco_fiscal_ok", "=", False),
             ("type", "!=", "service")])

    def _v_pagamentos(self, c):
        return bool(self.env["pos.payment.method"].sudo().search_count([("is_cash_count", "=", False)]))

    def _v_venda_teste(self, c):
        # Já vendendo de verdade = o teste já passou
        return bool(self.env["pos.order"].sudo().search_count([("state", "in", PAGOS)], limit=1))

    def _v_treinar(self, c):
        pessoas = self.env["res.users"].sudo().search([("boteco_perfil_id", "!=", False), ("share", "=", False)])
        return bool(pessoas) and all(pessoas.mapped("boteco_tour_visto"))

    def _v_fornecedores(self, c):
        return bool(self.env["res.partner"].sudo().search_count([("supplier_rank", ">", 0), ("mobile", "!=", False)]))

    def _v_fichas(self, c):
        return bool(self.env["mrp.bom"].sudo().search_count([])) and bool(
            self.env["boteco.contagem"].sudo().search_count([]))

    def _v_cozinha(self, c):
        return bool(self.env["mrp.bom"].sudo().search_count([("product_tmpl_id.boteco_produzido_cozinha", "=", True)]))

    def _v_backup(self, c):
        itens = self.env["boteco.saude"]._verificar_backup()
        return bool(itens) and itens[0]["estado"] == "ok"

    # ------------------------------------------------------------------
    def _passos_aplicaveis(self, company):
        tem_cozinha = company.boteco_tipo_unidade in ("cozinha_central", "bar_e_cozinha")
        for passo in PASSOS:
            codigo, _fase, _t, _e, _ob, _tipo, _acao, _art, modelo = passo
            if modelo and modelo not in self.env:
                continue
            if codigo == "cozinha" and not tem_cozinha:
                continue
            yield passo

    @api.model
    def estado(self):
        """Fases e passos com a situação de cada um (verificado agora)."""
        company = self.env.company
        registrados = {e.codigo: e.situacao for e in self.env["boteco.implantacao.estado"].sudo().search(
            [("company_id", "=", company.id)])}
        fases = {codigo: {"codigo": codigo, "nome": nome, "passos": []} for codigo, nome in FASES}
        for codigo, fase, titulo, explicacao, obrigatorio, tipo, acao, artigo, _modelo in self._passos_aplicaveis(company):
            verificar = getattr(self, "_v_%s" % codigo, None)
            if verificar and verificar(company):
                situacao = "feito"
            else:
                situacao = registrados.get(codigo, "pendente")
            fases[fase]["passos"].append({
                "codigo": codigo, "titulo": titulo, "explicacao": explicacao, "obrigatorio": obrigatorio,
                "tipo": tipo, "tem_acao": bool(acao), "artigo": artigo, "situacao": situacao,
            })
        lista = [f for f in fases.values() if f["passos"]]
        obrigatorios = [p for f in lista for p in f["passos"] if p["obrigatorio"] and f["codigo"] != "depois"]
        feitos = [p for p in obrigatorios if p["situacao"] == "feito"]
        return {
            "fases": lista,
            "total": len(obrigatorios),
            "feitos": len(feitos),
            "faltam": len(obrigatorios) - len(feitos),
            "concluida": company.boteco_implantacao_concluida,
            "assistente": not company.boteco_assistente_visto and not company.boteco_implantacao_concluida,
            "empresa": {"nome": company.name, "cnpj": company.vat or "", "rua": company.street or "",
                        "cidade": company.city or "", "telefone": company.phone or "",
                        "tipo_unidade": company.boteco_tipo_unidade or "bar"},
        }

    def _exigir_dono(self):
        if not (self.env.user._is_superuser() or self.env.user.has_group("boteco_base.group_dono")):
            raise UserError(_("Só o dono configura a implantação."))

    @api.model
    def acao(self, codigo):
        """Ação de "Fazer agora". Passos do tipo visita contam como feitos ao abrir."""
        self._exigir_dono()
        passo = next((p for p in PASSOS if p[0] == codigo), None)
        if not passo or not passo[6]:
            raise UserError(_("Passo sem tela."))
        if passo[5] == "visita":
            self._marcar(codigo, "feito")
        alvo = passo[6]
        if alvo.startswith("_"):
            return getattr(self, alvo)()
        return self.env["ir.actions.actions"]._for_xml_id(alvo)

    def _acao_empresa(self):
        """Etapa 1 do assistente (só CNPJ, endereço, logo e fuso), não o cadastro completo da empresa."""
        self.env.company.sudo().boteco_assistente_visto = False
        return self.env["ir.actions.actions"]._for_xml_id("boteco_base.action_boteco_primeiros_passos")

    def _acao_wifi(self):
        return self.env["boteco.wifi"].abrir()

    def _marcar(self, codigo, situacao):
        Estado = self.env["boteco.implantacao.estado"].sudo()
        atual = Estado.search([("company_id", "=", self.env.company.id), ("codigo", "=", codigo)])
        if atual:
            atual.write({"situacao": situacao, "usuario_id": self.env.user.id})
        else:
            Estado.create({"codigo": codigo, "situacao": situacao})

    @api.model
    def marcar(self, codigo, situacao):
        """'Pular por enquanto' (passos opcionais) ou 'Já fiz' (passos manuais)."""
        self._exigir_dono()
        passo = next((p for p in PASSOS if p[0] == codigo), None)
        if not passo:
            raise UserError(_("Passo desconhecido."))
        if situacao == "pulado" and passo[4]:
            raise UserError(_("Este passo é obrigatório para abrir a casa."))
        if situacao == "feito" and passo[5] != "manual":
            raise UserError(_("Este passo se marca sozinho quando estiver feito."))
        self._marcar(codigo, situacao)
        return self.estado()

    @api.model
    def salvar_assistente(self, dados):
        """Assistente das 3 telas: grava a empresa e o tipo de negócio."""
        self._exigir_dono()
        company = self.env.company.sudo()
        vals = {"boteco_assistente_visto": True}
        mapa = {"nome": "name", "cnpj": "vat", "rua": "street", "cidade": "city", "telefone": "phone"}
        for chave, campo in mapa.items():
            if dados.get(chave) is not None and dados.get(chave) != "":
                vals[campo] = dados[chave]
        if dados.get("tipo_unidade") in ("bar", "bar_e_cozinha", "cozinha_central"):
            vals["boteco_tipo_unidade"] = dados["tipo_unidade"]
        company.write(vals)
        return self.estado()

    @api.model
    def concluir(self, forcar=False):
        """'Abrir a casa'. Com passo obrigatório pendente só com confirmação (fica na auditoria)."""
        self._exigir_dono()
        estado = self.estado()
        if estado["faltam"] and not forcar:
            raise UserError(_("Ainda faltam %s passo(s) obrigatório(s).", estado["faltam"]))
        company = self.env.company.sudo()
        # Concluiu: a caixa some da barra e a chave "Primeiros passos" fica desligada na Central de Recursos
        company.write({"boteco_implantacao_concluida": True, "boteco_implantacao_concluida_em": fields.Datetime.now(),
                       "boteco_assistente_visto": True, "boteco_flag_assistente_implantacao": False})
        self.env["boteco.auditoria"].registrar(
            "outro", descricao=_("Casa aberta: implantação concluída (%s de %s passos obrigatórios)",
                                 estado["feitos"], estado["total"]))
        return True

    @api.model
    def resumo(self):
        """Caixa "Primeiros passos" na barra de cima: só para o dono e enquanto não terminar."""
        if not self.pendente_para(self.env.user):
            return {"mostrar": False}
        estado = self.estado()
        return {"mostrar": True, "feitos": estado["feitos"], "total": estado["total"], "faltam": estado["faltam"]}

    @api.model
    def pendente_para(self, user):
        """True se a tela inicial do dono deve ser os Primeiros passos."""
        company = self.env.company
        if not company.boteco_recurso_ativo("assistente_implantacao") or company.boteco_implantacao_concluida:
            return False
        return bool(user._is_superuser() or user.has_group("boteco_base.group_dono") or user._is_admin())

    @api.model
    def _marcar_banco_em_uso(self):
        """Na atualização: banco que já vende não vê o assistente das 3 telas (só a lista do que falta)."""
        for company in self.env["res.company"].sudo().search([]):
            if self.env["pos.order"].sudo().search_count([("company_id", "=", company.id)], limit=1):
                company.boteco_assistente_visto = True
        return True
