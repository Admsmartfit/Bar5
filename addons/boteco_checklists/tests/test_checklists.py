import base64
import re
from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import HttpCase, tagged

FOTO = base64.b64encode(base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="))


@tagged("post_install", "-at_install", "boteco")
class TestChecklists(HttpCase):
    """Etapa 30: checklists APPCC com PIN e manutenção preventiva."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.write({"boteco_flag_checklists_appcc": True, "boteco_flag_manutencao_preventiva": True})
        cls.env["boteco.checklist.modelo"].search([]).write({"active": False})
        cls.modelo = cls.env["boteco.checklist.modelo"].create({
            "name": "Fechamento teste", "frequencia": "diaria", "hora_limite": 23.9,
            "grupo_id": cls.env.ref("boteco_base.group_chapeiro").id,
            "item_ids": [
                fields.Command.create({"name": "Gás fechado", "tipo": "simnao", "critico": True}),
                fields.Command.create({"name": "Freezer", "tipo": "numero", "minimo": -25, "maximo": -18, "critico": True}),
                fields.Command.create({"name": "Foto da cozinha", "tipo": "foto"}),
            ]})
        cls.gas, cls.freezer, cls.foto = cls.modelo.item_ids
        cls.chapeiro = cls.env["res.users"].create({
            "name": "Chapeiro Teste", "login": "chapeiro_ck", "password": "chapeiro_ck_123",
            "groups_id": [fields.Command.set([cls.env.ref("base.group_user").id, cls.env.ref("boteco_base.group_chapeiro").id])]})
        cls.chapeiro._boteco_definir_pin("4826")
        cls.gerente = cls.env["res.users"].create({
            "name": "Gerente Teste", "login": "gerente_ck",
            "groups_id": [fields.Command.set([cls.env.ref("base.group_user").id, cls.env.ref("boteco_base.group_gerente").id])]})
        cls.Execucao = cls.env["boteco.checklist.execucao"]

    def _hoje(self):
        self.Execucao._cron_gerar()
        return self.Execucao.search([("modelo_id", "=", self.modelo.id)], order="id desc", limit=1)

    def _respostas(self, gas=True, temp=-20, foto=True):
        return {str(self.gas.id): {"valor_bool": gas}, str(self.freezer.id): {"valor_num": temp},
                str(self.foto.id): {"foto": FOTO if foto else False}}

    def test_cria_o_checklist_do_dia_uma_vez(self):
        e = self._hoje()
        self.Execucao._cron_gerar()
        self.assertEqual(self.Execucao.search_count([("modelo_id", "=", self.modelo.id)]), 1)
        self.assertIn(e, self.Execucao.with_user(self.chapeiro).pendentes_para(self.chapeiro))

    def test_assina_com_pin_e_tudo_conforme(self):
        e = self._hoje()
        with self.assertRaises(UserError):
            e.finalizar(self._respostas(), "0000", user=self.chapeiro)
        e.finalizar(self._respostas(), "4826", user=self.chapeiro)
        self.assertEqual(e.estado, "feito")
        self.assertEqual(e.assinado_por_id, self.chapeiro)
        self.assertEqual(e.n_nao_conformes, 0)
        self.assertFalse(self.env["boteco.nao.conformidade"].search([("execucao_id", "=", e.id)]))

    def test_falta_foto_nao_assina(self):
        e = self._hoje()
        with self.assertRaises(UserError):
            e.finalizar(self._respostas(foto=False), "4826", user=self.chapeiro)
        self.assertEqual(e.estado, "pendente")

    def test_temperatura_fora_da_faixa_no_item_critico_abre_nc_e_avisa(self):
        e = self._hoje()
        e.finalizar(self._respostas(temp=-10), "4826", user=self.chapeiro)
        nc = self.env["boteco.nao.conformidade"].search([("execucao_id", "=", e.id)])
        self.assertEqual(len(nc), 1)
        self.assertTrue(nc.critica)
        self.assertIn("-10", nc.descricao)
        self.assertIn(self.gerente, nc.activity_ids.user_id)
        with self.assertRaises(UserError):
            nc.action_resolver()  # sem dizer o que foi feito
        nc.acao = "Freezer regulado e produtos remanejados"
        nc.action_resolver()
        self.assertEqual(nc.estado, "resolvida")
        self.assertFalse(nc.activity_ids)

    def test_atrasado_fica_vermelho_no_painel(self):
        e = self._hoje()
        e.hora_limite = fields.Datetime.now() - timedelta(minutes=5)
        self.assertTrue(e.atrasado)
        alertas = self.env["boteco.painel"]._alertas_extras(self.company)
        self.assertTrue(any("Checklist atrasado: Fechamento teste" in a for a in alertas))

    def test_tela_do_celular_assina(self):
        e = self._hoje()
        self.authenticate("chapeiro_ck", "chapeiro_ck_123")
        pagina = self.url_open("/boteco/checklist")
        self.assertIn("Fechamento teste", pagina.text)
        pagina = self.url_open("/boteco/checklist/%s" % e.id)
        csrf = re.search(r'name="csrf_token" value="([^"]+)"', pagina.text).group(1)
        resposta = self.url_open("/boteco/checklist/%s" % e.id, data={
            "csrf_token": csrf, "item_%s" % self.gas.id: "sim", "item_%s" % self.freezer.id: "-19", "pin": "4826"},
            files={"item_%s_foto" % self.foto.id: ("cozinha.png", base64.b64decode(FOTO), "image/png")})
        self.assertIn("Checklist assinado", resposta.text)
        e.invalidate_recordset()
        self.assertEqual(e.estado, "feito")
        self.assertTrue(e.resposta_ids.filtered(lambda r: r.item_id == self.foto).foto)

    def test_relatorio_pdf(self):
        e = self._hoje()
        e.finalizar(self._respostas(), "4826", user=self.chapeiro)
        html = self.env["ir.actions.report"]._render_qweb_html("boteco_checklists.report_checklists", e.ids)[0]
        self.assertIn(b"Chapeiro Teste", html)
        acao = self.env["boteco.checklist.relatorio"].create({}).action_imprimir()
        # Na 1ª vez o Odoo pede o layout dos documentos (act_window); depois, o PDF
        self.assertIn(acao.get("type"), ("ir.actions.report", "ir.actions.client", "ir.actions.act_window"))

    def test_manutencao_preventiva_avisa_antes_e_quando_vence(self):
        self.env["maintenance.equipment"]._boteco_criar_planos()
        chopeira = self.env["maintenance.request"].search([("name", "=", "Limpeza da chopeira e das linhas")])
        self.assertTrue(chopeira.recurring_maintenance)
        self.assertEqual((chopeira.repeat_interval, chopeira.repeat_unit), (7, "day"))
        chopeira.schedule_date = fields.Datetime.now() - timedelta(days=1)
        alertas = self.env["boteco.painel"]._alertas_extras(self.company)
        self.assertTrue(any("Manutenção vencida: Limpeza da chopeira" in a for a in alertas))
        self.company.boteco_flag_manutencao_preventiva = False
        alertas = self.env["boteco.painel"]._alertas_extras(self.company)
        self.assertFalse(any("Manutenção" in a for a in alertas))

    def test_flag_desligada_nao_cria(self):
        self.company.boteco_flag_checklists_appcc = False
        self.Execucao._cron_gerar()
        self.assertFalse(self.Execucao.search([("modelo_id", "=", self.modelo.id)]))
