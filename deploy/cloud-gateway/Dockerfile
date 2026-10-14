# Imagen mínima del gateway. Solo el paquete arkos_cloud, el contrato y la configuración.
FROM python:3.12.10-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin arkos \
 && mkdir -p /var/lib/arkos-gateway && chown arkos:arkos /var/lib/arkos-gateway
WORKDIR /opt/arkos
COPY requirements-cloud.txt .
RUN pip install --no-cache-dir -r requirements-cloud.txt
COPY arkos_cloud ./arkos_cloud
COPY arkos_hermes/__init__.py arkos_hermes/contract.py ./arkos_hermes/
COPY config/cloud-gateway.json config/cloud-terms-record.json ./config/
USER arkos
CMD ["python", "-B", "-m", "arkos_cloud", "serve", "--gateway-config", "config/cloud-gateway.json", \
     "--terms-record", "config/cloud-terms-record.json", "--ledger", "/var/lib/arkos-gateway/ledger.sqlite3", \
     "--host", "127.0.0.1", "--port", "8787", "--trusted-proxy", "127.0.0.1"]
