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

env.cr.commit()
log("Pronto. PINs: " + ", ".join("%s=%s" % (l, p) for _n, l, _perfil, p in EQUIPE))
