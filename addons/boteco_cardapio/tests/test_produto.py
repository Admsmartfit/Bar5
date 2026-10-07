import base64
import io

from PIL import Image

from odoo.exceptions import ValidationError
from odoo.tests import Form, TransactionCase, tagged


def imagem_b64(largura, altura):
    saida = io.BytesIO()
    Image.new("RGB", (largura, altura), (200, 50, 50)).save(saida, format="PNG")
    return base64.b64encode(saida.getvalue())


@tagged("post_install", "-at_install", "boteco")
class TestProdutoCardapio(TransactionCase):
    def test_dados_fiscais_e_relatorio_de_pendencias(self):
        """Critério de aceite: relatório 'Produtos sem dados fiscais' lista todos os pendentes."""
        sem = self.env["product.template"].create({"name": "Caipirinha", "list_price": 18})
        com = self.env["product.template"].create({
            "name": "Água", "list_price": 5, "boteco_ncm": "22011000", "boteco_cfop": "5.102",
            "boteco_cst_csosn": "102", "boteco_origem": "0",
        })
        self.assertFalse(sem.boteco_fiscal_ok)
        self.assertIn("sem NCM", sem.boteco_fiscal_pendencias)
        self.assertTrue(com.boteco_fiscal_ok)
        self.assertEqual(com.boteco_ncm, "2201.10.00")
        self.assertEqual(com.boteco_cfop, "5102")
        acao = self.env.ref("boteco_cardapio.action_boteco_produtos_sem_fiscal")
        pendentes = self.env["product.template"].search(eval(acao.domain))  # noqa: S307 — domínio fixo do módulo
        self.assertIn(sem, pendentes)
        self.assertNotIn(com, pendentes)
        with self.assertRaises(ValidationError):
            com.boteco_ncm = "123"

    def test_padrao_fiscal_da_categoria(self):
        categoria = self.env["product.category"].create({
            "name": "Cervejas", "boteco_ncm_padrao": "2203.00.00", "boteco_cfop_padrao": "5405",
            "boteco_cst_csosn_padrao": "500", "boteco_maior_18_padrao": True,
        })
        produto = self.env["product.template"].create({"name": "Long neck", "categ_id": categoria.id})
        self.assertEqual(produto.boteco_ncm, "2203.00.00")
        self.assertTrue(produto.boteco_maior_18)
        self.assertTrue(produto.boteco_fiscal_ok)

    def test_acabou_tira_do_tablet_sem_apagar(self):
        produto = self.env["product.template"].create({"name": "Pastel", "available_in_pos": True})
        self.assertTrue(produto.self_order_available)
        produto.action_boteco_acabou()
        self.assertTrue(produto.boteco_esgotado)
        self.assertFalse(produto.self_order_available)
        self.assertTrue(produto.active)
        self.assertTrue(produto.boteco_esgotado_em)
        produto.action_boteco_voltou()
        self.assertTrue(produto.self_order_available)
        self.assertFalse(produto.boteco_esgotado_em)

    def test_foto_recortada_em_quadrado(self):
        produto = self.env["product.template"].create({"name": "Torresmo", "image_1920": imagem_b64(800, 400)})
        img = Image.open(io.BytesIO(base64.b64decode(produto.image_1920)))
        self.assertEqual(img.size[0], img.size[1])

    def test_cadastro_rapido_numa_tela(self):
        """Tela de cadastro rápido: tudo numa tela, poucos campos obrigatórios."""
        vista = self.env.ref("boteco_cardapio.product_template_view_form_rapido")
        with Form(self.env["product.template"], view=vista) as f:
            f.name = "Porção de calabresa"
            f.list_price = 38
            f.boteco_setor_id = self.env.ref("boteco_base.setor_chapa")
        self.assertEqual(f.record.boteco_setor_id.codigo, "chapa")

    def test_planilha_exportar_e_importar(self):
        self.env["product.template"].create({"name": "Chope teste", "list_price": 12, "available_in_pos": True,
                                             "default_code": "CHP1", "boteco_preco_happy": 8})
        assistente = self.env["boteco.cardapio.planilha"].create({})
        assistente.action_exportar()
        self.assertTrue(assistente.arquivo)
        # Reimporta a mesma planilha: atualiza sem duplicar
        importar = self.env["boteco.cardapio.planilha"].create({"arquivo": assistente.arquivo})
        importar.action_importar()
        self.assertIn("0 itens criados", importar.resultado)
        self.assertEqual(self.env["product.template"].search_count([("default_code", "=", "CHP1")]), 1)

    def test_preco_happy_auditado(self):
        produto = self.env["product.template"].create({"name": "Gin tônica", "list_price": 25})
        produto.boteco_preco_happy = 19.9
        self.assertTrue(self.env["boteco.auditoria"].search([
            ("acao", "=", "alteracao_preco"), ("res_id", "=", produto.id), ("valor_novo", "=", "19.90")
        ]))
