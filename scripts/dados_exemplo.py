# pyright: reportUndefinedVariable=false
# Dados de exemplo do Boteco (odoo shell). Para testes, treinamento e demonstração.
#
#   docker compose run --rm -T odoo odoo shell -c /etc/odoo/odoo.conf -d boteco --no-http < scripts/dados_exemplo.py
#
# Idempotente: procura antes de criar. NÃO rode no banco de produção depois da inauguração.
from odoo import Command


def log(msg):
    print("[exemplo] " + msg, flush=True)


def ref(xmlid):
    return env.ref(xmlid, raise_if_not_found=False)


setor_bar = ref("boteco_base.setor_bar")
setor_chapa = ref("boteco_base.setor_chapa")

# ---------------------------------------------------------------- equipe com PIN
EQUIPE = [
    ("Ana Garçonete", "ana", "garcom", "2580"),
    ("Bruno Garçom", "bruno", "garcom", "1470"),
    ("Carla Caixa", "carla", "caixa", "3691"),
    ("Diego Chapeiro", "diego", "chapeiro", "4826"),
    ("Elisa Gerente", "elisa", "gerente", "7314"),
    ("Fábio Cozinheiro", "fabio", "cozinheiro", "5937"),
    ("Gabi Comercial", "gabi", "comercial", "6048"),
]
config = env["pos.config"].search([("module_pos_restaurant", "=", True)], limit=1)
for nome, login, perfil, pin in EQUIPE:
    user = env["res.users"].search([("login", "=", login)], limit=1)
    perfil_rec = ref("boteco_base.perfil_%s" % perfil)
    if not user:
        user = env["res.users"].create({"name": nome, "login": login, "boteco_perfil_id": perfil_rec.id,
                                        "tz": "America/Sao_Paulo", "lang": "pt_BR",
                                        "boteco_pdv_config_id": config.id if config else False})
    if not user.boteco_tem_pin:
        try:
            user.boteco_pin = pin
        except Exception as erro:  # noqa: BLE001
            log("PIN de %s não definido: %s" % (nome, erro))
log("Equipe: %s" % ", ".join("%s (%s)" % (n, p) for n, _l, _perfil, p in EQUIPE))

# ---------------------------------------------------------------- categorias do tablet
Cat = env["pos.category"]


def categoria(nome, seq):
    c = Cat.search([("name", "=", nome)], limit=1)
    return c or Cat.create({"name": nome, "sequence": seq})


cervejas = categoria("Cervejas", 1)
drinks = categoria("Drinks", 2)
sem_alcool = categoria("Sem álcool", 3)
porcoes = categoria("Porções", 4)

# Categorias de produto com padrões fiscais
CatProd = env["product.category"]


def cat_prod(nome, ncm, cfop, cst, setor, maior18=False):
    c = CatProd.search([("name", "=", nome)], limit=1)
    vals = {"name": nome, "boteco_ncm_padrao": ncm, "boteco_cfop_padrao": cfop, "boteco_cst_csosn_padrao": cst,
            "boteco_setor_padrao_id": setor.id if setor else False, "boteco_maior_18_padrao": maior18}
    if c:
        c.write(vals)
        return c
    return CatProd.create(vals)


cp_cerveja = cat_prod("Cervejas e chopes", "2203.00.00", "5405", "500", setor_bar, True)
cp_destilado = cat_prod("Drinks e destilados", "2208.40.00", "5405", "500", setor_bar, True)
cp_bebida = cat_prod("Bebidas sem álcool", "2202.10.00", "5405", "500", setor_bar)
cp_porcao = cat_prod("Porções (produção própria)", "2106.90.90", "5101", "102", setor_chapa)

