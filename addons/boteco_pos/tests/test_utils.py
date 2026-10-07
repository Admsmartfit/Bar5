from odoo.tests import BaseCase, tagged

from ..models.utils import cnpj_valido, cpf_valido, dividir_em_partes, ler_snapshot


@tagged("post_install", "-at_install", "boteco")
class TestUtils(BaseCase):
    def test_dividir_em_partes_soma_exata(self):
        self.assertEqual(dividir_em_partes(100, 3), [33.34, 33.33, 33.33])
        self.assertEqual(dividir_em_partes(90.2, 4), [22.55, 22.55, 22.55, 22.55])
        for total in (0.01, 17.99, 123.45, 1000):
            for n in range(1, 9):
                partes = dividir_em_partes(total, n)
                self.assertEqual(len(partes), n)
                self.assertAlmostEqual(sum(partes), total, places=2)

    def test_documentos(self):
        self.assertTrue(cpf_valido("529.982.247-25"))
        self.assertFalse(cpf_valido("111.111.111-11"))
        self.assertFalse(cpf_valido("529.982.247-24"))
        self.assertTrue(cnpj_valido("11.222.333/0001-81"))
        self.assertFalse(cnpj_valido("11.222.333/0001-80"))

    def test_ler_snapshot(self):
        texto = '{"lines": {"u1 - ": {"uuid": "u1", "product_id": 5, "quantity": 2, "note": "sem gelo"}}}'
        self.assertEqual(ler_snapshot(texto)["u1"]["qtd"], 2)
        self.assertEqual(ler_snapshot(texto)["u1"]["nota"], "sem gelo")
        self.assertEqual(ler_snapshot("lixo"), {})
