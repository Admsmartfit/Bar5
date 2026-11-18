{
    "name": "Boteco – Base",
    "summary": "Perfis simplificados, login por PIN, auditoria, impressoras e saúde do sistema",
    "description": """
Fundação do Sistema Boteco Raiz (Etapa 0 do PRD).

* Perfis do boteco (garçom, caixa, chapeiro, gerente, cozinheiro, comercial, dono)
  como grupos do Odoo, com tela de liga/desliga de permissões e menus visíveis.
* Login por PIN (4 a 6 dígitos, guardado com hash, bloqueio após 5 tentativas).
* Autorização na hora com PIN do gerente para ações sensíveis.
* Registro de auditoria imutável (nem o banco deixa alterar ou apagar).
* Impressoras de rede ESC/POS (80 mm) com botão "Imprimir teste".
* Página de saúde: banco, impressoras, disco e último backup.
* Termos em linguagem de boteco nos menus de operação.
""",
    "version": "18.0.1.0.0",
    "category": "Boteco",
    "author": "Boteco Raiz",
    "license": "LGPL-3",
    "depends": [
        "base",
        "web",
        "bus",
        "mail",
        "point_of_sale",
        "pos_restaurant",
        "pos_self_order",
        "stock",
        "purchase",
        "mrp",
        "sale_management",
        "account",
    ],
    "data": [
        "security/boteco_security.xml",
        "security/ir.model.access.csv",
        "data/boteco_setor_data.xml",
        "data/boteco_perfil_data.xml",
        "data/boteco_termo_data.xml",
        "data/ir_cron_data.xml",
        "views/boteco_perfil_views.xml",
        "views/res_users_views.xml",
        "views/boteco_auditoria_views.xml",
        "views/boteco_impressora_views.xml",
        "views/boteco_setor_views.xml",
        "views/boteco_termo_views.xml",
        "views/res_company_views.xml",
        "views/boteco_atualizacao_views.xml",
        "views/stock_warehouse_views.xml",
        "views/pin_templates.xml",
        "views/saude_templates.xml",
        "views/ajuda_templates.xml",
        "views/menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "boteco_base/static/src/css/boteco_backend.scss",
            "boteco_base/static/src/js/botao_ajuda.js",
            "boteco_base/static/src/js/botao_ajuda.xml",
            "boteco_base/static/src/css/boteco_aparencia.scss",
            "boteco_base/static/src/js/aparencia.js",
            "boteco_base/static/src/js/aparencia.xml",
        ],
        "boteco_base.assets_pin": [
            "boteco_base/static/src/css/boteco_tokens.css",
            "boteco_base/static/src/pin/pin.css",
            "boteco_base/static/src/pin/pin.js",
        ],
    },
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": True,
}
