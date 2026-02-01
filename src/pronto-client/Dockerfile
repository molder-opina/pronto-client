FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

WORKDIR /opt/pronto

# Copiar requirements y wheels primero para aprovechar cache de Docker
COPY pronto-client/requirements.txt /tmp/requirements.txt
COPY wheels /tmp/wheels

# Instalar dependencias del sistema, paquetes Python y limpiar
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libffi-dev \
        libssl-dev \
        libpq-dev \
    && pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir --find-links=/tmp/wheels -r /tmp/requirements.txt \
    && apt-get purge -y --auto-remove build-essential \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/*

# Copiar solo pronto-client (shared viene del wheel pronto-shared)
COPY pronto-client /opt/pronto/pronto-client

# Crear symlink para compatibilidad con clients_app
RUN ln -s /opt/pronto/pronto-client /opt/pronto/clients_app

ENV PYTHONPATH=/opt/pronto
WORKDIR /opt/pronto/pronto-client

EXPOSE 5000

CMD ["gunicorn", "-b", "0.0.0.0:5000", "--timeout", "120", "--workers", "2", "--threads", "4", "wsgi:application"]
