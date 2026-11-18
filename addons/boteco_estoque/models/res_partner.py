"""Fornecedor com perfil no Instagram: leitura automática das ofertas do dia (Etapa 18)."""

import logging
from datetime import datetime, time, timedelta

import pytz

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

POSTS_POR_PERFIL = 6
# Horários da leitura (fuso da empresa). Poucas leituras por dia = menos risco de bloqueio do Instagram.
HORARIOS_INSTAGRAM = {
    "boteco_estoque.ir_cron_boteco_monitor_instagram": time(8, 0),
    "boteco_estoque.ir_cron_boteco_monitor_instagram_tarde": time(14, 0),
}


def proxima_execucao(hora, fuso, agora_utc):
    """Próximo instante (UTC sem fuso, como o Odoo guarda) em que o relógio local marca ``hora``."""
    agora_local = pytz.utc.localize(agora_utc).astimezone(fuso)
    alvo = fuso.localize(datetime.combine(agora_local.date(), hora))
    if alvo <= agora_local:
        alvo = fuso.localize(datetime.combine(agora_local.date() + timedelta(days=1), hora))
    return alvo.astimezone(pytz.utc).replace(tzinfo=None)


class ResPartner(models.Model):
    _inherit = "res.partner"

    boteco_instagram_handle = fields.Char(
        "Instagram do fornecedor", help="Perfil público com as ofertas (sem o @). Ex.: hortifruti_do_ze")
    boteco_instagram_lido_em = fields.Datetime("Instagram lido em", readonly=True, copy=False)

    @api.onchange("boteco_instagram_handle")
    def _onchange_boteco_instagram_handle(self):
        if self.boteco_instagram_handle:
            self.boteco_instagram_handle = self.boteco_instagram_handle.strip().lstrip("@").split("/")[-1]

    @api.model
    def _boteco_agendar_monitor_instagram(self):
        """Põe os dois crons do Instagram para rodar às 8:00 e às 14:00 (horário da empresa)."""
        fuso = self.env.company._boteco_tz()
        agora = fields.Datetime.now()
        for xmlid, hora in HORARIOS_INSTAGRAM.items():
            cron = self.env.ref(xmlid, raise_if_not_found=False)
            if cron:
                cron.sudo().write({"nextcall": proxima_execucao(hora, fuso, agora),
                                   "interval_number": 1, "interval_type": "days"})
        return True

    @api.model
    def _boteco_ler_posts(self, handle, desde):
        """Legendas recentes de um perfil público: [(texto, link)]. Usa o instaloader, se instalado."""
        try:
            import instaloader
        except ImportError:
            _logger.warning("Monitor de Instagram ligado, mas a biblioteca 'instaloader' não está instalada.")
            return []
        carregador = instaloader.Instaloader(download_pictures=False, download_videos=False, save_metadata=False,
                                             quiet=True)
        perfil = instaloader.Profile.from_username(carregador.context, handle)
        posts = []
        for post in perfil.get_posts():
            if post.date_utc < desde or len(posts) >= POSTS_POR_PERFIL:
                break
            posts.append((post.caption or "", "https://www.instagram.com/p/%s/" % post.shortcode))
        return posts

    @api.model
    def _cron_monitorar_instagram(self):
        """Lê os posts novos dos fornecedores e registra os preços no histórico (radar de preços)."""
        from odoo.addons.boteco_estoque.tools.orcamento import ler_texto

        if not self.env.company.boteco_recurso_ativo("monitor_instagram_fornecedores"):
            return True
        Importar = self.env["boteco.importar.orcamento"]
        agora = fields.Datetime.now()
        for fornecedor in self.search([("boteco_instagram_handle", "!=", False)]):
            desde = fornecedor.boteco_instagram_lido_em or (agora - timedelta(days=3))
            try:
                posts = self._boteco_ler_posts(fornecedor.boteco_instagram_handle, desde)
            except Exception:  # noqa: BLE001 — um perfil com problema não para os outros
                _logger.warning("Não consegui ler o Instagram de %s", fornecedor.boteco_instagram_handle, exc_info=True)
                continue
            for legenda, link in posts:
                for item in ler_texto(legenda):
                    produto = Importar._achar_insumo(item["descricao"], fornecedor)
                    if produto:
                        self.env["boteco.historico.preco"].registrar(
                            produto, item["preco"], fornecedor=fornecedor, origem="instagram", referencia=link,
                            descricao=item["descricao"])
            fornecedor.boteco_instagram_lido_em = agora
        return True
