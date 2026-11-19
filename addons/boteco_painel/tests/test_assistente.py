from unittest.mock import patch

import requests

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

from odoo.addons.boteco_base.models.boteco_assistente import login_de


class Resposta:
    def __init__(self, status, corpo):
        self.status_code = status
        self._corpo = corpo

    def json(self):
        return self._corpo


@tagged("post_install", "-at_install", "boteco")
class TestAssistente(TransactionCase):
    """Onboarding em 5 etapas (PRD 19/11/2026)."""

    def setUp(self):
        super().setUp()
        self.Impl = self.env["boteco.implantacao"]
        self.company = self.env.company

    # Etapa 1 ---------------------------------------------------------------
    def test_busca_cnpj_preenche_e_falha_sem_travar(self):
        corpo = {"razao_social": "BOTECO RAIZ LTDA", "nome_fantasia": "BOTECO RAIZ", "descricao_tipo_de_logradouro": "RUA",
                 "logradouro": "MOREIRA", "numero": "220", "bairro": "INDEPENDENCIA", "cep": "29306-320",
                 "municipio": "CACHOEIRO DE ITAPEMIRIM", "uf": "ES", "ddd_telefone_1": "2835110000"}
        with patch("odoo.addons.boteco_base.models.boteco_assistente.requests.get", return_value=Resposta(200, corpo)):
            r = self.Impl.buscar_cnpj("12.345.678/0001-90")
        self.assertEqual(r["nome"], "Boteco Raiz")
        self.assertEqual(r["cidade"], "Cachoeiro De Itapemirim")
        self.assertEqual(r["rua"], "Rua Moreira, 220")
        # API fora do ar: devolve erro na hora (campos manuais), não trava
        with patch("odoo.addons.boteco_base.models.boteco_assistente.requests.get", side_effect=requests.Timeout()):
            self.assertIn("fora do ar", self.Impl.buscar_cnpj("12345678000190")["erro"])
        self.assertIn("14", self.Impl.buscar_cnpj("123")["erro"])

    def test_salvar_identidade_com_logo_e_fuso(self):
        logo = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        self.Impl.salvar_identidade({"nome": "Boteco Teste", "razao_social": "Boteco Teste Ltda", "cnpj": "12345678000190",
                                     "rua": "Rua A, 1", "cidade": "Cachoeiro", "uf": "ES", "fuso": "America/Sao_Paulo",
                                     "logo": logo})
        self.assertEqual(self.company.name, "Boteco Teste")
        self.assertEqual(self.company.state_id.code, "ES")
        self.assertEqual(self.company.partner_id.tz, "America/Sao_Paulo")
        self.assertTrue(self.company.logo)
        with self.assertRaises(UserError):
            self.Impl.salvar_identidade({"nome": ""})

    # Etapa 2 ---------------------------------------------------------------
    def test_entrevista_esconde_modulos_e_cria_mesas(self):
        menu_cozinha = self.env.ref("boteco_cozinha_central.menu_boteco_cozinha")
        self.env["mrp.bom"].search([("product_tmpl_id.boteco_produzido_cozinha", "=", True)]).unlink()
        antes = self.env["restaurant.table"].search_count([])
        r = self.Impl.salvar_operacao({"atendimento": ["garcom", "balcao"], "producao_lote": False,
                                       "ambientes": [{"nome": "Varanda Teste", "mesas": 4, "lugares": 2}]})
        self.assertFalse(self.company.boteco_flag_autoatendimento_qr)
        self.assertEqual(self.company.boteco_tipo_unidade, "bar")
        self.assertFalse(menu_cozinha.active)
        if self.env["pos.config"].search_count([("module_pos_restaurant", "=", True)]):
            self.assertEqual(r["mesas_criadas"], 4)
            self.assertEqual(self.env["restaurant.table"].search_count([]), antes + 4)
            # Repetir não duplica o ambiente
            self.Impl.salvar_operacao({"atendimento": ["garcom"], "ambientes": [{"nome": "varanda teste", "mesas": 4}]})
            self.assertEqual(self.env["restaurant.table"].search_count([]), antes + 4)
        self.Impl.salvar_operacao({"atendimento": ["qr"], "producao_lote": True, "ambientes": []})
        self.assertTrue(self.company.boteco_flag_autoatendimento_qr)
        self.assertTrue(menu_cozinha.active)

    # Etapas 3 a 5 ----------------------------------------------------------
    def test_cardapio_cria_categorias_basicas(self):
        self.Impl.preparar_cardapio()
        nomes = self.env["pos.category"].search([]).mapped("name")
        for nome in ("Bebidas", "Porções", "Sobremesas"):
            self.assertIn(nome, nomes)

    def test_impressora_ip_invalido_e_rota_do_setor(self):
        setor = self.env["boteco.setor"].search([], limit=1)
        with self.assertRaises(UserError):
            self.Impl.salvar_impressora(setor.id, "não é ip")
        with patch("odoo.addons.boteco_base.tools.escpos.testar_conexao", return_value=False):
            self.Impl.salvar_impressora(setor.id, "10.255.255.1")
        self.assertEqual(setor.impressora_id.ip, "10.255.255.1")

    def test_equipe_com_pin_e_erros_por_linha(self):
        r = self.Impl.criar_equipe([{"nome": "Maria Gerente", "perfil": "gerente", "pin": "4829"},
                                    {"nome": "João Garçom", "perfil": "garcom", "pin": "1111"}])  # PIN fácil demais
        maria = self.env["res.users"].search([("login", "=", login_de("Maria Gerente"))])
        self.assertTrue(maria.boteco_tem_pin)
        self.assertEqual(maria.boteco_perfil_id.codigo, "gerente")
        self.assertEqual(len(r["erros"]), 1)
        self.assertEqual(r["erros"][0]["linha"], 1)

    def test_caixa_da_barra_diz_o_proximo_passo(self):
        self.company.write({"boteco_flag_assistente_implantacao": True, "boteco_implantacao_concluida": False})
        r = self.Impl.resumo()
        self.assertTrue(r["mostrar"])
        self.assertIn("proximo", r)

    def test_passo_da_empresa_abre_o_assistente(self):
        acao = self.Impl.acao("empresa_dados")
        self.assertEqual(acao["tag"], "boteco_base.primeiros_passos")
        self.assertFalse(self.company.boteco_assistente_visto)

    def test_caixa_nao_abre_sem_produto_ou_forma_de_pagamento(self):
        config = self.env["pos.config"].create({"name": "Caixa sem pagamento"})
        config.payment_method_ids = [(5, 0, 0)]
        with self.assertRaisesRegex(UserError, "forma de pagamento|item do cardápio"):
            config._check_before_creating_new_session()
