{
    "name": "Boteco – Reserva de mesas",
    "version": "18.0.1.0.0",
    "category": "Sales/Point of Sale",
    "summary": "Página de reserva, reserva no mapa do salão, lembretes, lista de espera, no-show e sinal por Pix",
    "description": """
Etapa 27 (PRD de recursos avançados), sem depender de módulo pago:

* Página pública /reservar (sem login, trava contra robô e limite por aparelho), com a política de tolerância.
* Disponibilidade pelos lugares das mesas e o tempo médio na mesa; junta mesas para grupo grande.
* Reserva aparece no mapa do salão do PDV com o horário; abrir a mesa marca "Chegou" com o nº de pessoas.
* Lembrete na véspera e 3 h antes (link pronto do WhatsApp para quem atende), página para confirmar/cancelar.
* Lista de espera: cancelou, o 1º da lista que cabe recebe a oferta.
* No-show automático depois da tolerância; histórico no cadastro do cliente.
* Sinal por Pix (chave separada) para grupos grandes: QR estático com valor e código da reserva.
""",
    "author": "Boteco Raiz",
    "license": "LGPL-3",
    "depends": ["boteco_pos"],
    "data": [
        "security/ir.model.access.csv",
        "data/ir_cron_data.xml",
        "views/reserva_views.xml",
        "views/central_views.xml",
        "views/reservar_templates.xml",
        "data/boteco_ajuda_artigos.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "boteco_reservas/static/src/pos/**/*",
        ],
    },
    "installable": True,
}
