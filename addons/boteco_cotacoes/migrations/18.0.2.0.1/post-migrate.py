"""19/11/2026: o WhatsApp e a fila de cotações saíram do Odoo; apaga as tabelas que ficaram órfãs."""


def migrate(cr, version):
    cr.execute("DROP TABLE IF EXISTS boteco_cotacao_fila CASCADE")
    cr.execute("DROP TABLE IF EXISTS boteco_whatsapp CASCADE")
