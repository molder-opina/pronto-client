FROM python:3.11-slim

ENV PYTHONPATH=/opt/pronto
ENV PYTHONUNBUFFERED=1

COPY pronto-client/requirements.txt /tmp/requirements.txt
COPY wheels /tmp/wheels

COPY shared /opt/pronto/shared

RUN pip install --no-cache-dir --no-index --find-links=/tmp/wheels -r /tmp/requirements.txt

COPY pronto-client /opt/pronto/pronto-client

WORKDIR /opt/pronto/pronto-client

CMD ["gunicorn", "-b", "0.0.0.0:5000", "--timeout", "120", "--workers", "2", "--threads", "4", "wsgi:application"]
