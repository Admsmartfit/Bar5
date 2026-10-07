# Etapa 10 – Implantação, backup e treinamento

## Backup

- **Local, a cada hora** (serviço `backup` do Docker): banco (`pg_dump`) + arquivos (fotos, anexos)
  em `BACKUP_DIR` (segundo disco), guardando 30 dias. A página `/boteco/saude` mostra o último.
- **Nuvem, todo dia às 07:30** (`scripts/backup-nuvem.sh`, agendado pelo instalador): pacote
  criptografado com GPG (AES256, senha `BACKUP_NUVEM_SENHA`) enviado pelo `rclone`. Configure uma vez
  com `rclone config` e preencha `BACKUP_NUVEM_DESTINO`.
- **Restaurar:** `./scripts/restaurar.sh [arquivo.dump]`. No desenvolvimento a restauração levou
  **14 segundos**. Teste mensal sem mexer no sistema: `BANCO=boteco_teste ./scripts/restaurar.sh`.

## Atualizar

`./scripts/atualizar.sh [--git] [--imagem]`: faz backup, atualiza os módulos e, se der erro,
restaura o backup sozinho e sobe o sistema como estava.

## Modo treinamento

`./scripts/treinamento.sh` copia o banco real para `boteco_treino` e sobe em
`https://boteco.local:8443` com faixa vermelha "MODO TREINAMENTO", impressão simulada e sem alertas
ou cobranças. Mesmos usuários e PINs. `./scripts/treinamento.sh parar` desliga.

## VPN e acesso remoto

Veja [vpn.md](vpn.md) (WireGuard: cozinha central e celular do dono).

## Carga inicial

Cardápio pela planilha (Cardápio › Importar/exportar), insumos e fichas técnicas, mesas (já
criadas), pessoas com perfil e PIN (Boteco › Configuração › Pessoas), impressoras e setores.
`scripts/dados_exemplo.py` mostra o formato com 14 itens e 7 pessoas.

## Guias e contingência

- Guia de uma página por perfil: `https://boteco.local/boteco/ajuda` (botão "Imprimir").
- Plano de contingência impresso: [contingencia.md](contingencia.md).

## Critérios de aceite

| Critério | Situação |
| --- | --- |
| Restaurar o backup de ontem num PC limpo em menos de 30 min | Instalação (≈3 min) + restauração (14 s no dev). **Pendente: ensaio num PC limpo.** |
| Cada funcionário faz sua tarefa principal no treinamento sem ajuda | **Pendente: sessão com a equipe** no modo treinamento |
| Desligar o servidor na noite de teste e seguir o plano não perde vendas | **Pendente: noite de teste com amigos** (registrar problemas abaixo) |

## Noite de teste – relatório de problemas

| Hora | Quem | O que aconteceu | Gravidade | Corrigido em |
| --- | --- | --- | --- | --- |
| | | | | |