# ---------------------------------------------------------------- cardápio
CARDAPIO = [
    # nome, categoria pdv, cat produto, preço, happy, custo, tempo, destaque
    ("Chope Pilsen 300 ml", cervejas, cp_cerveja, 9.90, 6.90, 3.20, 2, True),
    ("Chope Pilsen 500 ml", cervejas, cp_cerveja, 14.90, 10.90, 5.10, 2, False),
    ("Long neck", cervejas, cp_cerveja, 12.00, 9.00, 4.80, 1, False),
    ("Cerveja 600 ml", cervejas, cp_cerveja, 16.00, 0, 7.50, 1, False),
    ("Caipirinha de limão", drinks, cp_destilado, 19.00, 14.00, 4.00, 4, True),
    ("Gin tônica", drinks, cp_destilado, 26.00, 0, 7.00, 4, False),
    ("Refrigerante lata", sem_alcool, cp_bebida, 7.00, 0, 2.60, 1, False),
    ("Água sem gás", sem_alcool, cp_bebida, 5.00, 0, 1.20, 1, False),
    ("Suco de laranja", sem_alcool, cp_bebida, 10.00, 0, 2.50, 3, False),
    ("Bolinho de bacalhau (12 un)", porcoes, cp_porcao, 42.00, 0, 14.00, 15, True),
    ("Batata frita", porcoes, cp_porcao, 30.00, 0, 7.50, 12, False),
    ("Torresmo", porcoes, cp_porcao, 34.00, 0, 9.00, 12, False),
    ("Calabresa acebolada", porcoes, cp_porcao, 36.00, 0, 11.00, 12, False),
    ("Pastel de carne (6 un)", porcoes, cp_porcao, 28.00, 0, 8.00, 10, False),
    ("Vinho branco (garrafa)", drinks, cp_destilado, 89.00, 0, 35.00, 2, False),
    ("Água com gás", sem_alcool, cp_bebida, 5.50, 0, 1.40, 1, False),
    ("Tábua de frios (serve 3)", porcoes, cp_porcao, 79.00, 0, 26.00, 10, False),
    ("Picanha na chapa (serve 2)", porcoes, cp_porcao, 119.00, 0, 48.00, 20, False),
    ("Prato executivo", porcoes, cp_porcao, 32.00, 0, 11.00, 15, False),
    ("Hambúrguer artesanal", porcoes, cp_porcao, 36.00, 0, 12.00, 15, False),
    ("Petit gâteau com sorvete", porcoes, cp_porcao, 24.00, 0, 7.00, 8, False),
]
Produto = env["product.template"]
for nome, cat_pdv, cat_p, preco, happy, custo, tempo, destaque in CARDAPIO:
    p = Produto.search([("name", "=", nome)], limit=1)
    vals = {
        "name": nome, "list_price": preco, "boteco_preco_happy": happy, "standard_price": custo,
        "categ_id": cat_p.id, "pos_categ_ids": [Command.set([cat_pdv.id])], "available_in_pos": True,
        "sale_ok": True, "type": "consu", "boteco_tempo_preparo": tempo, "boteco_destaque": destaque,
        "taxes_id": [Command.clear()],
    }
    if p:
        p.write(vals)
    else:
        Produto.create(vals)
log("Cardápio: %s itens" % len(CARDAPIO))

# Adicional "Ponto" na batata e "Molho extra +R$ 3"
Atributo = env["product.attribute"]
molho = Atributo.search([("name", "=", "Molho extra")], limit=1) or Atributo.create({
    "name": "Molho extra", "display_type": "radio", "create_variant": "no_variant",
    "value_ids": [Command.create({"name": "Sem molho"}), Command.create({"name": "Cheddar", "default_extra_price": 3.0}),
                  Command.create({"name": "Barbecue", "default_extra_price": 3.0})],
})
batata = Produto.search([("name", "=", "Batata frita")], limit=1)
if batata and not batata.attribute_line_ids:
    env["product.template.attribute.line"].create({
        "product_tmpl_id": batata.id, "attribute_id": molho.id, "value_ids": [Command.set(molho.value_ids.ids)],
    })
log("Adicionais configurados")

