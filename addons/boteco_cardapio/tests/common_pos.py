"""Base dos testes que precisam de um PDV de restaurante (usada pelos módulos boteco_*).

Monta: plano de contas genérico (se faltar), diário de dinheiro e de banco, formas de
pagamento Dinheiro/PIX/Cartão, PDV "Bar Teste" com autoatendimento por QR, salão com 6 mesas
e produtos de bar e de chapa. ``_sincronizar`` envia pedidos como o PDV real faz
(``pos.order.sync_from_ui``), incluindo o "mandar pra cozinha" (last_order_preparation_change).
"""

import copy
import json
import uuid as uuid_lib

from odoo import fields

from odoo.addons.boteco_base.tests.common import BotecoCase


class BotecoPosCase(BotecoCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company = cls.env.company
        company.partner_id.tz = "America/Sao_Paulo"
        if not company.chart_template:
            cls.env["account.chart.template"].try_loading("generic_coa", company=company, install_demo=False)

        Journal = cls.env["account.journal"]
        cls.diario_caixa = Journal.create({"name": "Caixa do bar (teste)", "type": "cash", "code": "CXBT"})
        cls.diario_banco = Journal.create({"name": "Banco (teste)", "type": "bank", "code": "BKBT"})
        Metodo = cls.env["pos.payment.method"]
        cls.pm_dinheiro = Metodo.create({"name": "Dinheiro", "journal_id": cls.diario_caixa.id})
        cls.pm_pix = Metodo.create({"name": "PIX", "journal_id": cls.diario_banco.id})
        cls.pm_cartao = Metodo.create({"name": "Cartão", "journal_id": cls.diario_banco.id})

        cls.setor_bar = cls.env.ref("boteco_base.setor_bar")
        cls.setor_chapa = cls.env.ref("boteco_base.setor_chapa")

        cls.config = cls.env["pos.config"].create(
            {
                "name": "Bar Teste",
                "module_pos_restaurant": True,
                "payment_method_ids": [fields.Command.set([cls.pm_dinheiro.id, cls.pm_pix.id, cls.pm_cartao.id])],
                "self_ordering_mode": "mobile",
                "self_ordering_service_mode": "table",
                "self_ordering_default_user_id": cls.env.ref("base.user_admin").id,
            }
        )
        cls.salao = cls.env["restaurant.floor"].create({"name": "Salão", "pos_config_ids": [fields.Command.link(cls.config.id)]})
        cls.mesas = cls.env["restaurant.table"]
        for numero in range(1, 7):
            cls.mesas |= cls.env["restaurant.table"].create(
                {"table_number": numero, "floor_id": cls.salao.id, "seats": 4}
            )
        cls.mesa1, cls.mesa2 = cls.mesas[0], cls.mesas[1]

        categoria = cls.env["pos.category"].create({"name": "Cervejas"})
        Produto = cls.env["product.product"]
        base = {"available_in_pos": True, "taxes_id": [fields.Command.clear()], "type": "consu"}
        cls.chope = Produto.create({**base, "name": "Chope 300 ml", "list_price": 10.0, "standard_price": 3.0,
                                    "boteco_setor_id": cls.setor_bar.id, "boteco_maior_18": True,
                                    "boteco_preco_happy": 7.0, "pos_categ_ids": [fields.Command.link(categoria.id)]})
        cls.refri = Produto.create({**base, "name": "Refrigerante lata", "list_price": 7.0, "standard_price": 2.5,
                                    "boteco_setor_id": cls.setor_bar.id})
        cls.porcao = Produto.create({**base, "name": "Porção de bolinho", "list_price": 42.0, "standard_price": 14.0,
                                     "boteco_setor_id": cls.setor_chapa.id, "boteco_tempo_preparo": 15})
        cls.batata = Produto.create({**base, "name": "Batata frita", "list_price": 30.0, "standard_price": 8.0,
                                     "boteco_setor_id": cls.setor_chapa.id})

    # ------------------------------------------------------------------
    def _abrir_sessao(self, troco=0.0):
        if not self.config.current_session_id:
            self.config.open_ui()
        sessao = self.config.current_session_id
        if sessao.state == "opening_control":
            sessao.set_opening_control(troco, None)
        return sessao

    @staticmethod
    def _uuid():
        return str(uuid_lib.uuid4())

    def _linha(self, produto, qtd=1.0, preco=None, uuid=None, **extra):
        preco = produto.lst_price if preco is None else preco
        return {
            "uuid": uuid or self._uuid(),
            "product_id": produto.id,
            "qty": qtd,
            "price_unit": preco,
            "price_subtotal": preco * qtd * (1 - extra.get("discount", 0.0) / 100.0),
            "price_subtotal_incl": preco * qtd * (1 - extra.get("discount", 0.0) / 100.0),
            "discount": extra.pop("discount", 0.0),
            "tax_ids": [],
            "pack_lot_ids": [],
            "full_product_name": produto.display_name,
            **extra,
        }

    @staticmethod
    def _snapshot_envio(linhas, anterior=None):
        """Monta o last_order_preparation_change como o PDV faz ao 'mandar pra cozinha'."""
        snapshot = json.loads(anterior) if anterior else {"lines": {}}
        snapshot.setdefault("lines", {})
        for linha in linhas:
            chave = "%s - %s" % (linha["uuid"], linha.get("note") or "")
            snapshot["lines"][chave] = {
                "uuid": linha["uuid"],
                "product_id": linha["product_id"],
                "name": linha.get("full_product_name"),
                "note": linha.get("note") or "",
                "quantity": linha["qty"],
                "attribute_value_ids": [],
            }
        snapshot["generalNote"] = ""
        snapshot["sittingMode"] = "dine in"
        snapshot["metadata"] = {"serverDate": fields.Datetime.to_string(fields.Datetime.now())}
        return json.dumps(snapshot)

    def _pedido(self, linhas, mesa=None, uuid=None, enviar=True, pagamentos=None, pessoas=2, **extra):
        sessao = self._abrir_sessao()
        total = sum(l["price_subtotal_incl"] for l in linhas)
        dados = {
            "uuid": uuid or self._uuid(),
            "access_token": self._uuid(),
            "name": "Pedido %s" % (uuid or self._uuid())[:8],
            "session_id": sessao.id,
            "pricelist_id": self.config.pricelist_id.id,
            "fiscal_position_id": False,
            "date_order": fields.Datetime.to_string(fields.Datetime.now()),
            "user_id": self.env.uid,
            "table_id": mesa.id if mesa else False,
            "customer_count": pessoas,
            "sequence_number": 1,
            "lines": [[0, 0, linha] for linha in linhas],
            "amount_total": total,
            "amount_tax": 0.0,
            "amount_paid": 0.0,
            "amount_return": 0.0,
            "state": "draft",
            "last_order_preparation_change": self._snapshot_envio(linhas) if enviar else "{}",
            **extra,
        }
        if pagamentos is not None:
            dados["payment_ids"] = [
                [0, 0, {"amount": valor, "name": fields.Datetime.now(), "payment_method_id": metodo.id}]
                for metodo, valor in pagamentos
            ]
            dados["amount_paid"] = sum(v for _m, v in pagamentos)
            dados["state"] = "paid"
        return dados

    def _sincronizar(self, dados, user=None):
        """Envia como o PDV faz. Copia o dicionário: o sync_from_ui altera o que recebe."""
        Pedido = self.env["pos.order"].with_user(user) if user else self.env["pos.order"]
        resultado = Pedido.sync_from_ui([copy.deepcopy(dados)])
        return self.env["pos.order"].browse(resultado["pos.order"][0]["id"])
