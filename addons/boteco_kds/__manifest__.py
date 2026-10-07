{
    "name": "Boteco – Tela de produção (KDS) e impressão",
    "summary": "Pedido chega sozinho ao bar e à chapa: ticket impresso, tela com cronômetro, alerta de atraso",
    "description": """
Etapa 3 do PRD: produção no bar e na chapa.

* Roteamento por setor (bar, chapa...): cada item vai para a impressora e a tela do seu setor.
* Ticket grande e legível: mesa, hora, itens, adicionais, observação em destaque, origem.
* Fila de impressão no servidor: se a impressora cair, os tickets esperam e saem quando ela
  voltar, com aviso na tela e na página de saúde.
* Tela de produção (KDS) em OWL, inspirada no Mosaic do URY (código escrito do zero):
  cartões por pedido, toque para "preparando" e "pronto", som ao chegar, cronômetro,
  cor pelo tempo (verde até 10 min, amarelo até 20, vermelho acima) e alerta ao gerente
  acima de 30 minutos. Funciona só com toque (sem teclado e sem mouse).
* Aviso ao garçom quando o item fica pronto e tela de "prontos para entregar".
* Relatório de tempos médios por produto e por hora da noite.
""",
    "version": "18.0.1.0.0",
    "category": "Boteco",
    "author": "Boteco Raiz",
    "license": "LGPL-3",
    "depends": ["boteco_pos"],
    "data": [
        "security/ir.model.access.csv",
        "security/boteco_kds_security.xml",
        "data/ir_cron_data.xml",
        "views/boteco_kds_views.xml",
        "views/boteco_impressao_job_views.xml",
        "views/boteco_kds_tempo_views.xml",
        "views/menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "boteco_kds/static/src/kds/**/*",
        ],
        "point_of_sale._assets_pos": [
            "boteco_kds/static/src/pos/**/*",
        ],
    },
    "installable": True,
}