# ---------------------------------------------------------------- Central de Recursos (Etapa 11)
# Como ficou decidido na implantação das Etapas 11 a 23 (o dono muda na tela a qualquer momento)
company = env.company
company.write({
    "boteco_flag_ocupacao_padrao_mesa": True,
    "boteco_flag_salao_juncao_mesas": False,
    "boteco_flag_tablet_neutro_anti_burst": True,
    "boteco_flag_tablet_chamada_qualificada": False,
    "boteco_flag_quarentena_pedidos_anomalos": True,
    "boteco_flag_validacao_zscore_ticket": True,
    "boteco_flag_insumo_copos_primeira_cerveja": True,
    "boteco_flag_correlacao_vinho_agua": True,
    "boteco_flag_insumo_pratos_compartilhados": True,
    "boteco_flag_hold_fire_sobremesa_2_tempo": True,
    "boteco_flag_capacidade_finita_congelados": True,
    "boteco_flag_controle_volume_freezer": True,
    "boteco_flag_reserva_estoque_bar_b2b": True,
    "boteco_flag_explosao_insumos_fator_coccao": True,
    "boteco_flag_leitor_orcamento_pdf_imagem": True,
    "boteco_flag_monitor_instagram_fornecedores": False,
    "boteco_flag_radar_precos_oportunidade": True,
})
log("Central de Recursos configurada")

# ---------------------------------------------------------------- taxonomia de consumo (Etapa 12)
TAXONOMIA = {
    # nome: (tipo de consumo, serve pessoas, máx. por rodada, utensílios)
    "Chope Pilsen 300 ml": ("bebida_giro", 1, 0, "copo_cerveja"),
    "Chope Pilsen 500 ml": ("bebida_giro", 1, 0, "copo_cerveja"),
    "Long neck": ("bebida_giro", 1, 0, False),
    "Cerveja 600 ml": ("bebida_giro", 1, 0, "copo_cerveja"),
    "Caipirinha de limão": ("bebida_giro", 1, 0, False),
    "Gin tônica": ("bebida_giro", 1, 0, False),
    "Refrigerante lata": ("bebida_giro", 1, 0, False),
    "Água sem gás": ("agua", 1, 0, False),
    "Água com gás": ("agua", 1, 0, False),
    "Vinho branco (garrafa)": ("garrafa", 4, 0, "taca_vinho_gelo"),
    "Bolinho de bacalhau (12 un)": ("prato_compartilhado", 3, 0, False),
    "Batata frita": ("prato_compartilhado", 2, 0, False),
    "Torresmo": ("prato_compartilhado", 2, 0, False),
    "Calabresa acebolada": ("prato_compartilhado", 2, 0, False),
    "Pastel de carne (6 un)": ("prato_compartilhado", 2, 0, False),
    "Tábua de frios (serve 3)": ("prato_compartilhado", 3, 0, "pratos_compartilhados"),
    "Picanha na chapa (serve 2)": ("prato_compartilhado", 2, 0, "pratos_compartilhados"),
    "Prato executivo": ("prato_individual", 1, 0, False),
    "Hambúrguer artesanal": ("prato_individual", 1, 0, "guardanapo_reforcado"),
    "Petit gâteau com sorvete": ("sobremesa", 1, 3, False),
}
for nome, (tipo, serve, maximo, utensilio) in TAXONOMIA.items():
    p = Produto.search([("name", "=", nome)], limit=1)
    if p:
        p.write({"boteco_tipo_consumo": tipo, "boteco_serve_pessoas": serve, "boteco_max_por_rodada_sku": maximo,
                 "boteco_regra_utensilio": utensilio})
log("Taxonomia de consumo: %s itens" % len(TAXONOMIA))

# ---------------------------------------------------------------- cozinha central de congelados (Etapa 17)
Armazem = env["stock.warehouse"]
cozinha = Armazem.search([("boteco_tipo_unidade", "=", "cozinha_central"), ("company_id", "=", company.id)], limit=1)
if not cozinha and not Armazem.search([("code", "=", "CC")], limit=1):
    cozinha = Armazem.create({"name": "Cozinha Central", "code": "CC", "boteco_tipo_unidade": "cozinha_central"})
