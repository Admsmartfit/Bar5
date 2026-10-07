# Sistema Boteco Raiz

Sistema do bar, da cozinha central e da venda a outros bares, sobre o **Odoo Community 18**
(imagem oficial `odoo:18`), com módulos próprios `boteco_*`. Especificação completa em
[docs/PRD.md](docs/PRD.md).

## Instalar

Mini PC Linux limpo (Debian/Ubuntu), com o projeto copiado:

```bash
sudo ./instalar.sh
```

Em cerca de 3 minutos o sistema fica em `https://boteco.local` (o `http://` redireciona).
O instalador gera o `.env` com senhas aleatórias, o certificado HTTPS da rede interna, cria o banco
em português com plano de contas brasileiro, instala tudo, configura empresa, armazéns (bar e
cozinha central), PDV de restaurante com 20 mesas e agenda o backup na nuvem.

Antes de usar, edite no `.env`: `EMPRESA_*`, `REDE_CLIENTES`, `REDE_SISTEMA`, `BACKUP_DIR` e
`BACKUP_NUVEM_*`. Para testar ou fazer demonstração: `scripts/dados_exemplo.py` (veja abaixo).

## Endereços

| O quê | Onde |
| --- | --- |
| Entrar com PIN (equipe) | `https://boteco.local/boteco/pin` |
| Entrar com senha (dono) | `https://boteco.local/web/login` |
| Saúde do sistema | `https://boteco.local/boteco/saude` |
| Ajuda por perfil | `https://boteco.local/boteco/ajuda` |
| Modo treinamento | `https://boteco.local:8443` (depois de `./scripts/treinamento.sh`) |

## Comandos do dia a dia

| Comando | Para quê |
| --- | --- |
| `./scripts/atualizar.sh [--git] [--imagem]` | Atualiza com backup antes e volta automática se falhar |
| `./scripts/restaurar.sh [arquivo.dump]` | Restaura um backup (o mais recente se não informar) |
| `docker compose exec backup bash /usr/local/bin/backup-loop.sh --uma-vez` | Backup agora |
| `./scripts/treinamento.sh` / `ligar` / `parar` | Modo treinamento (banco separado) |
| `./scripts/testar.sh [modulos]` | Testes automáticos num banco descartável |
| `docker compose logs -f odoo` | Log ao vivo |

Dados de exemplo (cardápio, equipe com PIN): 

```bash
docker compose run --rm -T odoo odoo shell -c /etc/odoo/odoo.conf -d boteco --no-http < scripts/dados_exemplo.py
```

## Módulos

| Módulo | Etapa | O que faz |
| --- | --- | --- |
| `boteco_base` | 0 | Perfis, PIN com hash e bloqueio, autorização do gerente, auditoria imutável, impressoras, saúde |
| `boteco_cardapio` | 1 | Happy hour, oferta relâmpago, "Acabou", +18, dados fiscais, cadastro rápido, planilha, QR das mesas |
| `boteco_pos` | 2 | Couvert, taxa de serviço, cancelamento/desconto/cortesia com PIN, consumo de funcionário, contagem cega |
| `boteco_kds` | 3 | Tela de produção, fila de impressão que não perde ticket, alertas de atraso, prontos para entregar |
| `boteco_autoatendimento` | 4 | Tablet e QR: liberação do celular, rede do bar, +18, chamar garçom, pedir a conta, minha conta |
| `boteco_estoque` | 5 | CMV, XML da NF-e do fornecedor, lista de compras por WhatsApp, contagem pelo celular, perdas |
| `boteco_cozinha_central` | 6 | Produção com 3 botões, lote e etiqueta ZPL, FEFO, bloqueio de vencido, temperatura, rastreio |
| `boteco_b2b` | 7 | Venda por kg a outros bares, pedido recorrente, romaneio, contratos de assessoria |
| `boteco_painel` | 8 | Painel do dono, DRE por frente, fechamento do dia, fluxo de caixa |
| `boteco_fiscal_export` | 9 | Controle fiscal para emissão posterior: pendentes, exportação em lotes, retorno |
| `boteco_treinamento` | 10 | Só no banco de treino: faixa vermelha e impressão simulada |

Regra de ouro do projeto: **o código do Odoo nunca é alterado**; tudo está em `addons/`.

## Testes

```bash
./scripts/testar.sh                      # todos (104 testes)
./scripts/testar.sh boteco_base          # um módulo
node scripts/dev/verificar_telas.mjs https://localhost admin SENHA /pos/ui?config_id=1   # telas no Chrome headless
```

Documentação de cada etapa (o que é nativo, o que foi programado e como verificar cada critério de
aceite): [docs/etapa-0.md](docs/etapa-0.md) a [docs/etapa-10.md](docs/etapa-10.md).
