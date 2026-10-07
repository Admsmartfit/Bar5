from odoo import fields
from odoo.tests import tagged

from odoo.addons.boteco_cardapio.tests.common_pos import BotecoPosCase


@tagged("post_install", "-at_install", "boteco")
class TestPainel(BotecoPosCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.ref("boteco_cardapio.happy_hour_padrao").active = False
        cls.config.cash_control = True
        cls.pm_cartao.boteco_taxa_pct = 3.0

    def test_painel_mostra_a_noite_em_tempo_real(self):
        """Critério: o painel mostra os números da noite em tempo real (inclui conta aberta)."""
        antes = self.env["boteco.painel"].dados()["noite"]["faturamento"]
        self._sincronizar(self._pedido([self._linha(self.porcao, 1)], mesa=self.mesa1, pessoas=3))
        dados = self.env["boteco.painel"].dados()
        self.assertAlmostEqual(dados["noite"]["faturamento"] - antes, 42.0)
        self.assertGreaterEqual(dados["noite"]["clientes"], 3)
        self.assertEqual(dados["metas"][0]["meta"], 86)
        self.assertTrue(any(i["nome"] == self.porcao.name for i in dados["mais_vendidos"]))

    def test_relatorio_do_dia_bate_com_os_fechamentos_de_caixa(self):
        """Critério: relatório do dia bate com a soma dos fechamentos de caixa."""
        sessao = self._abrir_sessao(troco=100)
        self._sincronizar(self._pedido([self._linha(self.chope, 5)], mesa=self.mesa1, pagamentos=[(self.pm_dinheiro, 50)]))
        self._sincronizar(self._pedido([self._linha(self.porcao, 1)], mesa=self.mesa2, pagamentos=[(self.pm_pix, 42)]))
        self._sincronizar(self._pedido([self._linha(self.batata, 1)], mesa=self.mesas[2], pagamentos=[(self.pm_cartao, 30)]))
        sessao.with_user(self.caixa).try_cash_in_out("out", 20, "Cofre", {"translatedType": "out", "formattedAmount": "20"})
        sessao.with_user(self.gerente).boteco_registrar_contagem(
            {self.pm_dinheiro.id: 130.0, self.pm_pix.id: 42.0, self.pm_cartao.id: 30.0})
        dia = self.env.company.boteco_dia_operacao(fields.Datetime.now())
        dados = self.env["boteco.fechamento.dia"].calcular(dia)
        self.assertAlmostEqual(dados["vendas"], 122.0)
        self.assertAlmostEqual(dados["total_pagamentos"], 122.0)
        # esperado dos caixas (100 troco + 122 vendas - 20 sangria) menos troco e sangria = vendas do dia
        self.assertAlmostEqual(dados["caixa"]["esperado"], 202.0)
        self.assertAlmostEqual(dados["conferencia_vendas_caixa"], dados["total_pagamentos"])
        self.assertAlmostEqual(dados["sangrias"], 20.0)
        relatorio = self.env["boteco.fechamento.dia"].create({"dia": dia})
        pdf, _t = self.env["ir.actions.report"]._render_qweb_pdf("boteco_painel.report_fechamento_dia", relatorio.ids)
        self.assertTrue(pdf)
        relatorio.action_excel()
        self.assertTrue(relatorio.arquivo)

    def test_dre_separa_as_tres_frentes(self):
        """Critério: DRE do mês separa o lucro das três frentes."""
        self._sincronizar(self._pedido([self._linha(self.porcao, 2)], mesa=self.mesa1, pagamentos=[(self.pm_cartao, 84)]))
        cliente = self.env["res.partner"].create({"name": "Bar do Zé", "boteco_cliente_b2b": True})
        b2b = self.env["account.move"].create({
            "move_type": "out_invoice", "partner_id": cliente.id, "boteco_frente": "b2b",
            "invoice_date": fields.Date.today(),
            "invoice_line_ids": [fields.Command.create({"name": "Bolinho 20 kg", "quantity": 20, "price_unit": 42, "tax_ids": []})],
        })
        b2b.action_post()
        contrato = self.env["boteco.contrato.assessoria"].create({"partner_id": cliente.id})
        contrato.action_ativar()
        conta_luz = self.env["account.move"].create({
            "move_type": "in_invoice", "partner_id": cliente.id, "boteco_frente": "geral",
            "invoice_date": fields.Date.today(),
            "invoice_line_ids": [fields.Command.create({"name": "Energia", "quantity": 1, "price_unit": 500, "tax_ids": []})],
        })
        conta_luz.action_post()
        hoje = fields.Date.today()
        dre = self.env["boteco.dre"].calcular(hoje.replace(day=1), hoje)
        frentes = {f["codigo"]: f for f in dre["frentes"]}
        self.assertAlmostEqual(frentes["bar"]["receita"], 84.0)
        self.assertAlmostEqual(frentes["bar"]["taxas_cartao"], 84.0 * 0.03, places=2)
        self.assertAlmostEqual(frentes["b2b"]["receita"], 840.0)
        self.assertGreaterEqual(frentes["assessoria"]["receita"], 3500.0)
        self.assertAlmostEqual(dre["despesas_gerais"], 500.0)
        soma = sum(f["resultado"] for f in dre["frentes"]) - dre["despesas_gerais"]
        self.assertAlmostEqual(dre["resultado_total"], soma, places=2)
        relatorio = self.env["boteco.dre"].create({})
        pdf, _t = self.env["ir.actions.report"]._render_qweb_pdf("boteco_painel.report_dre", relatorio.ids)
        self.assertTrue(pdf)

    def test_fluxo_de_caixa(self):
        dados = self.env["boteco.painel"].fluxo_caixa()
        self.assertIn("previsto", dados)
        self.assertIn("realizado", dados)
