# VPN (WireGuard): cozinha central e acesso remoto do dono

O sistema nunca fica exposto na internet. A cozinha central e o celular do dono entram por uma VPN
WireGuard que termina no mini PC do bar.

## No mini PC do bar

```bash
sudo apt install wireguard
wg genkey | tee /etc/wireguard/servidor.key | wg pubkey > /etc/wireguard/servidor.pub
sudo cp scripts/vpn/wg0-servidor.conf.example /etc/wireguard/wg0.conf   # preencha as chaves
sudo systemctl enable --now wg-quick@wg0
```

No roteador do bar: liberar (encaminhar) a porta **UDP 51820** para o IP do mini PC. Se a operadora
não der IP fixo, use um DNS dinâmico (ex.: DuckDNS) no roteador.

## Em cada aparelho (cozinha central, celular do dono)

1. Instale o app WireGuard.
2. Gere a chave do aparelho e cadastre a chave pública como `[Peer]` no servidor.
3. Use `scripts/vpn/wg0-cliente.conf.example` (ou o QR gerado por `qrencode -t ansiutf8 < cliente.conf`).
4. Com a VPN ligada: `https://10.8.0.1` (painel do dono, sistema completo).

Dica: na cozinha central, o tablet de produção fica sempre com a VPN ligada.
