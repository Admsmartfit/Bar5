# Fase 2 da instalação (odoo shell): antes de instalar a contabilidade, a empresa precisa
# ser brasileira em reais. Assim o Odoo carrega o plano de contas do Brasil (l10n_br)
# em vez do genérico.
brasil = env.ref("base.br")
real = env.ref("base.BRL")
real.active = True
empresa = env.ref("base.main_company")
empresa.write({"country_id": brasil.id, "currency_id": real.id})
empresa.partner_id.tz = "America/Sao_Paulo"
env.cr.commit()
print("[boteco] Empresa marcada como brasileira (BRL)", flush=True)
