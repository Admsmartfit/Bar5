import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class BotecoImpressora(models.Model):
    _inherit = "boteco.impressora"

    def enviar_bytes(self, dados, levantar=True):
        """Treino: não imprime de verdade (papel e tickets falsos na chapa confundiriam a equipe)."""
        _logger.info("[TREINO] impressão simulada em %s (%s bytes)", self.name, len(dados or b""))
        self._marcar(True)
        return True


class BotecoImpressaoJob(models.Model):
    _inherit = "boteco.impressao.job"

    def _enviar(self):
        for job in self.filtered(lambda j: j.estado == "esperando"):
            job.write({"estado": "impresso", "impresso_em": fields.Datetime.now(), "ultimo_erro": "[TREINO] simulado"})
        return True
