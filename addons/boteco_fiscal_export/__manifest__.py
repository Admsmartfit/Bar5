{
    "name": "Boteco – Controle fiscal para emissão posterior",
    "summary": "O sistema não emite nota: guarda tudo o que a nota precisa, marca pendente, exporta em lotes "
    "e importa o retorno (número e chave)",
    "description": """
Etapa 9 do PRD.

* Toda conta fechada no bar gera um registro fiscal pendente do tipo NFC-e; toda entrega B2B gera
  um pendente do tipo NF-e.
* Cortesia total, consumo de funcionário e perda geram "não emitir", com motivo.
* Tela "Fiscal" com filtros por período, tipo e situação; totais pendentes por dia.
* Exportação por período em CSV, Excel e JSON: emitente, data e hora, itens (código, descrição, NCM,
  CFOP, CST/CSOSN, unidade, quantidade, valor unitário, desconto), taxa de serviço, formas de
  pagamento e CPF/CNPJ do cliente.
* Layout de exportação configurável (ordem e nome das colunas) para casar com o sistema emissor.
* Cada exportação vira um lote numerado; registro exportado não sai de novo sem pedido explícito.
* Importação do retorno (planilha com número e chave) marca cada registro como emitido.
* Bloqueio da exportação se algum item não tem NCM ou CFOP, com a lista do que corrigir.
* Pendências há mais de X dias aparecem como alerta no painel do dono.
""",
    "version": "18.0.1.0.0",
    "category": "Boteco",
    "author": "Boteco Raiz",
    "license": "LGPL-3",
    "depends": ["boteco_painel", "boteco_b2b"],
    "data": [
        "security/ir.model.access.csv",
        "data/fiscal_data.xml",
        "views/boteco_fiscal_registro_views.xml",
        "views/boteco_fiscal_layout_views.xml",
        "wizard/boteco_fiscal_exportacao_views.xml",
        "wizard/boteco_fiscal_retorno_views.xml",
        "views/res_company_views.xml",
        "views/menus.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
}
