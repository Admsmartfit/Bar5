import base64
import logging
from datetime import timedelta

from odoo import SUPERUSER_ID, api, fields, models

from odoo.addons.boteco_base.tools import escpos

_logger = logging.getLogger(__name__)

MAX_TENTATIVAS_IMEDIATAS = 1


class BotecoImpressaoJob(models.Model):
    """Fila de impressão: nenhum ticket se perde se a impressora estiver desligada.

    O envio acontece DEPOIS do commit da transação (o pedido já está salvo). Se falhar,
    o job fica "esperando" e o cron tenta de novo a cada minuto; a tela de produção e a
    página de saúde mostram o aviso.
    """

    _name = "boteco.impressao.job"
    _description = "Fila de impressão"
    _order = "id desc"

    name = fields.Char("Descrição", required=True)
    impressora_id = fields.Many2one("boteco.impressora", required=True, ondelete="cascade", index=True)
    dados = fields.Binary("Conteúdo (ESC/POS)", attachment=False, required=True)
    estado = fields.Selection(
        [("esperando", "Esperando"), ("impresso", "Impresso"), ("cancelado", "Cancelado")],
        default="esperando", required=True, index=True,
    )
    tentativas = fields.Integer(default=0)
    ultimo_erro = fields.Char()
    impresso_em = fields.Datetime()
    kds_pedido_id = fields.Many2one("boteco.kds.pedido", string="Ticket", ondelete="set null", index="btree_not_null")
    company_id = fields.Many2one("res.company", default=lambda s: s.env.company)

    @api.model
    def enfileirar(self, impressora, descricao, dados_bytes, kds_pedido=None):
        job = self.sudo().create({
            "name": descricao,
            "impressora_id": impressora.id,
            "dados": base64.b64encode(dados_bytes),
            "kds_pedido_id": kds_pedido.id if kds_pedido else False,
        })
        dbname = self.env.cr.dbname
        job_id = job.id

        def enviar_depois_do_commit():
            try:
                registry = self.env.registry
                with registry.cursor() as cr:
                    env = api.Environment(cr, SUPERUSER_ID, {})
                    env[self._name].browse(job_id).exists()._enviar()
            except Exception:  # noqa: BLE001 — impressão nunca derruba o pedido
                _logger.exception("Falha ao enviar o job de impressão %s (%s)", job_id, dbname)

        self.env.cr.postcommit.add(enviar_depois_do_commit)
        return job

    def _enviar(self):
        """Envia os jobs pendentes, por impressora, NA ORDEM de chegada.

        Antes de um job novo saem os que estavam esperando na mesma impressora; na primeira
        falha a impressora é marcada com problema e a fila dela para (o cron tenta de novo).
        """
        avisar = self.env["boteco.impressora"]
        for impressora in self.impressora_id:
            ate = max(self.filtered(lambda j: j.impressora_id == impressora).ids)
            fila = self.search([("impressora_id", "=", impressora.id), ("estado", "=", "esperando"), ("id", "<=", ate)],
                               order="id asc")
            for job in fila:
                try:
                    escpos.enviar(base64.b64decode(job.dados), impressora.ip, impressora.porta or 9100)
                except escpos.ImpressoraIndisponivel as erro:
                    job.write({"tentativas": job.tentativas + 1, "ultimo_erro": str(erro)[:250]})
                    if impressora.estado != "erro":
                        avisar |= impressora
                    impressora._marcar(False, str(erro))
                    break
                job.write({"estado": "impresso", "impresso_em": fields.Datetime.now(),
                           "tentativas": job.tentativas + 1, "ultimo_erro": False})
                if impressora.estado != "ok":
                    impressora._marcar(True)
                    self.env["boteco.kds.pedido"]._avisar_impressora(impressora, voltou=True)
        if avisar:
            self.env["boteco.kds.pedido"]._avisar_impressora(avisar)
        return True

    def action_reimprimir(self):
        for job in self:
            self.enfileirar(job.impressora_id, job.name + " (reimpressão)", base64.b64decode(job.dados), job.kds_pedido_id)
        return True

    def action_tentar_de_novo(self):
        self._enviar()
        return True

    @api.model
    def _cron_reenviar(self):
        """Reenvia o que ficou esperando, na ordem em que chegou."""
        pendentes = self.search([("estado", "=", "esperando")], order="id asc", limit=200)
        pendentes._enviar()
        # Limpeza: guarda 15 dias de histórico
        self.search([("estado", "!=", "esperando"), ("create_date", "<", fields.Datetime.now() - timedelta(days=15))]).unlink()
        return True
