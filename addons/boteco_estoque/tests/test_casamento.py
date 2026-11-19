from odoo import fields
from odoo.tests import BaseCase, TransactionCase, tagged

from odoo.addons.boteco_estoque.tools import casamento, orcamento


@tagged("post_install", "-at_install", "boteco")
class TestCasamentoPuro(BaseCase):
    """Regras do reconhecimento de insumo (sem banco)."""

    def test_palavra_inteira_e_sem_acento(self):
        self.assertEqual(casamento.pontuar("Cebola kg", "Calabresa acebolada"), 0.0)
        self.assertEqual(casamento.pontuar("Limão tahiti", "Limao Tahiti"), 1.0)
        self.assertEqual(casamento.pontuar("Batatas lavadas", "Batata lavada"), 1.0)

    def test_tamanho_precisa_bater(self):
        self.assertEqual(casamento.pontuar("Cerveja Heineken 330ml", "Cerveja 600 ml"), 0.0)
        self.assertEqual(casamento.pontuar("Refrigerante Guaraná 2L", "Refrigerante lata"), 0.0)
        self.assertEqual(casamento.pontuar("Cerveja Brahma 600ml cx c/24", "Cerveja 600 ml"), 1.0)

    def test_embalagem_vira_preco_por_unidade(self):
        self.assertEqual(casamento.embalagem("Cerveja 600ml cx c/24"), 24)
        self.assertEqual(casamento.embalagem("Água fardo c/12"), 12)
        self.assertEqual(casamento.embalagem("Refrigerante 2L"), 1)
        self.assertEqual(casamento.quantidade_no_insumo("Batata pct 2,5kg", "", ("weight", 1.0)), (2.5, True))
        self.assertEqual(casamento.quantidade_no_insumo("Alcatra", "kg", ("weight", 1.0)), (1.0, True))
        self.assertEqual(casamento.quantidade_no_insumo("Óleo 900ml cx c/20", "", ("volume", 1.0))[0], 18.0)

    def test_leitor_separa_legenda_e_ignora_condicoes(self):
        itens = orcamento.ler_texto("🔥OFERTA DO DIA🔥 Alcatra R$ 39,90/kg e Linguiça toscana 2 por 25,00! Só hoje #açougue\n"
                                    "Pedido mínimo R$ 300,00\nFrete grátis acima de 500,00")
        self.assertEqual([(i["descricao"], i["preco"]) for i in itens], [("Alcatra", 39.9), ("Linguiça toscana", 12.5)])
        self.assertEqual(itens[0]["unidade"], "kg")


@tagged("post_install", "-at_install", "boteco")
class TestCasamentoNoBanco(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Produto = cls.env["product.product"]
        un = cls.env.ref("uom.product_uom_unit")
        kg = cls.env.ref("uom.product_uom_kgm")
        cls.cerveja = Produto.create({"name": "Cerveja 600 ml", "purchase_ok": True, "uom_id": un.id, "uom_po_id": un.id})
        cls.long_neck = Produto.create({"name": "Long neck", "purchase_ok": True, "uom_id": un.id, "uom_po_id": un.id})
        cls.cebola = Produto.create({"name": "Cebola", "purchase_ok": True, "uom_id": kg.id, "uom_po_id": kg.id})
        # Prato do cardápio (vendido no PDV, da chapa): nunca recebe preço de fornecedor
        cls.prato = Produto.create({"name": "Calabresa acebolada com cebola", "purchase_ok": True, "available_in_pos": True,
                                    "boteco_tipo_consumo": "prato_compartilhado"})
        cls.Importar = cls.env["boteco.importar.orcamento"]

    def test_caixa_de_cerveja_vira_preco_da_garrafa(self):
        c = self.Importar._casar_insumo("Cerveja Brahma 600ml cx c/24", None, "")
        self.assertEqual((c["produto"], c["certeza"], c["fator"]), (self.cerveja, "alta", 24.0))

    def test_long_neck_nao_vira_cerveja_600(self):
        c = self.Importar._casar_insumo("Cerveja Heineken Long Neck 330ml", None, "")
        self.assertEqual(c["produto"], self.long_neck)

    def test_prato_nunca_e_candidato(self):
        c = self.Importar._casar_insumo("Cebola kg", None, "kg")
        self.assertEqual((c["produto"], c["certeza"]), (self.cebola, "alta"))
        self.assertNotIn(self.prato, self.Importar._insumos_candidatos())

    def test_parecido_so_sugere(self):
        c = self.Importar._casar_insumo("Cebola roxa especial", None, "")
        self.assertEqual(c["produto"], self.cebola)
        # Sem dizer se é por kg (o insumo é em kg): sugere, mas confere antes de gravar
        self.assertEqual(c["certeza"], "media")
        self.assertEqual(self.Importar._casar_insumo("Cebola roxa especial", None, "kg")["certeza"], "alta")
        c = self.Importar._casar_insumo("Cerveja Brahma", None, "")
        self.assertIn(c["certeza"], ("media", ""))  # sem tamanho e sem embalagem: confere antes de gravar
