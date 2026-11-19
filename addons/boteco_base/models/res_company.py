from datetime import datetime, time, timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError

TIPOS_UNIDADE = [
    ("bar", "Bar"),
    ("cozinha_central", "Cozinha central"),
    ("bar_e_cozinha", "Bar e cozinha central"),
]


class ResCompany(models.Model):
    _inherit = "res.company"

    boteco_tipo_unidade = fields.Selection(
        TIPOS_UNIDADE,
        string="Tipo de unidade",
        help="Como esta empresa aparece no boteco. Use 'Bar e cozinha central' quando o "
        "contador decidir por um CNPJ só (dois armazéns na mesma empresa).",
    )
    boteco_hora_virada = fields.Float(
        string="Hora em que o dia vira",
        default=6.0,
        help="O 'dia de operação' vai desta hora até a mesma hora do dia seguinte. "
        "Uma venda às 2h da madrugada de sábado conta na sexta.",
    )
    boteco_rede_clientes = fields.Char(
        string="Rede Wi-Fi dos clientes",
        help="Faixas de IP (ex.: 192.168.20.0/24) de onde o QR Code da mesa pode fazer pedido. "
        "Vazio = qualquer rede.",
    )
    boteco_rede_sistema = fields.Char(
        string="Rede do sistema",
        help="Faixas de IP dos aparelhos da equipe. A tela de login por PIN só aparece nelas. "
        "Vazio = qualquer rede.",
    )
    boteco_registro_sanitario = fields.Char(
        string="Registro sanitário",
        help="Número do registro na Vigilância Sanitária, impresso nas etiquetas.",
    )

    # ------------------------------------------------------------------
    # Central de Recursos (Liga/Desliga) — Etapa 11 do PRD Master
    # Toda regra nova checa company.boteco_recurso_ativo("<codigo>") antes de rodar.
    # ------------------------------------------------------------------
    # Grupo 1: Validação inteligente de pedidos e salão
    boteco_flag_ocupacao_padrao_mesa = fields.Boolean(
        string="Sugerir capacidade padrão na abertura da mesa", default=True,
        help="Ao abrir a mesa, o número de clientes já vem com os lugares cadastrados da mesa.",
    )
    boteco_flag_salao_juncao_mesas = fields.Boolean(
        string="Juntar mesas somando o número de clientes", default=False,
    )
    boteco_flag_tablet_neutro_anti_burst = fields.Boolean(
        string="Tablet neutro (sem ajuste de clientes) + trava anti-toque repetido", default=True,
    )
    boteco_flag_tablet_chamada_qualificada = fields.Boolean(
        string="Botões de chamada qualificada no tablet (copos/gelo, guardanapos, conta)",
        default=False,
    )
    boteco_flag_quarentena_pedidos_anomalos = fields.Boolean(
        string="Motor de quarentena (N+X): barrar pedidos fora do padrão e alertar garçom/caixa",
        default=True,
    )
    boteco_flag_validacao_zscore_ticket = fields.Boolean(
        string="Trava de anomalia financeira (3x ticket médio / Z-Score)", default=True,
    )

    # Grupo 2: Utensílios na impressão e correlações de consumo
    boteco_flag_insumo_copos_primeira_cerveja = fields.Boolean(
        string="1ª cerveja: imprimir aviso de [N] copos no bar (e delta de novos clientes)",
        default=True,
    )
    boteco_flag_correlacao_vinho_agua = fields.Boolean(
        string="Vinho: imprimir [N] taças/balde no bar e alertar garçom para oferecer água",
        default=True,
    )
    boteco_flag_insumo_pratos_compartilhados = fields.Boolean(
        string="Pratos compartilhados/lanches: imprimir [N] pratos e cesta de guardanapos",
        default=True,
    )
    boteco_flag_hold_fire_sobremesa_2_tempo = fields.Boolean(
        string="Hold & Fire: reter sobremesa (2º tempo) quando pedida junto com prato principal",
        default=True,
    )

    # Grupo 3: Cozinha central de congelados e proteção bar vs. B2B
    boteco_flag_capacidade_finita_congelados = fields.Boolean(
        string="Limitar plano de produção pela capacidade diária da cozinha", default=True,
    )
    boteco_flag_controle_volume_freezer = fields.Boolean(
        string="Controlar espaço livre nos freezers / câmara fria (litros)", default=True,
    )
    boteco_flag_reserva_estoque_bar_b2b = fields.Boolean(
        string="Proteger reserva mínima de congelados do bar contra vendas B2B", default=True,
    )
    boteco_flag_explosao_insumos_fator_coccao = fields.Boolean(
        string="Fator de correção/cocção na receita e alerta de matéria-prima faltante",
        default=True,
    )

    # Grupo 4: Inteligência de compras
    boteco_flag_leitor_orcamento_pdf_imagem = fields.Boolean(
        string="Leitor de orçamentos em PDF e foto/imagem", default=True,
    )
    boteco_flag_radar_precos_oportunidade = fields.Boolean(
        string="Radar de preços interessantes e economia nos congelados", default=True,
    )

    # Grupo 5: Recursos opcionais (PDV, portaria, KDS, WhatsApp IA, financeiro)
    boteco_flag_pdv_atalhos_f1_f12 = fields.Boolean(
        string="Atalhos F1-F12 no PDV e edição de pagamento pós-venda", default=False,
    )
    boteco_flag_pdv_fichas_avulsas = fields.Boolean(
        string="Fichas avulsas por unidade com código de barras", default=False,
    )
    boteco_flag_pdv_balanca_ean13 = fields.Boolean(
        string="Etiqueta de balança EAN-13 e produtos meio a meio", default=False,
    )
    boteco_flag_portaria_validador_saida = fields.Boolean(
        string="Validador de saída na portaria (comanda paga vs. pendente)", default=False,
    )
    boteco_flag_garcom_tags_rapidas = fields.Boolean(
        string="Tags rápidas de observação para o garçom e DeepLink Smart POS", default=False,
    )
    boteco_flag_kds_totalizador_pacing = fields.Boolean(
        string="KDS avançado: totalizador de grelha, pacing de praças e bump bar", default=False,
    )
    boteco_flag_crm_whatsapp_ia = fields.Boolean(
        string="Régua de clientes sumidos/aniversariantes (e futuro agente de WhatsApp)", default=False,
    )
    boteco_flag_delivery_roteirizacao_motoboy = fields.Boolean(
        string="Delivery: taxa por bairro, entregas e acerto de motoboys", default=False,
    )
    boteco_flag_financeiro_pix_rateio = fields.Boolean(
        string="Rateio da taxa de serviço (10%) entre garçons, cozinha/bar e casa", default=False,
    )

    # Etapas 26 e 33 (PRD de recursos avançados)
    boteco_happy_tolerancia_min = fields.Integer(
        "Tolerância do happy hour (min)", default=5,
        help="Item que entrou no carrinho do QR/tablet com preço de happy hour mantém esse preço se o pedido "
        "chegar até esses minutos depois do fim. 0 = vale o preço da hora do envio.",
    )
    boteco_flag_mensagens = fields.Boolean(
        string="Mensagens e notas internas nas telas (Enviar mensagem, Notas internas, histórico)", default=False,
        help="Desligado, a coluna de conversa do lado dos cadastros some (os registros continuam guardados).",
    )
    boteco_flag_ajuda_rapida = fields.Boolean(
        string="Ajuda rápida pesquisável (botão ?, F1 e Ctrl+K)", default=True,
    )
    boteco_flag_assistente_implantacao = fields.Boolean(
        string="Primeiros passos (assistente de configuração)", default=True,
    )
    # Etapa 36: QR expresso de bebidas (sempre disponível, sem liberação do garçom)
    boteco_flag_qr_bebidas = fields.Boolean(
        string="QR Code expresso de bebidas (2º QR por mesa)", default=True,
    )
    boteco_teto_bebidas_preparadas = fields.Integer(
        string="Teto de bebidas preparadas por envio (0 = automático)", default=0,
        help="Acima disso, as preparadas (drinks, doses, chope) do envio esperam o garçom confirmar. "
        "Automático = o limite de bebidas da mesa: o maior entre 4 e (2 × pessoas + 2).",
    )

    # Etapa 31: fidelidade / cashback (loyalty gratuito do Odoo)
    boteco_flag_fidelidade = fields.Boolean(
        string="Fidelidade / cashback no PDV e no tablet", default=True,
    )
    boteco_flag_fidelidade_com_promocao = fields.Boolean(
        string="Fidelidade também soma pontos em happy hour e ofertas", default=False,
    )

    # Etapa 34: venda a bares escondida por padrão (os dados ficam guardados)
    boteco_flag_vendas_b2b = fields.Boolean(
        string="Venda a bares (B2B): menus, metas e pedidos recorrentes", default=False,
    )

    def write(self, vals):
        if vals.get("boteco_flag_assistente_implantacao"):
            vals = {**vals, "boteco_implantacao_concluida": False}
        for campo in ("boteco_rede_clientes", "boteco_rede_sistema"):
            if vals.get(campo):
                from ..tools.rede import normalizar_redes
                try:
                    vals = {**vals, campo: normalizar_redes(vals[campo])}
                except ValueError:
                    raise UserError(_("\"%s\" não é uma rede. Use o formato 192.168.0.0/24.", vals[campo])) from None
        return super().write(vals)

    def boteco_recurso_ativo(self, nome_flag):
        """True se o recurso ``nome_flag`` está ligado na Central de Recursos.

        Aceita o código curto ("quarentena_pedidos_anomalos") ou o nome do campo
        ("boteco_flag_quarentena_pedidos_anomalos"). Flag desconhecida = desligada.
        """
        company = self[:1] or self.env.company
        campo = nome_flag if nome_flag.startswith("boteco_flag_") else f"boteco_flag_{nome_flag}"
        if campo not in company._fields:
            return False
        return bool(company.sudo()[campo])

    def action_boteco_central_recursos(self):
        # Sem @api.model: é chamado pelo menu (sem registro) e pelo botão do cadastro da empresa (com o registro)
        """Abre a Central de Recursos da empresa atual."""
        return {
            "type": "ir.actions.act_window",
            "name": "Central de Recursos (Liga/Desliga)",
            "res_model": "res.company",
            "res_id": self.env.company.id,
            "view_mode": "form",
            "views": [(self.env.ref("boteco_base.res_company_view_form_central_recursos").id, "form")],
            "target": "current",
        }

    # ------------------------------------------------------------------
    # Dia de operação
    # ------------------------------------------------------------------
    def _boteco_tz(self):
        self.ensure_one()
        tz_name = self.partner_id.tz or self.env.user.tz or "America/Sao_Paulo"
        try:
            return pytz.timezone(tz_name)
        except pytz.UnknownTimeZoneError:
            return pytz.timezone("America/Sao_Paulo")

    def boteco_dia_operacao(self, momento=None):
        """Data do 'dia de operação' de um instante (UTC naive, como o Odoo guarda)."""
        self.ensure_one()
        momento = momento or fields.Datetime.now()
        tz = self._boteco_tz()
        local = pytz.utc.localize(momento).astimezone(tz)
        virada = timedelta(hours=self.boteco_hora_virada or 0.0)
        return (local - virada).date()

    def boteco_intervalo_dia(self, dia):
        """(inicio, fim) em UTC naive do dia de operação ``dia`` (date)."""
        self.ensure_one()
        tz = self._boteco_tz()
        horas = self.boteco_hora_virada or 0.0
        inicio_local = tz.localize(datetime.combine(dia, time.min) + timedelta(hours=horas))
        fim_local = inicio_local + timedelta(days=1)
        return (
            inicio_local.astimezone(pytz.utc).replace(tzinfo=None),
            fim_local.astimezone(pytz.utc).replace(tzinfo=None),
        )

    @api.model
    def boteco_agora_local(self):
        """Agora no fuso da empresa atual (datetime com tz)."""
        return pytz.utc.localize(fields.Datetime.now()).astimezone(self.env.company._boteco_tz())
