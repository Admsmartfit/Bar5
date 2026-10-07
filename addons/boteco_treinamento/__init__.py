from . import models


def post_init_hook(env):
    """Marca o banco como de treino: nome da empresa, sem e-mail e sem crons de alerta para fora."""
    for empresa in env["res.company"].search([]):
        if not empresa.name.startswith("[TREINO]"):
            empresa.name = "[TREINO] %s" % empresa.name
    env["ir.mail_server"].search([]).write({"active": False})
    env["ir.config_parameter"].sudo().set_param("boteco.treinamento", "1")
