import json
import os
import shutil
from datetime import datetime, timezone

from odoo import _, api, fields, models
from odoo.tools import config

from ..tools import escpos

LIMITE_DISCO_PCT = 85
LIMITE_BACKUP_HORAS = 2


class BotecoSaude(models.AbstractModel):
    """Verificações da página de saúde do sistema (/boteco/saude)."""

    _name = "boteco.saude"
    _description = "Saúde do sistema"

    @api.model
    def _item(self, nome, ok, detalhe, alerta=False, acao=None):
        return {
            "nome": nome,
            "estado": "ok" if ok and not alerta else ("alerta" if ok else "erro"),
            "detalhe": detalhe,
            "acao": acao,
        }

    @api.model
    def _verificar_banco(self):
        cr = self.env.cr
        try:
            cr.execute("SELECT version(), pg_database_size(current_database())")
            versao, tamanho = cr.fetchone()
            cr.execute("SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()")
            conexoes = cr.fetchone()[0]
        except Exception as erro:  # noqa: BLE001 — a página de saúde não pode quebrar
            return [self._item(_("Banco de dados"), False, str(erro))]
        return [
            self._item(
                _("Banco de dados"),
                True,
                _("%(versao)s · %(tamanho)s MB · %(conexoes)s conexões",
                  versao=versao.split(",")[0], tamanho=round(tamanho / 1024 / 1024, 1), conexoes=conexoes),
            )
        ]

    @api.model
    def _verificar_impressoras(self):
        itens = []
        for impressora in self.env["boteco.impressora"].sudo().search([]):
            ok = escpos.testar_conexao(impressora.ip, impressora.porta or 9100, timeout=1.0)
            impressora._marcar(ok, None if ok else _("Sem resposta"))
            itens.append(
                self._item(
                    _("Impressora: %s", impressora.name),
                    ok,
                    "%s:%s" % (impressora.ip, impressora.porta) if ok else impressora._mensagem_erro(),
                )
            )
        if not itens:
            itens.append(self._item(_("Impressoras"), True, _("Nenhuma impressora cadastrada."), alerta=True))
        return itens

    @api.model
    def _uso_disco(self, caminho, nome):
        try:
            uso = shutil.disk_usage(caminho)
        except OSError:
            return None
        pct = round(uso.used * 100 / uso.total, 1) if uso.total else 0
        livre_gb = round(uso.free / 1024 ** 3, 1)
        return self._item(
            nome,
            True,
            _("%(pct)s%% usado · %(livre)s GB livres", pct=pct, livre=livre_gb),
            alerta=pct >= LIMITE_DISCO_PCT,
        )

    @api.model
    def _verificar_disco(self):
        itens = []
        dados = self._uso_disco(config["data_dir"], _("Disco do sistema"))
        if dados:
            itens.append(dados)
        pasta_backup = os.environ.get("BOTECO_BACKUP_DIR", "/backups")
        if os.path.isdir(pasta_backup):
            dados = self._uso_disco(pasta_backup, _("Disco de backup"))
            if dados:
                itens.append(dados)
        return itens

    @api.model
    def _verificar_backup(self):
        pasta = os.environ.get("BOTECO_BACKUP_DIR", "/backups")
        status_arquivo = os.path.join(pasta, "ultimo_backup.json")
        if not os.path.isfile(status_arquivo):
            return [self._item(_("Último backup"), False, _("Nenhum backup encontrado em %s.", pasta))]
        try:
            with open(status_arquivo, encoding="utf-8") as arq:
                info = json.load(arq)
            quando = datetime.fromisoformat(info["data"])
            if quando.tzinfo is None:
                quando = quando.replace(tzinfo=timezone.utc)
        except (OSError, ValueError, KeyError) as erro:
            return [self._item(_("Último backup"), False, _("Arquivo de status ilegível: %s", erro))]
        horas = (datetime.now(timezone.utc) - quando).total_seconds() / 3600
        ok = info.get("status") == "ok"
        detalhe = _(
            "%(quando)s (há %(horas)s h) · %(tamanho)s MB",
            quando=quando.astimezone().strftime("%d/%m %H:%M"),
            horas=round(horas, 1),
            tamanho=round(info.get("tamanho_bytes", 0) / 1024 / 1024, 1),
        )
        if not ok:
            detalhe += " · " + (info.get("erro") or _("falhou"))
        return [self._item(_("Último backup"), ok, detalhe, alerta=horas > LIMITE_BACKUP_HORAS)]

    @api.model
    def _verificacoes_extras(self):
        """Ponto de extensão para os outros módulos (fila de impressão, KDS...)."""
        return []

    @api.model
    def verificar(self):
        itens = []
        itens += self._verificar_banco()
        itens += self._verificar_impressoras()
        itens += self._verificar_disco()
        itens += self._verificar_backup()
        itens += self._verificacoes_extras()
        geral = "ok"
        if any(i["estado"] == "erro" for i in itens):
            geral = "erro"
        elif any(i["estado"] == "alerta" for i in itens):
            geral = "alerta"
        return {
            "geral": geral,
            "itens": itens,
            "verificado_em": fields.Datetime.to_string(fields.Datetime.now()),
        }
