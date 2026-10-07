# Etapa 4 – Tablet na mesa e QR Code (`boteco_autoatendimento`)

## Como funciona a segurança do QR

1. O QR da mesa é fixo (PDF em PDV › Imprimir › "QR Code das mesas").
2. Ao abrir, o celular recebe um identificador (cookie). Só pede de dentro da rede Wi-Fi dos
   clientes (`REDE_CLIENTES`) – fora dela, só consulta o cardápio.
3. No primeiro "Enviar pedido" o garçom recebe "Mesa 7: celular quer pedir" e libera com um toque.
   O pedido fica guardado no celular e sai sozinho quando ele libera.
4. A liberação vale para a **sessão da mesa**: quando a conta fecha, o código da sessão muda e o
   celular precisa de nova liberação (foto antiga do QR não pede).
5. Limite por envio (padrão R$ 300) configurável no PDV.
6. Primeira bebida alcoólica da mesa: aviso de +18 e o pedido só vai para o bar depois que o garçom
   confirma a idade (os demais pedidos seguem direto).

Tablet fixo: cadastre em Boteco › Salão e caixa › Tablets das mesas e abra o link gerado no tablet
(Android: "Fixar app"; iPad: "Acesso guiado"). Já vem liberado, tem tela de descanso com ofertas
após 2 min, volta para o início quando a conta fecha e só sai do cardápio com PIN do gerente.

## Critérios de aceite

| Critério | Teste / verificação |
| --- | --- |
| Cliente sem instrução pede 2 cervejas e 1 porção em menos de 30 s | **Pendente: teste com usuário real** (fluxo nativo: categoria → item → "Pedido") |
| Celular fora da rede com foto antiga do QR não pede | `test_celular_fora_da_rede_nao_pede`, `test_foto_antiga_do_qr_nao_pede` |
| "Pedir a conta" deixa a mesa roxa e avisa em até 2 s | `test_pedir_a_conta_deixa_a_mesa_roxa_em_ate_2s` |
| Desligar o Wi-Fi no meio não perde o carrinho | O autoatendimento do Odoo guarda o carrinho no aparelho (IndexedDB); o módulo avisa "pedido guardado" e reenvia quando a rede volta. **Pendente: teste físico com o Wi-Fi.** |

Verificado no navegador: barra da mesa, "Chamar garçom", pedido aguardando liberação e envio
automático depois da liberação, com ticket no KDS.
