FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install deps first for better layer caching.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Collect static for the admin (best-effort; no failure if nothing to collect).
RUN python manage.py collectstatic --noinput || true

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz')" || exit 1

# migrate sets up Django's own SQLite (auth/sessions); domain data is in Mongo.
# If PROMETHEUS_MULTIPROC_DIR is set (web service), prepare it so the 3 gunicorn
# workers aggregate their metrics; gunicorn.conf.py cleans up dead workers.
CMD ["sh", "-c", "if [ -n \"$PROMETHEUS_MULTIPROC_DIR\" ]; then rm -rf \"$PROMETHEUS_MULTIPROC_DIR\"; mkdir -p \"$PROMETHEUS_MULTIPROC_DIR\"; fi; python manage.py migrate --noinput && gunicorn config.wsgi:application --config gunicorn.conf.py --bind 0.0.0.0:8000 --workers 3 --access-logfile -"]
