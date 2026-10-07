from odoo.tests import TransactionCase, new_test_user


class BotecoCase(TransactionCase):
    """Base dos testes: cria uma pessoa de cada perfil com PIN."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.perfil_garcom = cls.env.ref("boteco_base.perfil_garcom")
        cls.perfil_caixa = cls.env.ref("boteco_base.perfil_caixa")
        cls.perfil_gerente = cls.env.ref("boteco_base.perfil_gerente")
        cls.perfil_dono = cls.env.ref("boteco_base.perfil_dono")
        cls.garcom = cls._pessoa("Garçom Teste", "garcom_teste", cls.perfil_garcom, "2580")
        cls.caixa = cls._pessoa("Caixa Teste", "caixa_teste", cls.perfil_caixa, "3691")
        cls.gerente = cls._pessoa("Gerente Teste", "gerente_teste", cls.perfil_gerente, "7314")

    @classmethod
    def _pessoa(cls, nome, login, perfil, pin):
        user = new_test_user(cls.env, login=login, name=nome, groups="base.group_user")
        user.write({"boteco_perfil_id": perfil.id, "boteco_pin": pin})
        return user
