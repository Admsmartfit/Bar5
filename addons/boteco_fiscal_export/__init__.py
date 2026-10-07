from . import models
from . import wizard


def post_init_hook(env):
    """Contas já pagas antes de instalar o módulo também entram no controle fiscal."""
    pedidos = env["pos.order"].search([("state", "in", ("paid", "done", "invoiced"))])
    pedidos._boteco_registrar_fiscal()
