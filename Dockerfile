# Imagem do servico principal (FeriasFlow API)
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATABASE_URL=sqlite:////app/data/feriasflow.db \
    CALENDARIO_URL=http://calendario-api:8000

WORKDIR /app

# Dependencias primeiro: camada cacheada enquanto o requirements nao muda
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Usuario sem privilegio (DevSecOps: privilegio minimo) e pasta do banco
RUN useradd --create-home api && mkdir -p /app/data && chown -R api:api /app
USER api

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
