import base64
from datetime import timedelta

from odoo import fields
from odoo.tests import tagged

from odoo.addons.boteco_cardapio.tests.common_pos import BotecoPosCase
from odoo.addons.boteco_conciliacao.models.conciliacao import dia_util


@tagged("post_install", "-at_install", "boteco")
class TestConciliacao(BotecoPosCase):
    """Etapa 28: recebíveis, extrato da maquininha e do banco."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.ref("boteco_cardapio.happy_hour_padrao").active = False
        cls.env.company.boteco_flag_conciliacao_cartoes = True
        cls.stone = cls.env["boteco.adquirente"].create({"name": "Stone", "taxa_ids": [
            fields.Command.create({"modalidade": "credito", "taxa_pct": 3.0, "prazo_dias": 30}),
            fields.Command.create({"modalidade": "debito", "taxa_pct": 1.0, "prazo_dias": 1}),
        ]})
        cls.pm_cartao.write({"boteco_adquirente_id": cls.stone.id, "boteco_modalidade": "credito"})
        cls.pm_pix.write({"boteco_modalidade": "pix", "boteco_taxa_pct": 0.0, "boteco_dias_recebimento": 0})
        cls.Recebivel = cls.env["boteco.recebivel"]

    def _vender(self, valor, metodo=None):
        dados = self._pedido([self._linha(self.batata, 1, preco=valor)], pagamentos=[(metodo or self.pm_cartao, valor)])
        return self._sincronizar(dados)

    def _recebivel(self, pedido):
        return self.Recebivel.search([("order_id", "=", pedido.id)])

    def _importar(self, tipo, conteudo, nome):
        extrato = self.env["boteco.extrato"].create({
            "tipo": tipo, "adquirente_id": self.stone.id if tipo == "maquininha" else False,
            "arquivo": base64.b64encode(conteudo.encode("utf-8")), "arquivo_nome": nome})
        extrato.action_importar()
        return extrato

    def _csv(self, linhas):
        cabecalho = "Data da venda;Valor bruto;Valor líquido;NSU;Bandeira;Produto\n"
        return cabecalho + "".join("%s;%s;%s;%s;Visa;Crédito\n" % l for l in linhas)

    def test_pagamento_vira_recebivel_com_taxa_e_prazo(self):
        r = self._recebivel(self._vender(100.0))
        self.assertEqual(r.adquirente_id, self.stone)
        self.assertEqual(r.taxa_esperada_pct, 3.0)
        self.assertEqual(r.liquido_esperado, 97.0)
        self.assertEqual(r.data_prevista, dia_util(r.data_venda, 30))
        self.assertEqual(r.estado, "previsto")
        self.assertFalse(self._recebivel(self._vender(20.0, self.pm_dinheiro)))  # dinheiro não vira recebível

    def test_flag_desligada_nao_gera_recebivel_e_some_do_painel(self):
        self.env.company.boteco_flag_conciliacao_cartoes = False
        self.assertFalse(self._recebivel(self._vender(50.0)))
        self.assertNotIn("cartoes", self.env["boteco.painel"].dados())

    def test_extrato_casa_iguais_e_aponta_diferencas(self):
        a, b, c = (self._recebivel(self._vender(v)) for v in (100.0, 50.0, 80.0))
        dia = a.data_venda.strftime("%d/%m/%Y")
        extrato = self._importar("maquininha", self._csv([
            (dia, "100,00", "97,00", "111"), (dia, "50,00", "48,50", "222"), (dia, "35,00", "33,95", "333"),
        ]), "stone.csv")
        self.assertEqual((a.estado, b.estado), ("conferido", "conferido"))
        self.assertEqual(a.nsu, "111")
        self.assertEqual(c.estado, "divergente")  # venda no caixa sem registro na maquininha
        self.assertIn("sem registro na maquininha", c.alerta)
        conferir = extrato.linha_ids.filtered(lambda l: l.estado == "conferir")
        self.assertEqual(conferir.valor_bruto, 35.0)  # venda na maquininha sem registro no caixa
        self.assertEqual(extrato.n_casadas, 2)

    def test_taxa_acima_da_contratada_mostra_o_valor_perdido(self):
        r = self._recebivel(self._vender(1000.0))
        dia = r.data_venda.strftime("%d/%m/%Y")
        self._importar("maquininha", self._csv([(dia, "1.000,00", "967,00", "9")]), "stone.csv")  # 3,3% em vez de 3%
        self.assertEqual(r.estado, "divergente")
        self.assertAlmostEqual(r.taxa_cobrada_pct, 3.3)
        self.assertAlmostEqual(r.valor_perdido, 3.0)
        self.assertIn("acima da contratada", r.alerta)

    def test_repasse_atrasado(self):
        r = self._recebivel(self._vender(60.0))
        r.data_prevista = fields.Date.today() - timedelta(days=5)
        self.Recebivel._cron_atrasados()
        self.assertEqual(r.estado, "atrasado")
        self.assertEqual(self.env["boteco.painel"].dados()["cartoes"]["atrasados"], 1)

    def test_extrato_do_banco_pix_e_repasse(self):
        pix = self._recebivel(self._vender(42.0, self.pm_pix))
        cartao = self._recebivel(self._vender(100.0))
        hoje = fields.Date.today()
        cartao.data_prevista = hoje
        ofx = """OFXHEADER:100
<OFX><BANKMSGSRSV1><STMTTRNRS><STMTRS><BANKTRANLIST>
<STMTTRN><TRNTYPE>CREDIT<DTPOSTED>{d}120000<TRNAMT>42.00<FITID>A1<MEMO>PIX RECEBIDO</STMTTRN>
<STMTTRN><TRNTYPE>CREDIT<DTPOSTED>{d}120000<TRNAMT>97.00<FITID>A2<MEMO>STONE REPASSE</STMTTRN>
<STMTTRN><TRNTYPE>CREDIT<DTPOSTED>{d}120000<TRNAMT>15.00<FITID>A3<MEMO>PIX DESCONHECIDO</STMTTRN>
<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>{d}120000<TRNAMT>-300.00<FITID>A4<MEMO>FORNECEDOR</STMTTRN>
</BANKTRANLIST></STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>""".format(d=hoje.strftime("%Y%m%d"))
        extrato = self._importar("banco", ofx, "banco.ofx")
        self.assertEqual(pix.estado, "pago")
        self.assertEqual(cartao.estado, "pago")
        conferir = extrato.linha_ids.filtered(lambda l: l.estado == "conferir")
        self.assertEqual(conferir.valor_bruto, 15.0)  # Pix sem venda vai para "Conferir"
        self.assertEqual(extrato.linha_ids.filtered(lambda l: l.tipo_linha == "debito").estado, "ignorado")

    def test_estorno_no_extrato(self):
        r = self._recebivel(self._vender(70.0))
        dia = r.data_venda.strftime("%d/%m/%Y")
        self._importar("maquininha", "Data;Valor;NSU;Status\n%s;-70,00;55;Estornada\n" % dia, "estornos.csv")
        self.assertEqual(r.estado, "estornado")

    def test_painel_e_caixa(self):
        r = self._recebivel(self._vender(100.0))
        cartoes = self.env["boteco.painel"].dados()["cartoes"]
        self.assertEqual(cartoes["taxa_mes"][0]["nome"], "Stone")
        self.assertAlmostEqual(cartoes["taxa_mes"][0]["valor"], 3.0)
        self.assertEqual(r.session_id.boteco_cartoes_total, 100.0)
        self.assertEqual(r.session_id.boteco_cartoes_confirmado, 0.0)
