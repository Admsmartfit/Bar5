from . import models
from . import controllers
from . import tools


def post_init_hook(env):
    """Configuração inicial depois de instalar o boteco_base.

    * Fuso de Brasília e português para o usuário admin (se o idioma existir).
    * Aplica os termos de boteco nos menus.
    * Marca a empresa principal como bar (o script de instalação ajusta depois).
    """
    admin = env.ref("base.user_admin", raise_if_not_found=False)
    if admin:
        vals = {"tz": "America/Sao_Paulo"}
        if env["res.lang"]._lang_get("pt_BR"):
            vals["lang"] = "pt_BR"
        admin.write(vals)
    env["boteco.termo"].search([])._aplicar()
    for company in env["res.company"].search([("boteco_tipo_unidade", "=", False)]):
        company.boteco_tipo_unidade = "bar"
