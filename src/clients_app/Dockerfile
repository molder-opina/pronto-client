FROM python:3.11-slim

ENV PYTHONPATH=/opt/pronto
ENV PYTHONUNBUFFERED=1

# Install build dependencies
COPY clients_app/requirements.txt /tmp/requirements.txt
COPY wheels /tmp/wheels

# Copy shared module files
COPY shared /opt/pronto/shared

# Install Python dependencies from requirements
RUN pip install --no-cache-dir --no-index --find-links=/tmp/wheels -r /tmp/requirements.txt

# Copy application code
COPY employees_app /opt/pronto/employees_app
COPY clients_app /opt/pronto/clients_app

# Set PYTHONPATH to include all app directories
ENV PYTHONPATH=/opt/pronto:/opt/pronto/shared:/opt/pronto/employees_app
WORKDIR /opt/pronto/clients_app

CMD ["gunicorn", "-b", "0.0.0.0:5000", "wsgi:application"]
