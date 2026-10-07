import psycopg2

from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tools import mute_logger

from .common import BotecoCase


@tagged("post_install", "-at_install", "boteco")
class TestAuditoria(BotecoCase):
    def test_alterar_preco_grava_quem_quando_antes_depois(self):
        """Critério de aceite da Etapa 0."""
        produto = self.env["product.template"].create({"name": "Chope 300 ml", "list_price": 9.0})
        produto.with_user(self.env.ref("base.user_admin")).list_price = 11.5
        registro = self.env["boteco.auditoria"].search(
            [("acao", "=", "alteracao_preco"), ("modelo", "=", "product.template"), ("res_id", "=", produto.id)]
        )
        self.assertEqual(len(registro), 1)
        self.assertEqual(registro.valor_antigo, "9.00")
        self.assertEqual(registro.valor_novo, "11.50")
        self.assertEqual(registro.usuario_id, self.env.ref("base.user_admin"))
        self.assertTrue(registro.data)

    def test_auditoria_nao_pode_ser_alterada_nem_apagada(self):
        registro = self.env["boteco.auditoria"].registrar("outro", descricao="teste")
        with self.assertRaises(UserError):
            registro.write({"descricao": "adulterado"})
        with self.assertRaises(UserError):
            registro.unlink()

    @mute_logger("odoo.sql_db")
    def test_gatilho_bloqueia_sql_direto(self):
        registro = self.env["boteco.auditoria"].registrar("outro", descricao="teste")
        with self.assertRaises(psycopg2.Error), self.env.cr.savepoint():
            self.env.cr.execute("UPDATE boteco_auditoria SET descricao = 'x' WHERE id = %s", [registro.id])
        with self.assertRaises(psycopg2.Error), self.env.cr.savepoint():
            self.env.cr.execute("DELETE FROM boteco_auditoria WHERE id = %s", [registro.id])

    def test_autorizacao_do_gerente(self):
        Autorizacao = self.env["boteco.autorizacao"].with_user(self.garcom)
        # PIN do garçom não autoriza cancelamento
        recusa = Autorizacao.solicitar("2580", "pode_cancelar_item", motivo="Erro do garçom")
        self.assertIn("erro", recusa)
        # PIN do gerente autoriza
        res = Autorizacao.solicitar("7314", "pode_cancelar_item", motivo="Erro do garçom", referencia="linha-1")
        self.assertEqual(res["autorizado_por_id"], self.gerente.id)
        usada = self.env["boteco.autorizacao"].consumir("pode_cancelar_item", referencia="linha-1")
        self.assertTrue(usada)
        # Não pode ser usada duas vezes
        self.assertFalse(self.env["boteco.autorizacao"].consumir("pode_cancelar_item", referencia="linha-1"))
        negadas = self.env["boteco.auditoria"].search([("acao", "=", "autorizacao_negada")])
        self.assertTrue(negadas)

    def test_autorizacao_bloqueia_apos_5_pins_errados(self):
        Autorizacao = self.env["boteco.autorizacao"].with_user(self.garcom)
        for _i in range(5):
            self.assertIn("erro", Autorizacao.solicitar("9999", "pode_dar_desconto"))
        resposta = Autorizacao.solicitar("7314", "pode_dar_desconto")
        self.assertTrue(resposta.get("bloqueado"))

    def test_gerente_nao_precisa_digitar_o_proprio_pin(self):
        res = self.env["boteco.autorizacao"].with_user(self.gerente).solicitar(None, "pode_dar_desconto")
        self.assertEqual(res["autorizado_por_id"], self.gerente.id)
