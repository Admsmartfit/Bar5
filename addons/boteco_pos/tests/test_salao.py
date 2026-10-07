from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.boteco_cardapio.tests.common_pos import BotecoPosCase

from ..models.utils import dividir_em_partes


@tagged("post_install", "-at_install", "boteco")
class TestSalao(BotecoPosCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.ref("boteco_cardapio.happy_hour_padrao").active = False
        cls.taxa = cls.env.ref("boteco_pos.produto_taxa_servico")

    def _como(self, user):
        return self.env["pos.order"].with_user(user)

    def test_conta_de_4_dividida_em_3_pix_e_1_cartao_fecha_zerada(self):
        """Critério de aceite: conta de 4 pessoas em 3 PIX e 1 cartão fecha com saldo zero."""
        linhas = [self._linha(self.chope, 4), self._linha(self.porcao, 1)]
        consumo = sum(l["price_subtotal_incl"] for l in linhas)            # 82,00
        linhas.append(self._linha(self.taxa, 1, preco=round(consumo * 0.10, 2)))  # 8,20
        total = consumo + round(consumo * 0.10, 2)
        partes = dividir_em_partes(total, 4)
        pagamentos = [(self.pm_pix, partes[0]), (self.pm_pix, partes[1]), (self.pm_pix, partes[2]), (self.pm_cartao, partes[3])]
        pedido = self._sincronizar(self._pedido(linhas, mesa=self.mesa1, pessoas=4, pagamentos=pagamentos))
        self.assertEqual(pedido.state, "paid")
        self.assertAlmostEqual(pedido.amount_paid, pedido.amount_total, places=2)
        self.assertAlmostEqual(pedido.amount_total - pedido.amount_paid, 0.0, places=2)
        self.assertEqual(len(pedido.payment_ids), 4)
        self.assertAlmostEqual(pedido.boteco_taxa_servico, 8.2, places=2)

    def test_item_enviado_cancelado_sem_pin_e_bloqueado(self):
        """Critério de aceite: item cancelado após envio sem PIN de gerente é bloqueado."""
        linha = self._linha(self.chope, 2)
        dados = self._pedido([linha], mesa=self.mesa1)
        pedido = self._sincronizar(dados, self.garcom)
        self.assertEqual(pedido.lines.boteco_qtd_enviada, 2)
        # Garçom tenta baixar para 1 sem PIN
        dados_menos = dict(dados, lines=[[1, pedido.lines.id, {"qty": 1, "price_subtotal": 10, "price_subtotal_incl": 10}]])
        with self.assertRaisesRegex(UserError, "PIN do gerente"):
            self._sincronizar(dados_menos, self.garcom)
        # Garçom tenta apagar a linha
        dados_apaga = dict(dados, lines=[[2, pedido.lines.id]])
        with self.assertRaises(UserError):
            self._sincronizar(dados_apaga, self.garcom)
        # Com o PIN do gerente (autorização para aquela linha), passa e fica na auditoria
        resposta = self.env["boteco.autorizacao"].with_user(self.garcom).solicitar(
            "7314", "pode_cancelar_item", motivo="Desistência do cliente", referencia=linha["uuid"]
        )
        self.assertNotIn("erro", resposta)
        self._sincronizar(dados_menos, self.garcom)
        self.assertEqual(pedido.lines.qty, 1)
        registro = self.env["boteco.auditoria"].search([("acao", "=", "cancelar_item"), ("referencia", "=", linha["uuid"])])
        self.assertEqual(len(registro), 1)
        self.assertEqual(registro.autorizado_por_id, self.gerente)
        self.assertEqual(registro.motivo, "Desistência do cliente")
        self.assertAlmostEqual(registro.valor, 10.0)

    def test_item_nao_enviado_pode_apagar_livre(self):
        dados = self._pedido([self._linha(self.chope, 2)], mesa=self.mesa1, enviar=False)
        pedido = self._sincronizar(dados, self.garcom)
        self._sincronizar(dict(dados, lines=[[2, pedido.lines.id]]), self.garcom)
        self.assertFalse(pedido.lines)

    def test_desconto_e_cortesia_precisam_de_pin(self):
        sem_pin = self._pedido([self._linha(self.porcao, 1, discount=10, boteco_motivo="Cliente da casa")], mesa=self.mesa2)
        with self.assertRaisesRegex(UserError, "PIN do gerente"):
            self._sincronizar(sem_pin, self.garcom)
        aut = self.env["boteco.autorizacao"].with_user(self.garcom).solicitar("7314", "pode_dar_cortesia", motivo="Aniversariante")
        cortesia = self._pedido([self._linha(self.chope, 1, discount=100, boteco_cortesia=True,
                                             boteco_motivo="Aniversariante", boteco_autorizacao_ref=aut["id"])], mesa=self.mesa2)
        pedido = self._como(self.garcom).browse(self._sincronizar(cortesia, self.garcom).id)
        self.assertEqual(pedido.lines.boteco_autorizado_por_id, self.gerente)
        self.assertAlmostEqual(pedido.boteco_total_cortesia, 10.0)
        self.assertTrue(self.env["boteco.auditoria"].search([("acao", "=", "cortesia"), ("autorizado_por_id", "=", self.gerente.id)]))

    def test_consumo_de_funcionario(self):
        dados = self._pedido([self._linha(self.chope, 1, preco=self.chope.standard_price)], mesa=None,
                             boteco_tipo_conta="funcionario", boteco_funcionario_ref=self.garcom.id,
                             boteco_funcionario_modo="custo")
        with self.assertRaisesRegex(UserError, "PIN do gerente"):
            self._sincronizar(dados, self.garcom)
        aut = self.env["boteco.autorizacao"].with_user(self.garcom).solicitar("7314", "pode_consumo_funcionario")
        dados = self._pedido([self._linha(self.chope, 1, preco=self.chope.standard_price)], mesa=None,
                             boteco_tipo_conta="funcionario", boteco_funcionario_ref=self.garcom.id,
                             boteco_funcionario_modo="custo", boteco_autorizacao_ref=aut["id"])
        pedido = self.env["pos.order"].browse(self._sincronizar(dados, self.garcom).id)
        self.assertEqual(pedido.boteco_autorizado_por_id, self.gerente)
        self.assertEqual(pedido.boteco_funcionario_id, self.garcom)
        self.assertTrue(self.env["boteco.auditoria"].search([("acao", "=", "consumo_funcionario"), ("res_id", "=", pedido.id)]))

    def test_envio_para_producao_gera_mudancas(self):
        capturadas = []
        original = type(self.env["pos.order"])._boteco_ao_enviar

        def espiar(pedidos, mudancas):
            capturadas.append(mudancas)
            return original(pedidos, mudancas)

        self.patch(type(self.env["pos.order"]), "_boteco_ao_enviar", espiar)
        chope = self._linha(self.chope, 2, note="sem colarinho")
        dados = self._pedido([chope], mesa=self.mesa1)
        pedido = self._sincronizar(dados)
        self.assertEqual(capturadas[-1][0]["quantidade"], 2)
        self.assertEqual(capturadas[-1][0]["nota"], "sem colarinho")
        self.assertTrue(pedido.boteco_primeiro_envio)
        # Mesma sincronização de novo (sem linhas novas): nada novo
        self._sincronizar(dict(dados, lines=[]))
        self.assertEqual(len(capturadas), 1)
        # Acrescenta uma porção
        porcao = self._linha(self.porcao, 1)
        dados2 = dict(dados, lines=[[0, 0, porcao]],
                      last_order_preparation_change=self._snapshot_envio([chope, porcao]))
        self._sincronizar(dados2)
        self.assertEqual(len(capturadas), 2)
        self.assertEqual([m["quantidade"] for m in capturadas[-1]], [1])

    def test_cpf_na_nota(self):
        pedido = self._sincronizar(self._pedido([self._linha(self.refri, 1)], mesa=self.mesa1, boteco_cpf_nota="529.982.247-25"))
        self.assertEqual(pedido.boteco_cpf_nota, "52998224725")
        self.assertTrue(pedido.boteco_cpf_valido)

    def test_mesa_chamou_e_pediu_conta(self):
        self.mesa1.boteco_marcar(pediu_conta=True)
        self.assertTrue(self.mesa1.boteco_pediu_conta)
        self.mesa1._boteco_limpar_chamados()
        self.assertFalse(self.mesa1.boteco_pediu_conta)

    def test_dados_do_pdv(self):
        sessao = self._abrir_sessao()
        dados = sessao.with_user(self.garcom)._boteco_dados_pdv()
        self.assertFalse(dados["permissoes"]["pode_cancelar_item"])
        self.assertTrue(dados["permissoes"]["pode_aprovar_qr"])
        self.assertEqual(dados["taxa_pct"], 10.0)
        self.assertTrue(any(m["tipo"] == "cancelamento" for m in dados["motivos"]))

    def test_cancelar_conta_inteira_exige_pin(self):
        dados = self._pedido([self._linha(self.chope, 2), self._linha(self.porcao, 1)], mesa=self.mesa1)
        pedido = self._sincronizar(dados, self.garcom)
        with self.assertRaises(UserError):
            self.env["pos.order"].with_user(self.garcom).remove_from_ui([pedido.id])
        self.env["boteco.autorizacao"].with_user(self.garcom).solicitar(
            "7314", "pode_cancelar_item", motivo="Desistência do cliente", referencia=pedido.uuid)
        self.env["pos.order"].with_user(self.garcom).remove_from_ui([pedido.id])
        self.assertEqual(self.env["boteco.auditoria"].search_count([("acao", "=", "cancelar_item"), ("res_id", "=", pedido.id)]), 2)

    def test_tela_nao_sobrescreve_campos_do_servidor(self):
        """O PDV devolve tudo o que carregou (com valores vazios/antigos): o servidor ignora."""
        linha = self._linha(self.chope, 2, boteco_qtd_enviada=0, boteco_preco_origem=False)
        dados = self._pedido([linha], mesa=self.mesa1, boteco_tipo_conta=False, boteco_origem=False,
                             boteco_snapshot_envio=False, boteco_primeiro_envio=False)
        pedido = self._sincronizar(dados, self.garcom)
        self.assertEqual(pedido.boteco_tipo_conta, "normal")
        self.assertEqual(pedido.lines.boteco_qtd_enviada, 2)
        # Reenvio com snapshot antigo vindo da tela não gera novo envio nem zera a quantidade enviada
        reenvio = dict(dados, lines=[[1, pedido.lines.id, {"boteco_qtd_enviada": 0, "qty": 2}]],
                       boteco_snapshot_envio="{}")
        self._sincronizar(reenvio, self.garcom)
        self.assertEqual(pedido.lines.boteco_qtd_enviada, 2)
