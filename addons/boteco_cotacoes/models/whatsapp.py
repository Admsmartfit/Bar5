"""Conexão do WhatsApp do bar por QR Code (como o WhatsApp Web), pelo Evolution API em contêiner próprio."""

import logging
from datetime import timedelta

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .cotacao import PARAM_TOKEN_WHATSAPP

_logger = logging.getLogger(__name__)

PARAM_URL = "boteco.evolution_url"
PARAM_CHAVE = "boteco.evolution_apikey"
PARAM_INSTANCIA = "boteco.evolution_instancia"
PARAM_ODOO_INTERNO = "boteco.evolution_webhook_base"
PARAM_ESTADO = "boteco.whatsapp_estado"
PARAM_DESDE = "boteco.whatsapp_estado_desde"
PARAM_NUMERO = "boteco.whatsapp_numero"
TEMPO = 15  # segundos: o Evolution fora do ar não pode travar a tela


class BotecoWhatsapp(models.AbstractModel):
    _name = "boteco.whatsapp"
    _description = "Conexão do WhatsApp do bar"

    # ------------------------------------------------------------------ configuração
    @api.model
    def _param(self, nome, padrao=""):
        return self.env["ir.config_parameter"].sudo().get_param(nome, padrao)

    @api.model
    def _configurado(self):
        return bool(self._param(PARAM_CHAVE))

    @api.model
    def _instancia(self):
        return self._param(PARAM_INSTANCIA, "bar5")

    @api.model
    def _chamar(self, metodo, caminho, **kwargs):
        if not self._configurado():
            raise UserError(_("Falta ligar o serviço do WhatsApp no servidor (chave do Evolution API). "
                              "Veja docs/whatsapp.md."))
        url = self._param(PARAM_URL, "http://evolution:8080").rstrip("/") + caminho
        try:
            resposta = requests.request(metodo, url, headers={"apikey": self._param(PARAM_CHAVE)}, timeout=TEMPO,
                                        **kwargs)
        except requests.RequestException as erro:
            raise UserError(_("O serviço do WhatsApp não respondeu (%s).", erro.__class__.__name__)) from erro
        try:
            return resposta.status_code, resposta.json()
        except ValueError:
            return resposta.status_code, {}

    @api.model
    def _webhook_url(self):
        token = self.env["boteco.cotacoes"]._token(PARAM_TOKEN_WHATSAPP)
        base = self._param(PARAM_ODOO_INTERNO, "http://odoo:8069").rstrip("/")
        return "%s/boteco/compras/whatsapp/%s" % (base, token)

    # ------------------------------------------------------------------ tela
    @api.model
    def estado(self):
        """Situação para a tela 'WhatsApp (conectar)': conectado, número, desde quando e o QR quando houver."""
        self._checar_dono()
        dados = {"configurado": self._configurado(), "ligado": self.env.company.boteco_recurso_ativo("cotacoes_whatsapp"),
                 "estado": self._param(PARAM_ESTADO, "close"), "numero": self._param(PARAM_NUMERO),
                 "desde": self._param(PARAM_DESDE), "qr": False}
        if dados["configurado"]:
            try:
                dados.update(self._atualizar_estado())
            except UserError as erro:
                dados.update(estado="erro", erro=str(erro.args[0]))
        return dados

    @api.model
    def conectar(self):
        """Cria a sessão (se faltar), liga o webhook e devolve o QR Code para o dono ler no celular."""
        self._checar_dono()
        instancia = self._instancia()
        webhook = {"enabled": True, "url": self._webhook_url(), "byEvents": False, "base64": True,
                   "events": ["MESSAGES_UPSERT", "CONNECTION_UPDATE"]}
        self._chamar("POST", "/instance/create", json={
            "instanceName": instancia, "qrcode": True, "integration": "WHATSAPP-BAILEYS", "webhook": webhook,
            "groupsIgnore": True, "readMessages": False, "alwaysOnline": False})
        self._chamar("POST", "/webhook/set/%s" % instancia, json={"webhook": webhook})
        status, dados = self._chamar("GET", "/instance/connect/%s" % instancia)
        qr = dados.get("base64") or (dados.get("qrcode") or {}).get("base64")
        if status >= 400 and not qr:
            raise UserError(_("Não consegui gerar o QR Code agora. Tente de novo em instantes."))
        self.env["boteco.cotacao.log"].registrar("conexao", "ok", detalhe=_("QR Code gerado"))
        return {"qr": qr if not qr or qr.startswith("data:") else "data:image/png;base64," + qr,
                "estado": "connecting"}

    @api.model
    def desconectar(self):
        self._checar_dono()
        self._chamar("DELETE", "/instance/logout/%s" % self._instancia())
        self._gravar_estado("close", "")
        self.env["boteco.cotacao.log"].registrar("conexao", "ok", detalhe=_("Desconectado pelo dono"))
        return True

    @api.model
    def _checar_dono(self):
        if not (self.env.user.has_group("boteco_base.group_dono") or self.env.su):
            raise UserError(_("Só o dono conecta o WhatsApp do bar."))

    # ------------------------------------------------------------------ situação
    @api.model
    def _atualizar_estado(self):
        instancia = self._instancia()
        _status, dados = self._chamar("GET", "/instance/connectionState/%s" % instancia)
        estado = ((dados.get("instance") or {}).get("state")) or dados.get("state") or "close"
        numero = self._param(PARAM_NUMERO)
        if estado == "open" and not numero:
            _s, lista = self._chamar("GET", "/instance/fetchInstances", params={"instanceName": instancia})
            item = (lista[0] if isinstance(lista, list) and lista else lista) or {}
            dono = item.get("ownerJid") or (item.get("instance") or {}).get("owner") or ""
            numero = dono.split("@")[0]
        self._gravar_estado(estado, numero if estado == "open" else "")
        return {"estado": estado, "numero": self._param(PARAM_NUMERO), "desde": self._param(PARAM_DESDE)}

    @api.model
    def _gravar_estado(self, estado, numero):
        Param = self.env["ir.config_parameter"].sudo()
        if Param.get_param(PARAM_ESTADO) != estado:
            Param.set_param(PARAM_ESTADO, estado)
            Param.set_param(PARAM_DESDE, fields.Datetime.to_string(fields.Datetime.now()))
        if Param.get_param(PARAM_NUMERO, "") != (numero or ""):
            Param.set_param(PARAM_NUMERO, numero or "")

    @api.model
    def _cron_verificar(self):
        """A cada 5 minutos: conexão caiu? (aviso no Painel do dono e na Saúde do sistema)."""
        if not self._configurado() or not self.env.company.boteco_recurso_ativo("cotacoes_whatsapp"):
            return True
        try:
            self._atualizar_estado()
        except UserError:
            self._gravar_estado("erro", "")
        return True

    @api.model
    def _alerta(self):
        """Texto do aviso quando o WhatsApp está configurado e ligado, mas sem conexão."""
        if not self._configurado() or not self.env.company.boteco_recurso_ativo("cotacoes_whatsapp"):
            return False
        estado = self._param(PARAM_ESTADO, "close")
        if estado == "open":
            return False
        if estado == "erro":
            return _("O serviço do WhatsApp não está respondendo: as cotações dos fornecedores não estão entrando.")
        return _("WhatsApp do bar desconectado: as cotações dos fornecedores não estão entrando. "
                 "Conecte de novo em Configuração › Sistema › WhatsApp (conectar).")

    # ------------------------------------------------------------------ mensagens recebidas
    @api.model
    def receber(self, evento, ip=None):
        """Webhook do Evolution API. Só mensagem de fornecedor cadastrado vira fila; o resto some sem gravar."""
        Log = self.env["boteco.cotacao.log"]
        tipo = (evento.get("event") or "").lower().replace("_", ".")
        dados = evento.get("data") or {}
        if tipo == "connection.update":
            estado = dados.get("state") or dados.get("status")
            if estado:
                self._gravar_estado(estado, (dados.get("wuid") or "").split("@")[0] if estado == "open" else "")
            return "conexao"
        if tipo != "messages.upsert":
            return "ignorado"
        if not self.env.company.boteco_recurso_ativo("cotacoes_whatsapp"):
            return "desligado"
        mensagens = dados if isinstance(dados, list) else [dados]
        resultado = "ignorado"
        for msg in mensagens:
            chave = msg.get("key") or {}
            remetente = chave.get("remoteJid") or ""
            if chave.get("fromMe") or not remetente.endswith("@s.whatsapp.net"):
                continue  # mensagem do próprio bar, grupo, status ou lista: descarta sem gravar
            fornecedor = self.env["res.partner"]._boteco_fornecedor_do_numero(remetente.split("@")[0])
            conteudo = msg.get("message") or {}
            texto = (conteudo.get("conversation") or (conteudo.get("extendedTextMessage") or {}).get("text")
                     or (conteudo.get("imageMessage") or {}).get("caption")
                     or (conteudo.get("documentMessage") or {}).get("caption") or "")
            if not fornecedor:
                # Não guarda número nem conteúdo: só conta que alguém mandou algo com cara de preço
                from odoo.addons.boteco_estoque.tools.orcamento import ler_texto
                if texto and ler_texto(texto):
                    Log.registrar("whatsapp", "desconhecido", ip=ip,
                                  detalhe=_("Número não cadastrado mandou mensagem com preços"))
                continue
            vals = {"partner_id": fornecedor.id, "canal": "whatsapp", "referencia": _("WhatsApp %s",
                                                                                         fields.Date.today().strftime("%d/%m"))}
            midia = conteudo.get("base64") or msg.get("base64")
            documento = conteudo.get("documentMessage") or {}
            imagem = conteudo.get("imageMessage") or {}
            if midia and (documento.get("mimetype") or "").endswith("pdf"):
                vals.update(tipo="pdf", arquivo=midia, mimetype="application/pdf")
            elif midia and imagem:
                vals.update(tipo="imagem", arquivo=midia, mimetype=imagem.get("mimetype") or "image/jpeg")
            elif texto:
                vals.update(tipo="texto", texto=texto[:20000])
            else:
                continue
            self.env["boteco.cotacao.fila"]._boteco_enfileirar(vals)
            Log.registrar("whatsapp", "ok", partner_id=fornecedor.id, ip=ip, detalhe=vals["tipo"])
            resultado = "ok"
        return resultado


