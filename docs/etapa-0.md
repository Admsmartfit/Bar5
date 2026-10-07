# Etapa 0 – Fundação

## O que é nativo e o que foi programado

| Item | Como foi feito |
| --- | --- |
| Odoo Community 18 + PostgreSQL 16 | Imagem oficial `odoo:18`, `docker-compose.yml`, Nginx com HTTPS na frente |
| pt_BR, fuso de São Paulo, real, `l10n_br` | `instalar.sh` em 3 fases: cria o banco, marca a empresa como brasileira e só então instala a contabilidade (assim o Odoo carrega o plano de contas `br`) |
| Empresas e armazéns | `scripts/configurar_empresa.py`: `EMPRESA_MODO=uma` (um CNPJ, armazéns Bar e Cozinha Central) ou `duas` (duas empresas) |
| PDV de restaurante com plantas | Mesmo script: "Salão" (mesas 1–14) e "Área aberta" (15–20), 4 lugares cada |
| Perfis, menus, tela inicial | `boteco_base`: grupo por perfil, menus visíveis por perfil, ação inicial `/boteco/inicio` que leva cada um à sua tela |
| Login por PIN | `boteco_base`: PIN de 4 a 6 dígitos com hash pbkdf2, único por pessoa, sem sequências fáceis, bloqueio por 15 min após 5 erros, só na rede do sistema. O dono entra com senha. |
| Auditoria | `boteco.auditoria`: gravada por todas as ações sensíveis; o ORM recusa alterar/apagar e um gatilho no PostgreSQL bloqueia UPDATE/DELETE |
| Impressão | Servidor envia ESC/POS pela rede (porta 9100), funciona com Epson ePOS e com outras marcas (o "serviço de impressão" previsto no PRD já vem pronto) |
| Saúde | `/boteco/saude`: banco, impressoras, disco do sistema e do backup, último backup, fila de impressão |

OCA: os repositórios OCA/pos e OCA/l10n-brazil (18.0) **não foram baixados nem avaliados** nesta
implementação; tudo foi escrito do zero sobre o Odoo nativo. Antes da próxima revisão vale comparar
com OCA/pos (fechamento cego, restrição de usuário por PDV) e OCA/l10n-brazil (`l10n_br_fiscal`), como
pede a regra 7 do PRD. A pasta `oca/` já está montada no Odoo para receber módulos LGPL aprovados.

## Critérios de aceite

| Critério | Como verificar | Situação |
| --- | --- | --- |
| `./instalar.sh` deixa o sistema em `http://boteco.local` em até 10 min | Rodar num mini PC limpo. No ambiente de desenvolvimento levou **2 min 40 s**. | ✔ (falta confirmar no mini PC real) |
| Garçom entra com PIN e vê só o que o perfil permite | Teste `test_garcom_ve_so_os_menus_do_perfil`; manual: `/boteco/pin` → Ana → 2580 → cai no PDV | ✔ |
| Alterar um preço grava quem, quando, valor antigo e novo | Teste `test_alterar_preco_grava_quem_quando_antes_depois`; manual: mudar o preço e ver Boteco › Gestão › Auditoria | ✔ |
| "Imprimir teste" imprime numa térmica 80 mm pela rede | Teste com impressora simulada (`test_imprimir_teste_numa_impressora_de_rede`). Manual: Boteco › Gestão › Impressoras › Imprimir teste | **Pendente: testar com a impressora real** (PRD pede antes de comprar as demais) |

## Teste com a impressora real (preencher)

| Data | Modelo | IP | Teste | Acentos | QR | Corte | Observação |
| --- | --- | --- | --- | --- | --- | --- | --- |
| | | | | | | | |

## Lista da seção 4 (facilidade de uso)

- Tela de PIN: um toque no nome, PIN, "Entrar" (3 toques). Botões de 80 px, modo escuro, erros dizem o que fazer ("PIN errado. Restam 4 tentativas.").
- Cadastro de pessoas: nome, usuário, perfil e PIN numa tela só; permissões por perfil numa tabela de chaves liga/desliga.
- Botão "?" (ajuda do perfil) e "Trocar de pessoa" na barra superior.
