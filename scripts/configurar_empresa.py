# pyright: reportUndefinedVariable=false
# Configuração inicial do Boteco. Roda dentro do "odoo shell" (variável `env` disponível):
#
#   docker compose run --rm -T odoo odoo shell -c /etc/odoo/odoo.conf -d boteco < scripts/configurar_empresa.py
#
# Pode rodar mais de uma vez: cada passo confere se já foi feito.
# Lê do ambiente: EMPRESA_NOME, EMPRESA_CNPJ, EMPRESA_CIDADE, EMPRESA_MODO (uma|duas),
# COZINHA_NOME, COZINHA_CNPJ, ODOO_ADMIN_USER_PASSWORD, BOTECO_HOSTNAME, REDE_CLIENTES, REDE_SISTEMA.
import os

from odoo import Command


def log(msg):
    print("[boteco] " + msg, flush=True)


def ref(xmlid):
    return env.ref(xmlid, raise_if_not_found=False)


brasil = ref("base.br")
real = ref("base.BRL")
if real and not real.active:
    real.active = True

nome = os.environ.get("EMPRESA_NOME") or "Boteco Raiz"
cnpj = os.environ.get("EMPRESA_CNPJ") or False
cidade = os.environ.get("EMPRESA_CIDADE") or False
modo = (os.environ.get("EMPRESA_MODO") or "uma").strip().lower()
rede_clientes = os.environ.get("REDE_CLIENTES") or False
rede_sistema = os.environ.get("REDE_SISTEMA") or False
host = os.environ.get("BOTECO_HOSTNAME") or "boteco.local"

# ---------------------------------------------------------------- empresa do bar
bar = env.ref("base.main_company")
vals = {
    "name": nome,
    "boteco_tipo_unidade": "bar" if modo == "duas" else "bar_e_cozinha",
    "boteco_rede_clientes": rede_clientes,
    "boteco_rede_sistema": rede_sistema,
    "boteco_hora_virada": 6.0,
}
if brasil:
    vals["country_id"] = brasil.id
if real:
    vals["currency_id"] = real.id
if cnpj:
    vals["vat"] = cnpj
if cidade:
    vals["city"] = cidade
bar.write(vals)
bar.partner_id.write({"tz": "America/Sao_Paulo", "lang": "pt_BR"})
log("Empresa: %s" % bar.name)

# Plano de contas brasileiro (l10n_br)
if not bar.chart_template and "l10n_br" in env["ir.module.module"].search([("state", "=", "installed")]).mapped("name"):
    env["account.chart.template"].try_loading("br", company=bar, install_demo=False)
    log("Plano de contas brasileiro carregado")

# ---------------------------------------------------------------- armazéns
Armazem = env["stock.warehouse"]
arm_bar = Armazem.search([("company_id", "=", bar.id)], order="id", limit=1)
if arm_bar:
    arm_bar.write({"name": "Bar", "boteco_tipo_unidade": "bar"})
    if arm_bar.code != "BAR":
        try:
            arm_bar.code = "BAR"
        except Exception:  # noqa: BLE001 — código já usado em lançamentos
            pass

if modo == "duas":
    cozinha = env["res.company"].search([("boteco_tipo_unidade", "=", "cozinha_central")], limit=1)
    if not cozinha:
        cozinha = env["res.company"].create({
            "name": os.environ.get("COZINHA_NOME") or "Cozinha Central",
            "vat": os.environ.get("COZINHA_CNPJ") or False,
            "country_id": brasil.id if brasil else False,
            "currency_id": real.id if real else False,
            "boteco_tipo_unidade": "cozinha_central",
            "parent_id": False,
        })
        if "l10n_br" in env["ir.module.module"].search([("state", "=", "installed")]).mapped("name"):
            env["account.chart.template"].try_loading("br", company=cozinha, install_demo=False)
        log("Empresa da cozinha central criada: %s" % cozinha.name)
    arm_cc = Armazem.search([("company_id", "=", cozinha.id)], limit=1)
    if arm_cc:
        arm_cc.write({"name": "Cozinha Central", "boteco_tipo_unidade": "cozinha_central"})
else:
    arm_cc = Armazem.search([("company_id", "=", bar.id), ("boteco_tipo_unidade", "=", "cozinha_central")], limit=1)
    if not arm_cc:
        arm_cc = Armazem.create({"name": "Cozinha Central", "code": "CC", "company_id": bar.id,
                                 "boteco_tipo_unidade": "cozinha_central"})
        log("Armazém da cozinha central criado")

# Lotes e validade ligados (cozinha central e FEFO)
grupos = env["res.config.settings"].create({
    "group_stock_production_lot": True,
    "group_stock_multi_locations": True,
    "module_product_expiry": True,
})
grupos.execute()
log("Lotes, validade e locais múltiplos ligados")

