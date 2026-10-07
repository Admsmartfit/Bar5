from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.boteco_cardapio.tests.common_pos import BotecoPosCase


@tagged("post_install", "-at_install", "boteco")
class TestCaixa(BotecoPosCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.ref("boteco_cardapio.happy_hour_padrao").active = False
        cls.config.cash_control = True

    def test_sangria_exige_motivo_e_permissao(self):
        sessao = self._abrir_sessao(troco=200)
        extras = {"translatedType": "out", "formattedAmount": "R$ 50,00"}
        with self.assertRaisesRegex(UserError, "motivo"):
            sessao.with_user(self.caixa).try_cash_in_out("out", 50, "  ", extras)
        with self.assertRaisesRegex(UserError, "PIN do gerente"):
            sessao.with_user(self.garcom).try_cash_in_out("out", 50, "Cofre", extras)
        sessao.with_user(self.caixa).try_cash_in_out("out", 50, "Recolhimento ao cofre", extras)
        registro = self.env["boteco.auditoria"].search([("acao", "=", "sangria"), ("res_id", "=", sessao.id)])
        self.assertEqual(registro.valor, 50)
        self.assertEqual(registro.motivo, "Recolhimento ao cofre")

    def test_fechamento_cego_mostra_diferenca_por_forma(self):
        """Critério de aceite: fechamento mostra a diferença entre contado e esperado por forma de pagamento."""
        sessao = self._abrir_sessao(troco=100)
        self._sincronizar(self._pedido([self._linha(self.chope, 5)], mesa=self.mesa1, pagamentos=[(self.pm_dinheiro, 50)]))
        self._sincronizar(self._pedido([self._linha(self.porcao, 1)], mesa=self.mesa2, pagamentos=[(self.pm_pix, 42)]))
        self._sincronizar(self._pedido([self._linha(self.batata, 1)], mesa=self.mesas[2], pagamentos=[(self.pm_cartao, 30)]))
        resultado = sessao.with_user(self.gerente).boteco_registrar_contagem({
            self.pm_dinheiro.id: 145.0,  # esperado 150 (100 troco + 50)
            self.pm_pix.id: 42.0,
            self.pm_cartao.id: 30.0,
        })
        por_forma = {l["nome"]: l for l in resultado["linhas"]}
        self.assertAlmostEqual(por_forma["Dinheiro"]["esperado"], 150.0)
        self.assertAlmostEqual(por_forma["Dinheiro"]["diferenca"], -5.0)
        self.assertAlmostEqual(por_forma["PIX"]["diferenca"], 0.0)
        self.assertAlmostEqual(por_forma["Cartão"]["diferenca"], 0.0)
        self.assertAlmostEqual(resultado["diferenca"], -5.0)
        fechamento = self.env["boteco.fechamento.caixa"].browse(resultado["fechamento_id"])
        self.assertEqual(fechamento.autorizado_por_id, self.gerente)
        pdf, _tipo = self.env["ir.actions.report"]._render_qweb_pdf("boteco_pos.report_fechamento_caixa", fechamento.ids)
        self.assertTrue(pdf)

    def test_caixa_precisa_do_pin_para_fechar(self):
        sessao = self._abrir_sessao()
        with self.assertRaisesRegex(UserError, "PIN do gerente"):
            sessao.with_user(self.caixa).boteco_registrar_contagem({})
        aut = self.env["boteco.autorizacao"].with_user(self.caixa).solicitar("7314", "pode_abrir_fechar_caixa")
        resultado = sessao.with_user(self.caixa).boteco_registrar_contagem({}, autorizacao_id=aut["id"])
        self.assertTrue(resultado["fechamento_id"])

    def test_nao_fecha_com_mesa_aberta(self):
        sessao = self._abrir_sessao()
        self._sincronizar(self._pedido([self._linha(self.chope, 1)], mesa=self.mesas[3]))
        with self.assertRaisesRegex(UserError, "Mesa 4"):
            sessao.with_user(self.gerente).boteco_registrar_contagem({})
        resposta = sessao.close_session_from_ui()
        self.assertFalse(resposta["successful"])
        self.assertIn("Mesa 4", resposta["message"])

    def test_abertura_auditada(self):
        self.config.open_ui()
        sessao = self.config.current_session_id
        sessao.with_user(self.caixa).set_opening_control(150, "Troco do dia")
        self.assertTrue(self.env["boteco.auditoria"].search([("acao", "=", "abrir_caixa"), ("res_id", "=", sessao.id), ("valor", "=", 150)]))

    def test_couvert_do_dia(self):
        empresa = self.env.company
        hoje = empresa.boteco_dia_operacao(fields.Datetime.now())
        self.env["boteco.agenda.musica"].create({"data": hoje, "artista": "Samba de Raiz", "valor_couvert": 15})
        dados = self._abrir_sessao()._boteco_dados_pdv()
        self.assertEqual(dados["couvert_valor"], 15)
        self.assertEqual(dados["couvert_artista"], "Samba de Raiz")
