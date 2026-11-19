# Coletor de ofertas (Etapa 35): fora do Odoo, para robôs não pesarem no caixa.
FROM mcr.microsoft.com/playwright/python:v1.47.0-jammy
RUN pip install --no-cache-dir requests==2.32.3 instaloader==4.14.1 playwright==1.47.0
WORKDIR /app
COPY coletor.py /app/coletor.py
ENV PYTHONUNBUFFERED=1
CMD ["python", "/app/coletor.py"]
