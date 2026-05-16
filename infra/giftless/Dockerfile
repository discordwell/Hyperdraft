FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl gettext-base \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# giftless 0.6.2 ships with no declared deps; install the upstream pinned
# requirements (saved locally for build reproducibility) before installing
# giftless itself.
COPY requirements-pinned.txt /app/requirements-pinned.txt
RUN pip install --no-cache-dir -r /app/requirements-pinned.txt && \
    pip install --no-cache-dir \
        'giftless==0.6.2' \
        'gunicorn==23.0.0'

COPY giftless.yaml.template /app/giftless.yaml.template
COPY wsgi.py /app/wsgi.py
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

ENV GIFTLESS_CONFIG_FILE=/app/giftless.yaml \
    PYTHONUNBUFFERED=1 \
    PORT=8000

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]

CMD ["gunicorn", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "2", \
     "--threads", "4", \
     "--worker-class", "gthread", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "--chdir", "/app", \
     "wsgi:app"]
