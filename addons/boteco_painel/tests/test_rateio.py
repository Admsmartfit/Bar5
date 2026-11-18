from odoo.exceptions import UserError, ValidationError
from odoo.tests import new_test_user, tagged

from odoo.addons.boteco_cardapio.tests.common_pos import BotecoPosCase


@tagged("post_install", "-at_install", "boteco")
class TestRateioTaxa(BotecoPosCase):
    """Etapa 23: rateio da taxa de serviço entre garçons, cozinha/bar e casa."""

    def _conta_paga(self, user, valor_consumo):
        taxa_prod = self.config.boteco_produto_taxa_id
        linhas = [self._linha(self.porcao, 1, preco=valor_consumo), self._linha(taxa_prod, 1, preco=valor_consumo / 10)]
        total = valor_consumo * 1.1
        dados = self._pedido(linhas, pagamentos=[(self.pm_dinheiro, total)], user_id=user.id)
        return self._sincronizar(dados)

    def test_rateio_proporcional(self):
        self.env.company.boteco_flag_financeiro_pix_rateio = True
        if not self.config.boteco_produto_taxa_id:
            self.skipTest("PDV sem produto de taxa de serviço")
        outro = new_test_user(self.env, login="garcom2_rateio", name="Bruno Garçom", groups="base.group_user")
        self._conta_paga(self.env.user, 300.0)  # gera R$ 30 de taxa
        self._conta_paga(outro, 100.0)  # gera R$ 10
        rateio = self.env["boteco.rateio.taxa"].create({})
        rateio.action_calcular()
        self.assertAlmostEqual(rateio.total_taxa, 40.0)
        garcons = rateio.linha_ids.filtered(lambda l: l.papel == "garcom")
        self.assertAlmostEqual(sum(garcons.mapped("valor")), 28.0)  # 70%
        self.assertAlmostEqual(garcons.filtered(lambda l: l.user_id == outro).valor, 7.0)
        self.assertAlmostEqual(rateio.linha_ids.filtered(lambda l: l.papel == "producao").valor, 8.0)
        self.assertAlmostEqual(rateio.linha_ids.filtered(lambda l: l.papel == "casa").valor, 4.0)

    def test_rateio_desligado(self):
        self.env.company.boteco_flag_financeiro_pix_rateio = False
        with self.assertRaises(UserError):
            self.env["boteco.rateio.taxa"].create({}).action_calcular()

    def test_percentuais_somam_100(self):
        with self.assertRaises(ValidationError):
            self.env.company.boteco_rateio_casa_pct = 50.0
