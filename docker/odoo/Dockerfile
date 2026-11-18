# Imagem do Odoo do Boteco: a oficial odoo:18 + bibliotecas Python extras dos módulos boteco_*.
# Construída pelo docker compose (./instalar.sh e ./scripts/atualizar.sh já fazem isso).
FROM odoo:18

USER root
# instaloader: leitura dos posts públicos de fornecedores no Instagram (Etapa 18, radar de preços)
RUN pip3 install --no-cache-dir --break-system-packages "instaloader==4.14.1"
USER odoo