class BotecoPainel(models.AbstractModel):
    _inherit = "boteco.painel"

    @api.model
    def _alertas_extras(self, company):
        alertas = super()._alertas_extras(company)
        aviso = self.env["boteco.whatsapp"]._alerta()
        if aviso:
            alertas.append(aviso)
        revisar = self.env["boteco.cotacao.revisar"].sudo().search_count([("estado", "=", "revisar")])
        if revisar:
            alertas.append(_("%s item(ns) de cotação esperando você ligar ao insumo (Compras › Cotações para revisar).",
                             revisar))
        desconhecidos = self.env["boteco.cotacao.log"].sudo().search_count([
            ("resultado", "=", "desconhecido"), ("create_date", ">=", fields.Datetime.now() - timedelta(days=1))])
        if desconhecidos:
            alertas.append(_("%s número(s) não cadastrado(s) mandaram preços no WhatsApp hoje. Cadastre o fornecedor "
                             "(com o celular) se quiser que entre no radar.", desconhecidos))
        return alertas


class BotecoSaude(models.AbstractModel):
    _inherit = "boteco.saude"

    @api.model
    def _verificacoes_extras(self):
        itens = super()._verificacoes_extras()
        Whats = self.env["boteco.whatsapp"]
        if Whats._configurado() and self.env.company.boteco_recurso_ativo("cotacoes_whatsapp"):
            aviso = Whats._alerta()
            numero = Whats._param(PARAM_NUMERO)
            itens.append(self._item(_("WhatsApp do bar (cotações)"), not aviso,
                                    aviso or _("Conectado: %s", numero or "?"),
                                    acao="/odoo/action-boteco_cotacoes.action_boteco_whatsapp_conectar" if aviso else None))
        return itens
