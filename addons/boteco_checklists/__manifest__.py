{
    "name": "Boteco – Checklists APPCC e manutenção preventiva",
    "version": "18.0.1.0.0",
    "category": "Manufacturing/Maintenance",
    "summary": "Checklists de abertura/fechamento e boas práticas (RDC 216) com foto e PIN; manutenção da chopeira, gás e extintores",
    "description": """
Etapa 30 (PRD de recursos avançados), sem módulo pago:

* Modelos de checklist com itens sim/não, número com faixa (temperatura), foto e texto; item crítico.
* Modelos prontos: abertura do salão, fechamento da cozinha, recebimento, chopeira, controle de pragas.
* Execução pelo celular (/boteco/checklist), assinatura com o PIN; atrasado fica vermelho para o gerente.
* Não conformidade com prazo, aviso imediato no item crítico, lembrada até ser resolvida.
* PDF para a fiscalização (respostas, fotos e quem assinou).
* Manutenção preventiva sobre o 'maintenance' gratuito: planos, aviso antes de vencer e custo.
""",
    "author": "Boteco Raiz",
    "license": "LGPL-3",
    "depends": ["boteco_painel", "maintenance", "mail"],
    "data": [
        "security/ir.model.access.csv",
        "security/grupos.xml",
        "data/ir_cron_data.xml",
        "data/modelos_data.xml",
        "data/manutencao_data.xml",
        "views/relatorio_views.xml",
        "views/checklist_views.xml",
        "views/tela_templates.xml",
        "data/boteco_ajuda_artigos.xml",
    ],
    "installable": True,
}
