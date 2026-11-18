from odoo import _, api, fields, models
from odoo.exceptions import UserError


class RestaurantTable(models.Model):
    _inherit = "restaurant.table"

    boteco_chamou_garcom = fields.Boolean("Chamou o garçom", copy=False)
    boteco_chamou_garcom_em = fields.Datetime(copy=False)
    boteco_pediu_conta = fields.Boolean("Pediu a conta", copy=False)
    boteco_pediu_conta_em = fields.Datetime(copy=False)
    # Etapa 13: quantas pessoas estão na mesa agora (N do motor de conferência e dos utensílios)
    boteco_clientes_atuais = fields.Integer(
        "Clientes na mesa", copy=False,
        help="Quantas pessoas estão na mesa agora. Ao abrir a mesa vem com os lugares cadastrados "
        "(se o recurso estiver ligado na Central de Recursos); o garçom ajusta.",
    )

    @api.model
    def _load_pos_data_fields(self, config_id):
        campos = super()._load_pos_data_fields(config_id)
        return campos + ["boteco_chamou_garcom", "boteco_chamou_garcom_em", "boteco_pediu_conta", "boteco_pediu_conta_em",
                         "boteco_clientes_atuais"]

    def _boteco_dados_mesa(self):
        self.ensure_one()
        return {
            "id": self.id,
            "numero": self.table_number,
            "boteco_chamou_garcom": self.boteco_chamou_garcom,
            "boteco_chamou_garcom_em": fields.Datetime.to_string(self.boteco_chamou_garcom_em) if self.boteco_chamou_garcom_em else False,
            "boteco_pediu_conta": self.boteco_pediu_conta,
            "boteco_pediu_conta_em": fields.Datetime.to_string(self.boteco_pediu_conta_em) if self.boteco_pediu_conta_em else False,
            "boteco_clientes_atuais": self.boteco_clientes_atuais,
        }

    def _boteco_avisar(self, evento=None):
        """Avisa os PDVs (mapa de mesas e celular do garçom) em tempo real."""
        for mesa in self:
            for config in mesa.floor_id.pos_config_ids:
                if config.current_session_id:
                    config._notify("BOTECO_MESA", {**mesa._boteco_dados_mesa(), "evento": evento})

    def boteco_marcar(self, chamou_garcom=None, pediu_conta=None):
        agora = fields.Datetime.now()
        vals = {}
        if chamou_garcom is not None:
            vals.update(boteco_chamou_garcom=chamou_garcom, boteco_chamou_garcom_em=agora if chamou_garcom else False)
        if pediu_conta is not None:
            vals.update(boteco_pediu_conta=pediu_conta, boteco_pediu_conta_em=agora if pediu_conta else False)
        if vals:
            self.sudo().write(vals)
            evento = "pediu_conta" if pediu_conta else "chamou_garcom" if chamou_garcom else "atendido"
            self._boteco_avisar(evento)
        return True

    def _boteco_limpar_chamados(self):
        marcadas = self.filtered(lambda m: m.boteco_chamou_garcom or m.boteco_pediu_conta)
        if marcadas:
            marcadas.sudo().write({
                "boteco_chamou_garcom": False, "boteco_chamou_garcom_em": False,
                "boteco_pediu_conta": False, "boteco_pediu_conta_em": False,
            })
            marcadas._boteco_avisar("liberada")
        # Mesa sem conta aberta: zera a ocupação (e o que depende dela, ex.: copos já levados)
        abertas = self.env["pos.order"].sudo().search([("table_id", "in", self.ids), ("state", "=", "draft")]).table_id
        livres = self - abertas
        if livres:
            livres._boteco_zerar_ocupacao()

    # ------------------------------------------------------------------
    # Ocupação da mesa (Etapa 13)
    # ------------------------------------------------------------------
    def _boteco_zerar_ocupacao(self):
        """Mesa liberada. Ponto de extensão: outros módulos zeram o que for por ocupação."""
        self.filtered("boteco_clientes_atuais").sudo().write({"boteco_clientes_atuais": 0})

    def boteco_iniciar_ocupacao(self):
        """Abertura da mesa: sugere a capacidade cadastrada (seats) como número de clientes."""
        for mesa in self:
            if mesa.boteco_clientes_atuais:
                continue
            company = mesa.floor_id.pos_config_ids[:1].company_id or self.env.company
            if company.boteco_recurso_ativo("ocupacao_padrao_mesa"):
                mesa.sudo().boteco_clientes_atuais = mesa.seats or 2
        return True

    def boteco_definir_clientes(self, quantidade):
        """Garçom/caixa ajusta o número de pessoas na mesa (e nas contas abertas dela)."""
        quantidade = int(quantidade or 0)
        if quantidade < 1:
            raise UserError(_("A mesa precisa ter pelo menos 1 pessoa."))
        for mesa in self:
            mesa.sudo().boteco_clientes_atuais = quantidade
            pedidos = self.env["pos.order"].sudo().search([("table_id", "=", mesa.id), ("state", "=", "draft")])
            pedidos.filtered(lambda p: p.customer_count != quantidade).write({"customer_count": quantidade})
            mesa._boteco_avisar("clientes")
        return True

    def _boteco_mesa_raiz(self):
        self.ensure_one()
        mesa, vistos = self, set()
        while mesa.parent_id and mesa.id not in vistos:
            vistos.add(mesa.id)
            mesa = mesa.parent_id
        return mesa

    def _boteco_grupo(self):
        """Mesa + mesas juntadas a ela (junção nativa do Odoo: parent_id)."""
        self.ensure_one()
        raiz = self._boteco_mesa_raiz()
        grupo = raiz
        filhas = self.search([("parent_id", "=", raiz.id)])
        while filhas - grupo:
            grupo |= filhas
            filhas = self.search([("parent_id", "in", grupo.ids)])
        return grupo

    def _boteco_clientes_da_mesa(self):
        """N de uma mesa isolada: ajustado pelo garçom > contas abertas > lugares (se o recurso estiver ligado)."""
        self.ensure_one()
        if self.boteco_clientes_atuais:
            return self.boteco_clientes_atuais
        pedidos = self.env["pos.order"].sudo().search([("table_id", "=", self.id), ("state", "=", "draft"),
                                                      ("boteco_origem", "in", ("garcom", "caixa"))])
        contagem = max(pedidos.mapped("customer_count") or [0])
        if contagem:
            return contagem
        company = self.floor_id.pos_config_ids[:1].company_id or self.env.company
        if company.boteco_recurso_ativo("ocupacao_padrao_mesa"):
            return self.seats or 2
        return 0

    def boteco_n_clientes(self):
        """N usado pelas regras: soma as mesas juntadas quando a junção está ligada. Nunca menos de 1."""
        self.ensure_one()
        company = self.floor_id.pos_config_ids[:1].company_id or self.env.company
        if company.boteco_recurso_ativo("salao_juncao_mesas"):
            total = sum(m._boteco_clientes_da_mesa() for m in self._boteco_grupo())
        else:
            total = self._boteco_clientes_da_mesa()
        return max(total, 1)

    def action_boteco_agrupar_mesas(self, mesa_destino_id):
        """Junta esta(s) mesa(s) à mesa de destino somando o número de clientes."""
        destino = self.browse(mesa_destino_id).exists()
        if not destino:
            raise UserError(_("Mesa de destino não encontrada."))
        company = destino.floor_id.pos_config_ids[:1].company_id or self.env.company
        if not company.boteco_recurso_ativo("salao_juncao_mesas"):
            raise UserError(_("A junção de mesas está desligada na Central de Recursos."))
        raiz = destino._boteco_mesa_raiz()
        # Cada mesa guarda o seu N; o N do grupo é sempre a soma (ver boteco_n_clientes)
        for mesa in (self | raiz):
            if not mesa.boteco_clientes_atuais:
                mesa.sudo().boteco_clientes_atuais = mesa._boteco_clientes_da_mesa()
        (self - raiz).sudo().write({"parent_id": raiz.id})
        (self | raiz)._boteco_avisar("juntou")
        return raiz.boteco_n_clientes()
