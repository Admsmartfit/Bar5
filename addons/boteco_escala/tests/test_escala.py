import re
from datetime import datetime, timedelta

import pytz

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import HttpCase, tagged

from odoo.addons.boteco_cardapio.tests.common_pos import BotecoPosCase


@tagged("post_install", "-at_install", "boteco")
class TestEscala(HttpCase, BotecoPosCase):
    """Etapa 29: escala pelo movimento, troca com aprovação e ponto pelo PIN."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.ref("boteco_cardapio.happy_hour_padrao").active = False
        cls.company = cls.env.company
        cls.company.write({"boteco_flag_escala_turnos": True, "boteco_flag_ponto_pin": True,
                           "boteco_ponto_so_na_rede": True, "boteco_hora_virada": 6.0})
        cls.tz = cls.company._boteco_tz()
        cls.noite = cls.env.ref("boteco_escala.turno_noite")

        def pessoa(nome, login, perfil, pin):
            user = cls.env["res.users"].create({"name": nome, "login": login, "password": login + "_123",
                                                "boteco_perfil_id": cls.env.ref("boteco_base.%s" % perfil).id})
            user._boteco_definir_pin(pin)
            return user
        cls.ana = pessoa("Ana Garçom", "ana_esc", "perfil_garcom", "3817")
        cls.bia = pessoa("Bia Garçom", "bia_esc", "perfil_garcom", "5294")
        cls.gerente = pessoa("Gil Gerente", "gil_esc", "perfil_gerente", "7461")
        hoje = fields.Date.today()
        cls.segunda = hoje + timedelta(days=7 - hoje.weekday())  # próxima segunda

    def _local_utc(self, dia, hora):
        return self.tz.localize(datetime.combine(dia, datetime.min.time()) + timedelta(hours=hora)) \
            .astimezone(pytz.utc).replace(tzinfo=None)

    def _venda(self, dia, pessoas):
        dados = self._pedido([self._linha(self.batata, 1)], pagamentos=[(self.pm_dinheiro, 30.0)], pessoas=pessoas,
                             date_order=fields.Datetime.to_string(self._local_utc(dia, 20)))
        return self._sincronizar(dados)

    def _semana(self):
        return self.env["boteco.escala.semana"].create({"inicio": self.segunda})

    # ------------------------------------------------------------------ previsão
    def test_sexta_a_noite_pede_mais_garcons_que_terca(self):
        for semanas in range(1, 5):
            sexta = self.segunda - timedelta(days=7 * semanas - 4)
            terca = self.segunda - timedelta(days=7 * semanas - 1)
            for _ in range(4):
                self._venda(sexta, 25)  # 100 clientes na sexta
            self._venda(terca, 20)  # 20 clientes na terça
        semana = self._semana()
        semana.action_calcular()
        prev = {(p.dia.weekday(), p.turno_id): p for p in semana.previsao_ids}
        sexta, terca = prev[(4, self.noite)], prev[(1, self.noite)]
        self.assertEqual(sexta.clientes, 100)
        self.assertEqual(terca.clientes, 20)
        self.assertEqual(sexta._sugestao()["garcom"], 4)  # 1 garçom a cada 25 clientes
        self.assertEqual(terca._sugestao()["garcom"], 1)
        self.assertGreater(sexta._sugestao()["garcom"], terca._sugestao()["garcom"])

    def test_ajuste_de_jogo_aumenta_a_previsao(self):
        sexta = self.segunda - timedelta(days=3)
        for semanas in range(4):
            self._venda(sexta - timedelta(days=7 * semanas), 40)
        semana = self._semana()
        semana.ajuste_ids = [fields.Command.create({"dia": self.segunda + timedelta(days=4), "ajuste_pct": 50, "motivo": "Jogo"})]
        semana.action_calcular()
        p = semana.previsao_ids.filtered(lambda x: x.dia.weekday() == 4 and x.turno_id == self.noite)
        self.assertEqual(p.clientes, 60)

    # ------------------------------------------------------------------ publicação
    def test_sem_folga_nao_publica_sem_confirmar(self):
        semana = self._semana()
        semana.turno_ids = [fields.Command.create({"user_id": self.ana.id, "dia": self.segunda + timedelta(days=i),
                                                   "turno_id": self.noite.id}) for i in range(7)]
        self.assertIn("sem folga", semana.alertas)
        acao = semana.action_publicar()
        self.assertEqual(acao["res_model"], "boteco.escala.confirmar")
        self.assertEqual(semana.estado, "rascunho")
        self.env["boteco.escala.confirmar"].browse(acao["res_id"]).action_confirmar()
        self.assertEqual(semana.estado, "publicada")
        self.assertEqual(semana.turno_ids[0].perfil, "garcom")
        self.assertEqual(semana.turno_ids[0].horas, 8.0)
        self.assertEqual(semana.turno_ids[0].custo, 112.0)  # 8 h x R$ 14
        self.assertIn("wa.me", semana.turno_ids[0].action_whatsapp()["url"])

    def test_troca_so_vale_depois_da_aprovacao(self):
        semana = self._semana()
        semana.turno_ids = [fields.Command.create({"user_id": self.ana.id, "dia": self.segunda, "turno_id": self.noite.id})]
        semana.with_context(boteco_confirmado=True).action_publicar()
        turno = semana.turno_ids
        troca = self.env["boteco.escala.troca"].with_user(self.ana).create(
            {"turno_id": turno.id, "para_user_id": self.bia.id, "motivo": "Consulta médica"})
        self.assertEqual(turno.user_id, self.ana)
        with self.assertRaises(UserError):
            troca.with_user(self.ana).action_aprovar()
        self.assertEqual(turno.user_id, self.ana)
        troca.with_user(self.gerente).action_aprovar()
        self.assertEqual(turno.user_id, self.bia)
        with self.assertRaises(UserError):  # não dá para pedir troca do turno dos outros
            self.env["boteco.escala.troca"].with_user(self.ana).create({"turno_id": turno.id, "para_user_id": self.ana.id})

    # ------------------------------------------------------------------ ponto
    def test_ponto_fora_da_rede_recusado(self):
        Ponto = self.env["boteco.ponto"]
        with self.assertRaises(UserError):
            Ponto.bater(self.ana, "3817", na_rede=False)
        # Fora da rede da equipe a página nem abre (não lista os nomes)
        self.company.write({"boteco_rede_clientes": "10.99.0.0/24", "boteco_rede_sistema": "10.98.0.0/24"})
        self.env.flush_all()
        pagina = self.url_open("/boteco/ponto")
        self.assertIn("rede do bar", pagina.text)
        self.assertNotIn("Ana Garçom", pagina.text)
        # Na rede da equipe: toca no nome, digita o PIN
        self.company.boteco_rede_sistema = "127.0.0.0/8"
        self.env.flush_all()
        pagina = self.url_open("/boteco/ponto")
        self.assertIn("Ana Garçom", pagina.text)
        csrf = re.search(r'name="csrf_token" value="([^"]+)"', pagina.text).group(1)
        resposta = self.url_open("/boteco/ponto", data={"csrf_token": csrf, "user_id": self.ana.id, "pin": "3817"})
        self.assertIn("entrada às", resposta.text)
        self.company.boteco_ponto_so_na_rede = False
        self.assertEqual(Ponto.bater(self.ana, "3817", na_rede=False)["tipo"], "saida")
        with self.assertRaises(UserError):
            Ponto.bater(self.ana, "0000")

    def test_dobra_no_mesmo_dia_nao_conta_horas_duas_vezes(self):
        """Auditoria: almoço e noite no mesmo dia; entrada atrasada no almoço não cai também na noite."""
        ontem = fields.Date.today() - timedelta(days=1)
        segunda = ontem - timedelta(days=ontem.weekday())
        almoco = self.env.ref("boteco_escala.turno_almoco")
        semana = self.env["boteco.escala.semana"].create({"inicio": segunda})
        semana.turno_ids = [fields.Command.create({"user_id": self.ana.id, "dia": ontem, "turno_id": almoco.id}),
                            fields.Command.create({"user_id": self.ana.id, "dia": ontem, "turno_id": self.noite.id})]
        semana.with_context(boteco_confirmado=True).action_publicar()
        t_almoco = semana.turno_ids.filtered(lambda t: t.turno_id == almoco)
        t_noite = semana.turno_ids.filtered(lambda t: t.turno_id == self.noite)
        funcionario = self.env["boteco.ponto"]._funcionario(self.ana)
        Presenca = self.env["hr.attendance"]
        # Almoço: chegou 2h30 atrasada (13h30) e saiu às 16h; noite: 17h às 1h
        Presenca.create({"employee_id": funcionario.id, "check_in": t_almoco.inicio + timedelta(hours=2, minutes=30),
                         "check_out": t_almoco.fim})
        Presenca.create({"employee_id": funcionario.id, "check_in": t_noite.inicio, "check_out": t_noite.fim})
        relatorio = self.env["boteco.escala.relatorio"].create({"data_de": ontem, "data_ate": ontem})
        relatorio.action_gerar()
        linha_almoco = relatorio.linha_ids.filtered(lambda l: l.turno == almoco.name)
        linha_noite = relatorio.linha_ids.filtered(lambda l: l.turno == self.noite.name)
        self.assertAlmostEqual(linha_almoco.horas_trabalhadas, 2.5, places=2)
        self.assertEqual(linha_almoco.atraso_min, 150)
        self.assertAlmostEqual(linha_noite.horas_trabalhadas, 8.0, places=2)
        self.assertEqual(linha_noite.horas_extras, 0.0)

    def test_escalado_x_trabalhado_mostra_atraso_e_horas_extras(self):
        ontem = fields.Date.today() - timedelta(days=1)
        segunda = ontem - timedelta(days=ontem.weekday())
        semana = self.env["boteco.escala.semana"].create({"inicio": segunda})
        semana.turno_ids = [fields.Command.create({"user_id": self.ana.id, "dia": ontem, "turno_id": self.noite.id}),
                            fields.Command.create({"user_id": self.bia.id, "dia": ontem, "turno_id": self.noite.id})]
        semana.with_context(boteco_confirmado=True).action_publicar()
        turno = semana.turno_ids.filtered(lambda t: t.user_id == self.ana)
        funcionario = self.env["boteco.ponto"]._funcionario(self.ana)
        self.env["hr.attendance"].create({"employee_id": funcionario.id, "check_in": turno.inicio + timedelta(minutes=20),
                                          "check_out": turno.fim + timedelta(minutes=80)})
        relatorio = self.env["boteco.escala.relatorio"].create({"data_de": ontem, "data_ate": ontem})
        relatorio.action_gerar()
        ana = relatorio.linha_ids.filtered(lambda l: l.user_id == self.ana)
        bia = relatorio.linha_ids.filtered(lambda l: l.user_id == self.bia)
        self.assertEqual(ana.atraso_min, 20)
        self.assertAlmostEqual(ana.horas_extras, 1.0, places=2)
        self.assertTrue(bia.faltou)
        self.assertIn("/web/content/", relatorio.action_csv()["url"])

    def test_flag_desligada(self):
        self.company.boteco_flag_escala_turnos = False
        with self.assertRaises(UserError):
            self._semana().action_calcular()
        self.company.boteco_flag_ponto_pin = False
        with self.assertRaises(UserError):
            self.env["boteco.ponto"].bater(self.ana, "3817")
