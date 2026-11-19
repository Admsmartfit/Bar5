{
    "name": "Boteco – Escala de turnos e ponto pelo PIN",
    "version": "18.0.1.0.0",
    "category": "Human Resources",
    "summary": "Escala sugerida pelo movimento, custo de pessoal, troca de turno com aprovação e ponto pelo PIN (hr_attendance)",
    "description": """
Etapa 29 (PRD de recursos avançados), sem módulo pago (Planning é pago; hr_attendance é gratuito):

* Previsão de clientes e faturamento por dia e turno (últimas 4 semanas do caixa), com ajuste de feriado/jogo/show.
* Regras de cobertura por perfil (clientes por garçom, por chapeiro…) -> sugestão de pessoas por turno.
* Escala da semana com custo e % do faturamento; alertas antes de publicar (sem folga, horas demais, turno descoberto).
* "Minha escala" para cada pessoa, link pelo WhatsApp; troca de turno só com aprovação do gerente.
* Ponto pelo PIN no tablet da entrada (opcional: só na rede do bar); relatório escalado x trabalhado e CSV para a folha.
""",
    "author": "Boteco Raiz",
    "license": "LGPL-3",
    "depends": ["boteco_painel", "hr_attendance"],
    "data": [
        "security/ir.model.access.csv",
        "security/grupos.xml",
        "data/escala_data.xml",
        "views/escala_views.xml",
        "views/ponto_templates.xml",
        "data/boteco_ajuda_artigos.xml",
    ],
    "installable": True,
}