# ---------------------------------------------------------------- formas de pagamento e PDV
Diario = env["account.journal"]


def diario(nome_d, tipo, codigo):
    d = Diario.search([("code", "=", codigo), ("company_id", "=", bar.id)], limit=1)
    return d or Diario.create({"name": nome_d, "type": tipo, "code": codigo, "company_id": bar.id})


caixa = diario("Caixa do bar", "cash", "CXBAR")
banco = diario("Recebimentos (PIX e cartões)", "bank", "RECB")
Metodo = env["pos.payment.method"]


def metodo(nome_m, journal):
    m = Metodo.search([("name", "=", nome_m), ("company_id", "=", bar.id)], limit=1)
    return m or Metodo.create({"name": nome_m, "journal_id": journal.id, "company_id": bar.id})


metodos = metodo("Dinheiro", caixa) | metodo("PIX", banco) | metodo("Cartão de débito", banco) | metodo("Cartão de crédito", banco)

admin = env.ref("base.user_admin")
config = env["pos.config"].search([("company_id", "=", bar.id), ("module_pos_restaurant", "=", True)], limit=1)
if not config:
    config = env["pos.config"].search([("company_id", "=", bar.id)], limit=1)
cfg_vals = {
    "name": "Bar",
    "module_pos_restaurant": True,
    "payment_method_ids": [Command.set(metodos.ids)],
    "cash_control": True,
    "iface_splitbill": True,
    "iface_printbill": True,
    "self_ordering_mode": "mobile",
    "self_ordering_service_mode": "table",
    "self_ordering_pay_after": "meal",
    "self_ordering_default_user_id": admin.id,
    "picking_type_id": arm_bar.pos_type_id.id if arm_bar and arm_bar.pos_type_id else False,
}
cfg_vals = {k: v for k, v in cfg_vals.items() if k in env["pos.config"]._fields and v is not False}
if config and config.current_session_id:
    log("PDV com caixa aberto: configuração do PDV mantida (feche o caixa para reaplicar)")
elif config:
    config.write(cfg_vals)
else:
    config = env["pos.config"].create(cfg_vals)
log("PDV de restaurante: %s" % config.name)

# Plantas de mesas: Salão (mesas 1 a 14) e Área aberta (15 a 20) – cerca de 80 lugares
Planta = env["restaurant.floor"]
Mesa = env["restaurant.table"]
for nome_planta, numeros, inicio_x in (("Salão", range(1, 15), 40), ("Área aberta", range(15, 21), 40)):
    planta = Planta.search([("name", "=", nome_planta)], limit=1)
    if not planta:
        planta = Planta.create({"name": nome_planta, "pos_config_ids": [Command.link(config.id)]})
    elif config not in planta.pos_config_ids:
        planta.pos_config_ids = [Command.link(config.id)]
    for i, numero in enumerate(numeros):
        if not Mesa.search_count([("floor_id", "=", planta.id), ("table_number", "=", numero)]):
            Mesa.create({
                "floor_id": planta.id, "table_number": numero, "seats": 4, "shape": "square",
                "position_h": inicio_x + (i % 5) * 140, "position_v": 40 + (i // 5) * 140,
                "width": 110, "height": 110,
            })
# A planta padrão criada pelo Odoo (nome da empresa, 1 mesa) atrapalha: remove se não tiver pedidos
for planta in Planta.search([("name", "not in", ["Salão", "Área aberta"]), ("pos_config_ids", "in", config.ids)]):
    if not env["pos.order"].search_count([("table_id", "in", planta.table_ids.ids)]):
        try:
            with env.cr.savepoint():
                planta.table_ids.write({"active": False})
                planta.active = False
            log("Planta padrão arquivada: %s" % planta.name)
        except Exception as erro:  # noqa: BLE001 — com caixa aberto o Odoo pode recusar
            log("Planta padrão mantida (%s)" % erro)
log("Mesas criadas/conferidas")

# ---------------------------------------------------------------- dono, URL e idioma
senha = os.environ.get("ODOO_ADMIN_USER_PASSWORD")
admin_vals = {"boteco_perfil_id": env.ref("boteco_base.perfil_dono").id, "tz": "America/Sao_Paulo",
              "lang": "pt_BR", "company_ids": [Command.set(env["res.company"].search([]).ids)]}
if senha:
    admin_vals["password"] = senha
admin.write(admin_vals)

ICP = env["ir.config_parameter"].sudo()
ICP.set_param("web.base.url", "https://%s" % host)
ICP.set_param("web.base.url.freeze", "True")
log("Endereço do sistema: https://%s" % host)

env.cr.commit()
log("Configuração concluída.")
