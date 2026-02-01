FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

WORKDIR /opt/pronto

# Instalar dependencias de compilación, instalar paquetes Python, y limpiar todo en una sola capa
COPY employees_app/requirements.txt /tmp/requirements.txt
COPY wheels /tmp/wheels
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libffi-dev libssl-dev \
    && pip install --no-cache-dir --no-index --find-links=/tmp/wheels -r /tmp/requirements.txt \
    && pip install --no-cache-dir --no-index --find-links=/tmp/wheels requests==2.32.3 \
    && apt-get purge -y --auto-remove build-essential \
    && rm -rf /var/lib/apt/lists/* /tmp/*

# Copy entire build context to ensure all modules (admin, shared, waiter, etc.) are available
COPY . /opt/pronto

ENV PYTHONPATH=/opt/pronto
WORKDIR /opt/pronto/employees_app

CMD ["gunicorn", "-b", "0.0.0.0:5000", "wsgi:application"]
