import json

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.http import request

ACOES = [
    ("cancelar_item", "Cancelamento de item"),
    ("desconto", "Desconto"),
    ("cortesia", "Cortesia"),
    ("consumo_funcionario", "Consumo de funcionário"),
    ("remover_taxa", "Taxa de serviço retirada"),
    ("remover_couvert", "Couvert retirado"),
    ("sangria", "Sangria"),
    ("reforco", "Reforço"),
    ("abrir_caixa", "Abertura de caixa"),
    ("fechar_caixa", "Fechamento de caixa"),
    ("ajuste_estoque", "Ajuste de estoque"),
    ("perda", "Perda / quebra"),
    ("alteracao_preco", "Alteração de preço"),
    ("autorizacao", "Autorização do gerente"),
    ("autorizacao_negada", "Autorização negada"),
    ("perfil_alterado", "Perfil alterado"),
    ("permissao", "Permissão alterada"),
    ("pin_alterado", "PIN alterado"),
    ("pin_desbloqueado", "PIN desbloqueado"),
    ("aprovacao_qr", "Celular aprovado no QR"),
    ("quiosque", "Saída do modo quiosque"),
    ("fiscal", "Controle fiscal"),
    ("lgpd", "Dados pessoais (LGPD)"),
    ("atualizacao", "Atualização do sistema"),
    ("outro", "Outro"),
]


class BotecoAuditoria(models.Model):
    """Registro de auditoria: quem fez o quê, quando, e quem autorizou.

    Imutável: o ORM recusa alterar/apagar e um gatilho no PostgreSQL bloqueia
    UPDATE e DELETE mesmo por SQL direto.
    """

    _name = "boteco.auditoria"
    _description = "Registro de auditoria"
    _order = "data desc, id desc"
    _rec_name = "descricao"

    data = fields.Datetime(default=fields.Datetime.now, required=True, readonly=True, index=True)
    acao = fields.Selection(ACOES, required=True, readonly=True, index=True)
    descricao = fields.Char("Descrição", readonly=True)
    usuario_id = fields.Many2one(
        "res.users", string="Quem fez", readonly=True, index=True, ondelete="restrict",
        default=lambda s: s.env.user,
    )
    autorizado_por_id = fields.Many2one("res.users", string="Quem autorizou", readonly=True, ondelete="restrict")
    modelo = fields.Char("Modelo", readonly=True)
    res_id = fields.Integer("ID do registro", readonly=True)
    referencia = fields.Char("Referência", readonly=True, index=True)
    valor_antigo = fields.Char("Antes", readonly=True)
    valor_novo = fields.Char("Depois", readonly=True)
    valor = fields.Float("Valor (R$)", readonly=True, digits="Product Price")
    motivo = fields.Text("Motivo", readonly=True)
    detalhe = fields.Text("Detalhes (JSON)", readonly=True)
    ip = fields.Char("IP", readonly=True)
    company_id = fields.Many2one(
        "res.company", readonly=True, index=True, default=lambda s: s.env.company, ondelete="restrict"
    )

    def init(self):
        # Gatilho de imutabilidade. Para migrações de esquema, um script pode usar
        #   SET LOCAL boteco.auditoria_migracao = '1';
        self.env.cr.execute(
            """
            CREATE OR REPLACE FUNCTION boteco_auditoria_imutavel() RETURNS trigger AS $$
            BEGIN
                IF current_setting('boteco.auditoria_migracao', true) = '1' THEN
                    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
                    RETURN NEW;
                END IF;
                RAISE EXCEPTION 'Registro de auditoria nao pode ser alterado nem apagado';
            END;
            $$ LANGUAGE plpgsql;
            DROP TRIGGER IF EXISTS boteco_auditoria_imutavel ON boteco_auditoria;
            CREATE TRIGGER boteco_auditoria_imutavel
                BEFORE UPDATE OR DELETE ON boteco_auditoria
                FOR EACH ROW EXECUTE FUNCTION boteco_auditoria_imutavel();
            """
        )

    def write(self, vals):
        raise UserError(_("Registro de auditoria não pode ser alterado."))

    def unlink(self):
        raise UserError(_("Registro de auditoria não pode ser apagado."))

    @api.model
    def registrar(
        self,
        acao,
        registro=None,
        descricao=None,
        valor_antigo=None,
        valor_novo=None,
        valor=0.0,
        motivo=None,
        autorizado_por=None,
        referencia=None,
        detalhe=None,
    ):
        """Grava uma linha de auditoria. Sempre funciona (usa sudo), nunca levanta por permissão."""
        ip = None
        try:
            if request:
                ip = request.httprequest.remote_addr
        except RuntimeError:
            ip = None
        vals = {
            "acao": acao,
            "descricao": descricao or dict(ACOES).get(acao, acao),
            "usuario_id": self.env.user.id,
            "autorizado_por_id": autorizado_por.id if autorizado_por else False,
            "valor_antigo": "" if valor_antigo is None else str(valor_antigo),
            "valor_novo": "" if valor_novo is None else str(valor_novo),
            "valor": valor or 0.0,
            "motivo": motivo or False,
            "referencia": referencia or False,
            "detalhe": json.dumps(detalhe, ensure_ascii=False, default=str) if detalhe else False,
            "ip": ip,
            "company_id": self.env.company.id,
        }
        if registro is not None and registro:
            registro = registro[:1]
            vals.update({"modelo": registro._name, "res_id": registro.id})
            if "company_id" in registro._fields and registro.company_id:
                vals["company_id"] = registro.company_id.id
        return self.sudo().create(vals)

    def action_abrir_registro(self):
        self.ensure_one()
        if not self.modelo or not self.res_id or self.modelo not in self.env:
            raise UserError(_("Este registro não aponta para nenhum documento."))
        return {
            "type": "ir.actions.act_window",
            "res_model": self.modelo,
            "res_id": self.res_id,
            "view_mode": "form",
            "target": "current",
        }
