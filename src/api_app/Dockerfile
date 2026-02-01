FROM python:3.11-slim

ENV PYTHONPATH=/opt/pronto
ENV PYTHONUNBUFFERED=1

WORKDIR /opt/pronto

# Copy requirements from all apps
COPY clients_app/requirements.txt /tmp/requirements-clients.txt
COPY employees_app/requirements.txt /tmp/requirements-employees.txt
COPY wheels /tmp/wheels

# Install dependencies (merging both sets + common)
RUN pip install --no-cache-dir --no-index --find-links=/tmp/wheels -r /tmp/requirements-clients.txt && \
    pip install --no-cache-dir --no-index --find-links=/tmp/wheels -r /tmp/requirements-employees.txt && \
    pip install --no-cache-dir --no-index --find-links=/tmp/wheels gunicorn flask-cors flask-session

# Copy shared code
COPY shared /opt/pronto/shared

# Copy app codes
COPY clients_app /opt/pronto/clients_app
COPY employees_app /opt/pronto/employees_app
COPY api_app /opt/pronto/api_app

# Set workdir to API app
WORKDIR /opt/pronto/api_app

CMD ["gunicorn", "-b", "0.0.0.0:5000", "wsgi:application"]
