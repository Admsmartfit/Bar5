import re
from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import HttpCase, tagged

from odoo.addons.boteco_cardapio.tests.common_pos import BotecoPosCase
from odoo.addons.boteco_reservas.models.boteco_reserva import utc_para_local
from odoo.addons.boteco_reservas.models.pix import crc16


@tagged("post_install", "-at_install", "boteco")
class TestReservas(HttpCase, BotecoPosCase):
    """Etapa 27: reserva de mesas, lembretes, lista de espera, no-show e sinal."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.write({"boteco_flag_reservas_mesas": True, "boteco_flag_reserva_sinal": False,
                           "boteco_reserva_faixas": "19:00, 20:00, 21:00", "boteco_reserva_permanencia_min": 120,
                           "boteco_reserva_tolerancia_min": 15, "boteco_reserva_max_pessoas": 30})
        # Só as mesas do salão de teste aceitam reserva
        outras = cls.env["restaurant.table"].search([("id", "not in", cls.mesas.ids)])
        outras.write({"boteco_reservavel": False})
        cls.Reserva = cls.env["boteco.reserva"]
        cls.amanha = utc_para_local(cls.company, fields.Datetime.now()).date() + timedelta(days=1)

    def setUp(self):
        super().setUp()
        self.sessao = self._abrir_sessao()

    def url_open(self, *args, **kwargs):
        # A página roda em outra transação do servidor de teste: grava antes e relê depois
        self.env.flush_all()
        resposta = super().url_open(*args, **kwargs)
        self.env.invalidate_all()
        return resposta

    def _reservar(self, pessoas=4, faixa="20:00", nome="Ana Souza", celular="11988887777"):
        return self.Reserva.boteco_reservar(self.company, {"dia": str(self.amanha), "faixa": faixa, "pessoas": pessoas,
                                                           "nome": nome, "celular": celular}, origem="telefone")

    def _csrf(self, html):
        return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)

    def _direta(self, minutos, pessoas=3):
        """Reserva com hora exata (ex.: daqui a 30 min), como o atendente lança."""
        return self.Reserva.create({"cliente_nome": "Bruno Lima", "celular": "11977776666", "pessoas": pessoas,
                                    "data_hora": fields.Datetime.now() + timedelta(minutes=minutos)})

    # ------------------------------------------------------------------ página pública
    def test_reserva_pela_pagina_publica(self):
        pagina = self.url_open("/reservar?dia=%s&pessoas=4" % self.amanha)
        self.assertEqual(pagina.status_code, 200)
        self.assertIn("20:00", pagina.text)
        self.assertIn("Seguramos a mesa", pagina.text)  # política visível
        resposta = self.url_open("/reservar", data={
            "csrf_token": self._csrf(pagina.text), "dia": str(self.amanha), "pessoas": "4", "faixa": "20:00",
            "nome": "Carla Dias", "celular": "(11) 96666-5555", "observacao": "Aniversário"})
        self.assertIn("/reservar/", resposta.url)
        reserva = self.Reserva.search([("cliente_nome", "=", "Carla Dias")])
        self.assertEqual(reserva.estado, "confirmada")
        self.assertEqual(reserva.origem, "link")
        self.assertEqual(len(reserva.mesa_ids), 1)
        self.assertEqual(reserva.partner_id.mobile, "(11) 96666-5555")
        self.assertIn("Reserva confirmada", resposta.text)

    def test_robo_nao_reserva(self):
        pagina = self.url_open("/reservar?dia=%s&pessoas=2" % self.amanha)
        self.url_open("/reservar", data={"csrf_token": self._csrf(pagina.text), "dia": str(self.amanha), "pessoas": "2",
                                         "faixa": "20:00", "nome": "Robô", "celular": "11911112222", "site": "x"})
        self.assertFalse(self.Reserva.search([("cliente_nome", "=", "Robô")]))

    # ------------------------------------------------------------------ capacidade
    def test_nao_reserva_alem_da_capacidade(self):
        for i in range(6):  # 6 mesas de 4 lugares
            self._reservar(4, nome="Grupo %s" % i, celular="1190000000%s" % i)
        with self.assertRaises(UserError):
            self._reservar(4, nome="Sem lugar")
        disponivel = {f["faixa"]: f["livre"] for f in self.Reserva.boteco_disponibilidade(self.company, self.amanha, 4)}
        self.assertFalse(disponivel["20:00"])
        self.assertFalse(disponivel["21:00"])  # 21h ainda está dentro das 2 h das reservas de 20h

    def test_grupo_grande_junta_mesas(self):
        reserva = self._reservar(10)
        self.assertEqual(len(reserva.mesa_ids), 3)
        self.assertGreaterEqual(sum(reserva.mesa_ids.mapped("seats")), 10)

    # ------------------------------------------------------------------ mapa e chegada
    def test_mapa_do_salao_e_chegou(self):
        reserva = self._direta(30, pessoas=3)
        mapa = self.env["restaurant.table"].boteco_reservas_mapa(self.config.id)
        mesa = reserva.mesa_ids
        self.assertEqual(mapa[str(mesa.id)]["nome"], "Bruno")
        self.assertEqual(mapa[str(mesa.id)]["pessoas"], 3)
        resultado = mesa.boteco_reserva_chegou()
        self.assertEqual(resultado["pessoas"], 3)
        self.assertEqual(reserva.estado, "chegou")
        self.assertEqual(mesa.boteco_clientes_atuais, 3)
        self.assertNotIn(str(mesa.id), self.env["restaurant.table"].boteco_reservas_mapa(self.config.id))

    # ------------------------------------------------------------------ lembretes, cancelamento, no-show
    def test_lembrete_da_vespera(self):
        reserva = self._direta(24 * 60)
        self.Reserva._cron_lembretes()
        self.assertEqual(reserva.lembrete_pendente, "d1")
        acao = reserva.action_abrir_whatsapp()
        self.assertIn("wa.me/5511977776666", acao["url"])
        self.assertIn(reserva.token, acao["url"])
        self.assertTrue(reserva.lembrete_d1_feito)
        self.assertFalse(reserva.lembrete_pendente)

    def test_cancelar_pelo_link_oferece_vaga_na_lista_de_espera(self):
        reserva = self._reservar(4)
        espera = self.env["boteco.reserva.espera"].create({"nome": "Dani", "celular": "11955554444",
                                                           "dia": self.amanha, "pessoas": 4, "faixa": "20:00"})
        pagina = self.url_open("/reservar/%s" % reserva.token)
        self.assertIn("Preciso cancelar", pagina.text)
        self.url_open("/reservar/%s" % reserva.token, data={"csrf_token": self._csrf(pagina.text), "acao": "cancelar"})
        self.assertEqual(reserva.estado, "cancelada")
        self.assertEqual(espera.estado, "oferecida")
        self.assertEqual(espera.faixa_oferecida, "20:00")
        self.assertIn("wa.me", espera.action_abrir_whatsapp()["url"])

    def test_no_show_depois_da_tolerancia(self):
        atrasada = self._direta(-20)
        no_prazo = self._direta(-10)
        self.Reserva._cron_no_show()
        self.assertEqual(atrasada.estado, "no_show")
        self.assertEqual(no_prazo.estado, "confirmada")
        self.assertEqual(atrasada.partner_id.boteco_no_shows, 1)

    # ------------------------------------------------------------------ sinal
    def test_sinal_por_pix_para_grupo_grande(self):
        self.company.write({"boteco_flag_reserva_sinal": True, "boteco_reserva_sinal_min_pessoas": 10,
                            "boteco_reserva_sinal_por_pessoa": 20.0, "boteco_reserva_pix_chave": "12345678000190"})
        pequena = self._reservar(4)
        self.assertEqual(pequena.estado, "confirmada")
        grande = self._reservar(10, celular="11933332222")
        self.assertEqual(grande.estado, "pendente")
        self.assertEqual(grande.sinal_valor, 200.0)
        pix = self.company._boteco_pix_sinal(grande)
        self.assertTrue(pix.startswith("000201"))
        self.assertIn("540" + "6200.00", pix)
        self.assertEqual(pix[-4:], crc16(pix[:-4]))
        self.assertIn(pix[:20], self.url_open("/reservar/%s" % grande.token).text)
        grande.action_sinal_recebido()
        self.assertEqual(grande.estado, "confirmada")

    # ------------------------------------------------------------------ flag
    def test_flag_desligada(self):
        reserva = self._direta(30)
        self.company.boteco_flag_reservas_mesas = False
        self.assertIn("Reservas indisponíveis", self.url_open("/reservar").text)
        self.assertEqual(self.env["restaurant.table"].boteco_reservas_mapa(self.config.id), {})
        with self.assertRaises(UserError):
            self._reservar(2)
        self.Reserva._cron_no_show()
        self.assertEqual(reserva.estado, "confirmada")
