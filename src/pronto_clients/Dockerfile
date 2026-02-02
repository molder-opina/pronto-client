FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

WORKDIR /opt/pronto

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libffi-dev libssl-dev libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# Copy and install shared library
COPY pronto-libs /opt/pronto/pronto-libs
RUN pip install --no-cache-dir /opt/pronto/pronto-libs

# Install Client requirements
COPY pronto-client/src/pronto_clients/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Copy Client Code
COPY pronto-client/src/pronto_clients /opt/pronto/pronto_clients

ENV PYTHONPATH=/opt/pronto
WORKDIR /opt/pronto/pronto_clients

EXPOSE 5000

CMD ["gunicorn", "-b", "0.0.0.0:5000", "--timeout", "120", "--workers", "2", "--threads", "4", "wsgi:application"]
