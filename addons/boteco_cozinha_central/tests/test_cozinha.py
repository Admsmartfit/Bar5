import time
from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.boteco_base.tests.common import BotecoCase
from odoo.addons.boteco_base.tests.test_escpos import ImpressoraFalsa


@tagged("post_install", "-at_install", "boteco")
class TestCozinhaCentral(BotecoCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.cozinheiro = cls._pessoa("Fábio Cozinha", "fabio_teste", cls.env.ref("boteco_base.perfil_cozinheiro"), "5937")
        company = cls.env.company
        company.write({"vat": "11.222.333/0001-81", "boteco_registro_sanitario": "SIF 1234"})
        Armazem = cls.env["stock.warehouse"]
        cls.bar = Armazem.search([("company_id", "=", company.id)], limit=1)
        cls.cc = Armazem.create({"name": "Cozinha Central (teste)", "code": "CCT", "boteco_tipo_unidade": "cozinha_central"})
        kg = cls.env.ref("uom.product_uom_kgm")
        Produto = cls.env["product.product"]
        cls.bacalhau = Produto.create({"name": "Bacalhau dessalgado", "is_storable": True, "uom_id": kg.id,
                                       "uom_po_id": kg.id, "standard_price": 80.0})
        cls.batata = Produto.create({"name": "Batata", "is_storable": True, "uom_id": kg.id, "uom_po_id": kg.id,
                                     "standard_price": 5.0})
        cls.bolinho = Produto.create({"name": "Massa de bolinho de bacalhau", "boteco_produzido_cozinha": True,
                                      "uom_id": kg.id, "uom_po_id": kg.id, "expiration_time": 90,
                                      "boteco_conservacao": "congelado", "sale_ok": True, "list_price": 42.0})
        cls.receita = cls.env["mrp.bom"].create({
            "product_tmpl_id": cls.bolinho.product_tmpl_id.id, "product_qty": 10.0, "product_uom_id": kg.id,
            "type": "normal", "boteco_perda_esperada": 5.0,
            "bom_line_ids": [fields.Command.create({"product_id": cls.bacalhau.id, "product_qty": 4.0}),
                             fields.Command.create({"product_id": cls.batata.id, "product_qty": 7.0})],
        })
        Quant = cls.env["stock.quant"].with_context(inventory_mode=True)
        for produto, qtd in ((cls.bacalhau, 50), (cls.batata, 100)):
            Quant.create({"product_id": produto.id, "location_id": cls.cc.lot_stock_id.id,
                          "inventory_quantity": qtd}).action_apply_inventory()

    def setUp(self):
        super().setUp()
        self.falsa = ImpressoraFalsa()
        self.addCleanup(self.falsa.fechar)
        self.impressora = self.env["boteco.impressora"].create(
            {"name": "Etiquetas", "ip": "127.0.0.1", "porta": self.falsa.porta, "linguagem": "zpl"})
        self.cc.boteco_impressora_etiqueta_id = self.impressora

    def _producao(self, qtd=10.0):
        producao = self.env["mrp.production"].create({
            "product_id": self.bolinho.id, "bom_id": self.receita.id, "product_qty": qtd,
            "picking_type_id": self.cc.manu_type_id.id,
            "location_src_id": self.cc.lot_stock_id.id, "location_dest_id": self.cc.lot_stock_id.id,
        })
        producao.action_confirm()
        return producao

    def _produzir(self, peso=9.6):
        producao = self._producao()
        producao.with_user(self.cozinheiro).boteco_iniciar()
        resultado = producao.with_user(self.cozinheiro).boteco_finalizar(peso)
        return producao, resultado

    def test_insumo_sem_saldo_so_fecha_com_pin_do_gerente(self):
        """Auditoria: produzir sem matéria-prima no estoque deixaria o saldo negativo."""
        producao = self._producao(qtd=200.0)  # precisa de 80 kg de bacalhau; o estoque tem 50
        producao.with_user(self.cozinheiro).boteco_iniciar()
        r = producao.with_user(self.cozinheiro).boteco_finalizar(190)
        self.assertTrue(r["precisa_pin"])
        self.assertEqual(r["faltas"][0]["nome"], "Bacalhau dessalgado")
        self.assertNotEqual(producao.state, "done")
        r = producao.with_user(self.cozinheiro).boteco_finalizar(190, "0000")
        self.assertEqual(r["erro"], "PIN não confere.")
        self.assertNotEqual(producao.state, "done")
        producao.with_user(self.cozinheiro).boteco_finalizar(190, "7314")  # gerente libera
        self.assertEqual(producao.state, "done")
        self.assertTrue(self.env["boteco.auditoria"].search([("acao", "=", "ajuste_estoque"),
                                                             ("descricao", "ilike", producao.name)]))

    def test_mesma_etiqueta_lida_duas_vezes_conta_uma(self):
        producao, _r = self._produzir(9.6)
        lote = producao.lot_producing_id
        picking = self.env["stock.picking"].create({
            "picking_type_id": self.cc.int_type_id.id, "location_id": self.cc.lot_stock_id.id,
            "location_dest_id": self.bar.lot_stock_id.id,
            "move_ids": [fields.Command.create({"name": "Massa", "product_id": self.bolinho.id, "product_uom_qty": 5.0,
                                                "product_uom": self.bolinho.uom_id.id,
                                                "location_id": self.cc.lot_stock_id.id,
                                                "location_dest_id": self.bar.lot_stock_id.id})],
        })
        picking.action_confirm()
        picking.boteco_ler_lote(lote.name)
        with self.assertRaisesRegex(UserError, "já foi lido"):
            picking.boteco_ler_lote(lote.name)
        self.assertAlmostEqual(sum(picking.move_ids.move_line_ids.filtered("picked").mapped("quantity")), 5.0)

    def test_finalizar_gera_lote_baixa_insumos_e_imprime_etiqueta_em_3s(self):
        """Critérios: etiqueta em até 3 s; cozinheiro só digita o peso."""
        inicio = time.time()
        producao, resultado = self._produzir(9.6)
        self.env["boteco.impressao.job"].search([("estado", "=", "esperando")])._enviar()
        limite = time.time() + 3
        while not self.falsa.recebido and time.time() < limite:
            time.sleep(0.02)
        self.assertLess(time.time() - inicio, 3.0)
        self.assertTrue(self.falsa.recebido, "etiqueta não saiu")
        zpl = self.falsa.recebido[0].decode("utf-8")
        lote = producao.lot_producing_id
        self.assertTrue(lote)
        for esperado in ("Massa de bolinho de bacalhau", lote.name, "VALIDADE", "MANTER CONGELADO", "11.222.333/0001-81",
                         "SIF 1234", "9,600 kg", "^BQN"):
            self.assertIn(esperado, zpl)
        self.assertEqual(producao.state, "done")
        self.assertTrue(lote.name.startswith("CC"))
        self.assertEqual(lote.boteco_peso, 9.6)
        self.assertEqual(lote.boteco_fabricacao, fields.Date.context_today(producao))
        self.assertAlmostEqual((lote.expiration_date.date() - fields.Date.today()).days, 90, delta=1)
        self.assertEqual(resultado["rendimento"], 96.0)
        # Insumos da receita inteira, não proporcionais ao peso
        consumido = {m.product_id: m.quantity for m in producao.move_raw_ids}
        self.assertEqual(consumido[self.bacalhau], 4.0)
        self.assertEqual(consumido[self.batata], 7.0)
        self.assertAlmostEqual(self.bolinho.with_context(location=self.cc.lot_stock_id.id).qty_available, 9.6)

    def test_lote_vencido_nao_pode_ser_transferido(self):
        """Critério: tentar transferir um lote vencido é bloqueado."""
        producao, _r = self._produzir(10)
        lote = producao.lot_producing_id
        lote.expiration_date = fields.Datetime.now() - timedelta(days=1)
        self.assertEqual(lote.boteco_situacao, "vencido")
        transferencia = self.env["stock.picking"].create({
            "picking_type_id": self.cc.int_type_id.id, "location_id": self.cc.lot_stock_id.id,
            "location_dest_id": self.bar.lot_stock_id.id,
            "move_ids": [fields.Command.create({"name": "x", "product_id": self.bolinho.id, "product_uom_qty": 2,
                                                "product_uom": self.bolinho.uom_id.id,
                                                "location_id": self.cc.lot_stock_id.id,
                                                "location_dest_id": self.bar.lot_stock_id.id})],
        })
        transferencia.action_confirm()
        with self.assertRaisesRegex(UserError, "VENCIDO"):
            transferencia.boteco_ler_lote(lote.name)
        # Mesmo forçando a linha, a validação bloqueia
        self.env["stock.move.line"].create({
            "move_id": transferencia.move_ids.id, "picking_id": transferencia.id, "product_id": self.bolinho.id,
            "lot_id": lote.id, "quantity": 2, "location_id": self.cc.lot_stock_id.id,
            "location_dest_id": self.bar.lot_stock_id.id, "picked": True,
        })
        transferencia.move_ids.move_line_ids.filtered(lambda ml: ml.lot_id != lote).unlink()
        with self.assertRaisesRegex(UserError, "bloqueado"):
            transferencia.move_ids.picked = True
            transferencia._action_done()

    def test_vencendo_em_3_dias_fica_amarelo(self):
        producao, _r = self._produzir(10)
        lote = producao.lot_producing_id
        lote.expiration_date = fields.Datetime.now() + timedelta(days=2)
        self.assertEqual(lote.boteco_situacao, "vencendo")
        self.assertIn(lote, self.env["stock.lot"].search([("boteco_situacao", "=", "vencendo")]))

    def test_transferencia_para_o_bar_lendo_qr_e_confirmando(self):
        producao, _r = self._produzir(10)
        lote = producao.lot_producing_id
        transferencia = self.env["stock.picking"].create({
            "picking_type_id": self.cc.int_type_id.id, "location_id": self.cc.lot_stock_id.id,
            "location_dest_id": self.bar.lot_stock_id.id,
            "move_ids": [fields.Command.create({"name": "x", "product_id": self.bolinho.id, "product_uom_qty": 3,
                                                "product_uom": self.bolinho.uom_id.id,
                                                "location_id": self.cc.lot_stock_id.id,
                                                "location_dest_id": self.bar.lot_stock_id.id})],
        })
        transferencia.action_confirm()
        with self.assertRaises(UserError):
            transferencia.action_boteco_confirmar_recebimento()  # ainda não separado
        transferencia.boteco_ler_lote(lote.name)
        transferencia.boteco_concluir_separacao()
        self.assertTrue(transferencia.boteco_separado)
        transferencia.action_boteco_confirmar_recebimento()
        self.assertEqual(transferencia.state, "done")
        rastreio = lote.boteco_rastreio()
        self.assertTrue(any(d["tipo"] == "unidade" for d in rastreio["destinos"]))

    def test_rastreio_mostra_insumos_e_clientes(self):
        """Critério: busca por um código de lote mostra todos os clientes que o receberam."""
        producao, _r = self._produzir(10)
        lote = producao.lot_producing_id
        clientes = self.env["res.partner"].create([{"name": "Bar do Zé"}, {"name": "Bar da Tia"}])
        for cliente in clientes:
            venda = self.env["sale.order"].create({
                "partner_id": cliente.id, "warehouse_id": self.cc.id,
                "order_line": [fields.Command.create({"product_id": self.bolinho.id, "product_uom_qty": 2})],
            })
            venda.action_confirm()
            entrega = venda.picking_ids
            entrega.boteco_ler_lote(lote.name)
            entrega.boteco_concluir_separacao()
            self.assertEqual(entrega.state, "done")
        dados = self.env["stock.lot"].boteco_buscar_rastreio(lote.name)
        self.assertEqual(dados["clientes"], ["Bar da Tia", "Bar do Zé"])
        self.assertEqual({i["produto"] for i in dados["insumos"]}, {"Bacalhau dessalgado", "Batata"})
        assistente = self.env["boteco.rastreio"].create({"codigo": lote.name})
        assistente.action_buscar()
        self.assertIn("Bar do Zé", assistente.clientes)

    def test_temperatura_fora_da_faixa(self):
        freezer = self.env["boteco.equipamento"].create({"name": "Freezer 1", "tipo": "freezer",
                                                          "temperatura_min": -25, "temperatura_max": -18})
        ok = self.env["boteco.temperatura"].boteco_registrar(freezer.id, -20)
        ruim = self.env["boteco.temperatura"].boteco_registrar(freezer.id, -12, "Porta mal fechada, ajustada")
        self.assertFalse(ok["fora_da_faixa"])
        self.assertTrue(ruim["fora_da_faixa"])
        registros = self.env["boteco.temperatura"].browse([ok["id"], ruim["id"]])
        pdf, _tipo = self.env["ir.actions.report"]._render_qweb_pdf("boteco_cozinha_central.report_temperatura", registros.ids)
        self.assertTrue(pdf)

    def test_plano_de_producao_considera_b2b(self):
        cliente = self.env["res.partner"].create({"name": "Bar Cliente"})
        venda = self.env["sale.order"].create({
            "partner_id": cliente.id, "warehouse_id": self.cc.id, "commitment_date": fields.Datetime.now(),
            "order_line": [fields.Command.create({"product_id": self.bolinho.id, "product_uom_qty": 15})],
        })
        venda.action_confirm()
        plano = self.env["boteco.plano.producao"].create({})
        plano.action_calcular()
        linha = plano.linha_ids.filtered(lambda l: l.product_id == self.bolinho)
        self.assertEqual(linha.pedidos_b2b, 15)
        self.assertEqual(linha.quantidade, 20)  # 2 receitas de 10 kg
        plano.action_criar_producoes()
        self.assertTrue(self.env["mrp.production"].search([("product_id", "=", self.bolinho.id), ("state", "=", "confirmed")]))
