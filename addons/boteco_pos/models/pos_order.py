import json
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .utils import documento_valido, ler_snapshot, so_digitos

_logger = logging.getLogger(__name__)

# Campos que só o servidor controla: o que vier da tela é descartado (a tela devolve tudo o que
# carregou, inclusive valores antigos; aceitar isso deixaria a tela burlar o controle).
CAMPOS_SERVIDOR_PEDIDO = {
    "boteco_snapshot_envio", "boteco_primeiro_envio", "boteco_ultimo_envio", "boteco_autorizado_por_id",
    "boteco_taxa_servico", "boteco_couvert", "boteco_total_cortesia", "boteco_total_desconto",
    "boteco_dia_operacao", "boteco_funcionario_id", "boteco_cpf_valido",
}
CAMPOS_SERVIDOR_LINHA = {
    "boteco_qtd_enviada", "boteco_autorizado_por_id", "boteco_oferta_id", "boteco_preco_origem", "boteco_preco_fixado",
}

ORIGENS = [("garcom", "Garçom"), ("caixa", "Caixa"), ("tablet", "Tablet da mesa"), ("qr", "QR Code")]


class PosOrder(models.Model):
    _inherit = "pos.order"

    boteco_origem = fields.Selection(ORIGENS, string="Origem", default="garcom", index=True)
    boteco_tipo_conta = fields.Selection(
        [("normal", "Normal"), ("funcionario", "Consumo de funcionário")],
        string="Tipo de conta", default="normal", required=True, index=True,
    )
    # O PDV envia só o id (o modelo de usuários não é carregado inteiro na tela)
    boteco_funcionario_ref = fields.Integer("Funcionário (id)", copy=False)
    boteco_funcionario_id = fields.Many2one("res.users", string="Funcionário (consumo)",
                                            compute="_compute_boteco_funcionario", store=True)
    boteco_funcionario_modo = fields.Selection([("custo", "A preço de custo"), ("zero", "Sem cobrar")],
                                               string="Cobrança do funcionário")
    boteco_autorizacao_ref = fields.Integer("Autorização (conta)", copy=False)
    boteco_autorizado_por_id = fields.Many2one("res.users", string="Autorizado por", copy=False, readonly=True)
    boteco_cpf_nota = fields.Char("CPF/CNPJ na nota", copy=False)
    boteco_cpf_valido = fields.Boolean("Documento válido", compute="_compute_boteco_cpf_valido", store=True)
    boteco_taxa_removida = fields.Boolean("Taxa de serviço retirada", copy=False)
    boteco_couvert_removido = fields.Boolean("Couvert retirado", copy=False)
    boteco_taxa_servico = fields.Monetary("Taxa de serviço", compute="_compute_boteco_totais", store=True)
    boteco_couvert = fields.Monetary("Couvert", compute="_compute_boteco_totais", store=True)
    boteco_total_cortesia = fields.Monetary("Cortesias", compute="_compute_boteco_totais", store=True)
    boteco_total_desconto = fields.Monetary("Descontos", compute="_compute_boteco_totais", store=True)
    boteco_snapshot_envio = fields.Text(
        "Já enviado à produção", copy=False,
        help="Cópia do que já foi mandado pra cozinha/bar e processado pelo servidor.",
    )
    boteco_primeiro_envio = fields.Datetime("Primeiro pedido", copy=False, readonly=True)
    boteco_ultimo_envio = fields.Datetime("Último pedido", copy=False, readonly=True)
    boteco_dia_operacao = fields.Date("Dia de operação", compute="_compute_boteco_dia_operacao", store=True, index=True)

    # ------------------------------------------------------------------
    @api.depends("boteco_cpf_nota")
    def _compute_boteco_cpf_valido(self):
        for pedido in self:
            pedido.boteco_cpf_valido = bool(pedido.boteco_cpf_nota) and documento_valido(pedido.boteco_cpf_nota)

    @api.depends("boteco_funcionario_ref")
    def _compute_boteco_funcionario(self):
        for pedido in self:
            pedido.boteco_funcionario_id = self.env["res.users"].browse(pedido.boteco_funcionario_ref).exists()                 if pedido.boteco_funcionario_ref else False

    @api.depends("date_order", "company_id")
    def _compute_boteco_dia_operacao(self):
        for pedido in self:
            pedido.boteco_dia_operacao = (
                pedido.company_id.boteco_dia_operacao(pedido.date_order) if pedido.date_order else False
            )

    @api.depends("lines.price_subtotal_incl", "lines.product_id", "lines.discount", "lines.boteco_cortesia",
                 "lines.qty", "lines.price_unit")
    def _compute_boteco_totais(self):
        for pedido in self:
            config = pedido.config_id
            taxa_prod = config.boteco_produto_taxa_id
            couvert_prod = config.boteco_produto_couvert_id
            taxa = couvert = cortesia = desconto = 0.0
            for linha in pedido.lines:
                if taxa_prod and linha.product_id == taxa_prod:
                    taxa += linha.price_subtotal_incl
                elif couvert_prod and linha.product_id == couvert_prod:
                    couvert += linha.price_subtotal_incl
                cheio = linha.price_unit * linha.qty
                abatido = cheio * (linha.discount or 0.0) / 100.0
                if linha.boteco_cortesia:
                    cortesia += abatido
                elif linha.discount:
                    desconto += abatido
            pedido.boteco_taxa_servico = taxa
            pedido.boteco_couvert = couvert
            pedido.boteco_total_cortesia = cortesia
            pedido.boteco_total_desconto = desconto

    # ------------------------------------------------------------------
    # Normalização e regras na gravação (vale para qualquer origem: PDV, QR, servidor)
    # ------------------------------------------------------------------
    @api.model
    def _boteco_normalizar(self, vals):
        if "boteco_tipo_conta" in vals and not vals["boteco_tipo_conta"]:
            vals["boteco_tipo_conta"] = "normal"
        if "boteco_origem" in vals and not vals["boteco_origem"]:
            vals["boteco_origem"] = "garcom"
        if vals.get("boteco_cpf_nota"):
            vals["boteco_cpf_nota"] = so_digitos(vals["boteco_cpf_nota"])
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [self._boteco_normalizar(dict(v)) for v in vals_list]
        pedidos = super().create(vals_list)
        pedidos._boteco_conferir_conta_especial()
        return pedidos

    def write(self, vals):
        vals = self._boteco_normalizar(dict(vals))
        if vals.get("state") == "cancel":
            # Cancelar a conta inteira com itens já enviados também exige PIN do gerente
            for pedido in self.filtered(lambda p: p.state == "draft"):
                enviadas = pedido.lines.filtered(lambda l: l.boteco_qtd_enviada > 0)
                enviadas._boteco_conferir_cancelamento({l.id: 0.0 for l in enviadas})
        res = super().write(vals)
        if "boteco_tipo_conta" in vals or "boteco_autorizacao_ref" in vals:
            self._boteco_conferir_conta_especial()
        return res

    def _boteco_conferir_conta_especial(self):
        """Consumo de funcionário precisa de permissão ou PIN do gerente (uma vez por conta)."""
        for pedido in self.filtered(lambda p: p.boteco_tipo_conta == "funcionario" and not p.boteco_autorizado_por_id):
            sessao = pedido.session_id
            autorizado_por = sessao._boteco_exigir(
                "pode_consumo_funcionario", pedido.boteco_autorizacao_ref or None, referencia=None
            )
            super(PosOrder, pedido).write({"boteco_autorizado_por_id": autorizado_por.id})
            self.env["boteco.auditoria"].registrar(
                "consumo_funcionario", registro=pedido,
                descricao=_("Consumo de %(func)s (%(modo)s)", func=pedido.boteco_funcionario_id.name or "?",
                            modo=dict(self._fields["boteco_funcionario_modo"].selection).get(pedido.boteco_funcionario_modo, "")),
                valor=sum(pedido.lines.mapped(lambda l: l.product_id.standard_price * l.qty)),
                autorizado_por=autorizado_por, referencia=pedido.uuid,
            )

    # ------------------------------------------------------------------
    # Envio para produção: o servidor processa o que mudou desde o último envio
    # ------------------------------------------------------------------
    @api.model
    def _boteco_limpar_dados_da_tela(self, pedido):
        for campo in CAMPOS_SERVIDOR_PEDIDO:
            pedido.pop(campo, None)
        for comando in pedido.get("lines") or []:
            if isinstance(comando, (list, tuple)) and len(comando) >= 3 and isinstance(comando[2], dict):
                for campo in CAMPOS_SERVIDOR_LINHA:
                    comando[2].pop(campo, None)
        return pedido

    @api.model
    def sync_from_ui(self, orders):
        for pedido in orders:
            self._boteco_limpar_dados_da_tela(pedido)
        resultado = super().sync_from_ui(orders)
        ids = [o["id"] for o in resultado.get("pos.order", [])]
        self.browse(ids)._boteco_processar_envio()
        return resultado

    def _boteco_processar_envio(self):
        """Compara o que o PDV marcou como enviado com o que o servidor já processou.

        Gera a lista de mudanças (novos itens e cancelamentos) e chama ``_boteco_ao_enviar``,
        que o boteco_kds usa para imprimir e montar a tela de produção.
        """
        agora = fields.Datetime.now()
        for pedido in self:
            atual = ler_snapshot(pedido.last_order_preparation_change)
            anterior = ler_snapshot(pedido.boteco_snapshot_envio)
            if atual == anterior:
                continue
            mudancas = []
            for uuid in set(atual) | set(anterior):
                novo = atual.get(uuid, {}).get("qtd", 0.0)
                velho = anterior.get(uuid, {}).get("qtd", 0.0)
                if novo == velho:
                    continue
                info = atual.get(uuid) or anterior.get(uuid)
                linha = pedido.lines.filtered(lambda l, u=uuid: l.uuid == u)[:1]
                mudancas.append({
                    "uuid": uuid,
                    "linha": linha,
                    "produto_id": info.get("produto") or linha.product_id.id,
                    "nome": info.get("nome") or linha.full_product_name,
                    "nota": info.get("nota") or "",
                    "atributos": info.get("atributos") or [],
                    "quantidade": novo - velho,
                })
            vals = {"boteco_snapshot_envio": pedido.last_order_preparation_change}
            if any(m["quantidade"] > 0 for m in mudancas):
                vals["boteco_ultimo_envio"] = agora
                if not pedido.boteco_primeiro_envio:
                    vals["boteco_primeiro_envio"] = agora
            super(PosOrder, pedido).write(vals)
            for linha in pedido.lines:
                qtd = atual.get(linha.uuid, {}).get("qtd", 0.0)
                if linha.boteco_qtd_enviada != qtd:
                    linha.with_context(boteco_sistema=True).write({"boteco_qtd_enviada": qtd})
            if mudancas:
                pedido._boteco_ao_enviar(mudancas)

    def _boteco_ao_enviar(self, mudancas):
        """Ponto de extensão (boteco_kds): imprime tickets e alimenta a tela de produção."""
        return True

    def boteco_marcar_enviado(self):
        """Marca tudo como enviado à produção a partir do servidor (usado pelo autoatendimento)."""
        for pedido in self:
            snapshot = json.loads(pedido.last_order_preparation_change or "{}") or {}
            snapshot.setdefault("lines", {})
            for linha in pedido.lines.filtered(lambda l: not l.skip_change and l.qty > 0):
                chave = "%s - %s" % (linha.uuid, linha.note or "")
                snapshot["lines"][chave] = {
                    "uuid": linha.uuid,
                    "product_id": linha.product_id.id,
                    "name": linha.full_product_name or linha.product_id.display_name,
                    "note": linha.note or "",
                    "quantity": linha.qty,
                    "attribute_value_ids": [{"id": a.id, "name": a.name} for a in linha.attribute_value_ids],
                }
            snapshot["metadata"] = {"serverDate": fields.Datetime.to_string(fields.Datetime.now())}
            super(PosOrder, pedido).write({"last_order_preparation_change": json.dumps(snapshot)})
        self._boteco_processar_envio()
        return True

    # ------------------------------------------------------------------
    def _process_saved_order(self, draft):
        res = super()._process_saved_order(draft)
        # Conta paga: a mesa volta a ficar livre (sem "pediu a conta"/"chamou garçom")
        mesas = self.filtered(lambda p: p.state in ("paid", "done", "invoiced")).table_id
        if mesas:
            mesas._boteco_limpar_chamados()
        return res
