# Atualização do sistema pela tela

Fluxo: desenvolver aqui → `git push` para o GitHub → no servidor, **Boteco → Configuração → Atualizar sistema → Atualizar agora**.

## Como funciona

O Odoo roda dentro do Docker e não pode se atualizar sozinho (teria que se parar e reiniciar).
Por isso são duas partes:

| Parte | Onde roda | O que faz |
| :--- | :--- | :--- |
| Tela "Atualizar sistema" (`boteco.atualizacao`) | Odoo | Mostra a versão instalada, as versões novas do GitHub e o resultado da última atualização. Grava o pedido em `atualizacao/pedido.txt`. Só o dono pode atualizar e todo pedido fica na auditoria. |
| Agente (`scripts/agente_atualizacao.sh`) | Servidor Linux, via systemd | `boteco-atualizacao.path` percebe o pedido e roda `scripts/atualizar.sh --git`: backup → `git pull` → reconstrói a imagem → atualiza os módulos → sobe o Odoo. Se algo falhar, **volta o código e o banco** para como estavam. `boteco-atualizacao-verificar.timer` procura versões novas a cada 3 horas. |

A pasta `atualizacao/` (fora do Git) é a única coisa compartilhada entre os dois.

## Preparar o servidor (uma vez)

1. Clonar o repositório no servidor e rodar `sudo ./instalar.sh` (instala os serviços do systemd).
2. Se o repositório no GitHub for **privado**, o servidor precisa de acesso de leitura. O mais seguro é uma
   *deploy key* só de leitura:
   ```bash
   sudo ssh-keygen -t ed25519 -f /root/.ssh/boteco_deploy -N ""
   sudo cat /root/.ssh/boteco_deploy.pub   # colar em GitHub > Settings > Deploy keys (sem "write access")
   printf 'Host github.com\n  IdentityFile /root/.ssh/boteco_deploy\n' | sudo tee -a /root/.ssh/config
   git remote set-url origin git@github.com:USUARIO/REPOSITORIO.git
   ```
3. Não editar arquivos direto no servidor: alteração local faz o `git pull` recusar (a tela avisa).

## Regras para as atualizações

- Atualize com os caixas fechados (a tela não deixa com caixa aberto) — o sistema fica uns 5 minutos fora do ar.
- Módulo novo (`addons/boteco_novo`) não é instalado sozinho: só os já instalados são atualizados.
- Comandos à mão no servidor: `sudo ./scripts/atualizar.sh --git` ou
  `sudo bash scripts/agente_atualizacao.sh verificar`. Logs: `journalctl -u boteco-atualizacao`.