if cozinha:
    cozinha.write({"boteco_capacidade_prod_diaria_kg": 60.0, "boteco_capacidade_freezer_litros": 400.0})
    kg = ref("uom.product_uom_kgm")
    PP = env["product.product"]

    def insumo(nome, custo):
        p = PP.search([("name", "=", nome)], limit=1)
        return p or PP.create({"name": nome, "is_storable": True, "purchase_ok": True, "sale_ok": False,
                               "uom_id": kg.id, "uom_po_id": kg.id, "standard_price": custo})

    bacalhau = insumo("Bacalhau dessalgado", 80.0)
    batata_in = insumo("Batata in natura", 5.0)
    massa = PP.search([("name", "=", "Massa de bolinho de bacalhau (congelada)")], limit=1)
    if not massa:
        massa = PP.create({"name": "Massa de bolinho de bacalhau (congelada)", "boteco_produzido_cozinha": True,
                           "uom_id": kg.id, "uom_po_id": kg.id, "sale_ok": True, "list_price": 68.0,
                           "boteco_conservacao": "congelado", "expiration_time": 90})
    massa.write({"boteco_lote_max_diario": 30.0, "boteco_volume_freezer_litros": 1.2,
                 "boteco_estoque_min_bar": 8.0, "boteco_dias_cobertura": 3})
    if not env["mrp.bom"].search([("product_tmpl_id", "=", massa.product_tmpl_id.id)], limit=1):
        env["mrp.bom"].create({
            "product_tmpl_id": massa.product_tmpl_id.id, "product_qty": 10.0, "product_uom_id": kg.id,
            "type": "normal", "boteco_fator_coccao": 0.95,
            "bom_line_ids": [
                Command.create({"product_id": bacalhau.id, "product_qty": 4.0, "boteco_qtd_liquida": 3.6,
                                "boteco_fator_correcao": 1.11}),
                Command.create({"product_id": batata_in.id, "product_qty": 7.0, "boteco_qtd_liquida": 6.0,
                                "boteco_fator_correcao": 1.17}),
            ],
        })
    log("Cozinha central: capacidade 60 kg/dia, freezer 400 L, reserva do bar 8 kg de massa de bolinho")

    # Etapa 34: o mesmo congelado vendido de dois jeitos
    #  - "para levar" (congelado): sem setor -> a venda só baixa o estoque
    #  - porção frita: setor Chapa + ficha técnica (kit) -> baixa o congelado e manda ticket para a chapa
    massa.write({"available_in_pos": True, "sale_ok": True, "boteco_setor_id": False})
    porcao = Produto.search([("name", "=", "Bolinho de bacalhau (12 un)")], limit=1)
    if porcao and not env["mrp.bom"].search([("product_tmpl_id", "=", porcao.id), ("type", "=", "phantom")], limit=1):
        env["mrp.bom"].create({
            "product_tmpl_id": porcao.id, "type": "phantom", "product_qty": 1,
            "bom_line_ids": [Command.create({"product_id": massa.id, "product_qty": 0.36})],
        })
    log("Bolinho: 'Massa congelada' para levar (só estoque) e 'Bolinho (12 un)' frito (kit + chapa)")

    # ------------------------------------------------------------ radar de preços com uma oferta ativa (Etapa 18)
    import datetime as _dt

    Parceiro = env["res.partner"]
    peixaria = Parceiro.search([("name", "=", "Peixaria do Porto")], limit=1) or Parceiro.create(
        {"name": "Peixaria do Porto", "is_company": True, "supplier_rank": 1, "boteco_instagram_handle": "peixariadoporto"})
    Historico = env["boteco.historico.preco"]
    if not Historico.search_count([("product_id", "=", bacalhau.id)]):
        hoje = _dt.date.today()
        for dias, preco in ((55, 82.0), (35, 79.5), (15, 81.0)):
            Historico.registrar(bacalhau, preco, fornecedor=peixaria, origem="nfe", data=hoje - _dt.timedelta(days=dias),
                                referencia="NF exemplo")
        Historico.registrar(bacalhau, 68.9, fornecedor=peixaria, origem="orcamento_texto",
                            referencia="Lista do WhatsApp", descricao="Bacalhau dessalgado kg 68,90")
    log("Radar de preços: bacalhau 15% abaixo da média (aparece no Painel do dono)")

env.cr.commit()
log("Pronto. PINs: " + ", ".join("%s=%s" % (l, p) for _n, l, _perfil, p in EQUIPE))
