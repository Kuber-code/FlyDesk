# Demo cockpit image. Build context is the repo root so `flydesk/` and
# `tests/fixtures/` are available to import/read. Independent of flydesk:latest.
FROM python:3.12-slim

WORKDIR /app

# App deps (pymongo, redis, pydantic, prometheus-client, …) + demo deps.
COPY requirements.txt ./requirements.txt
COPY demo/requirements.txt ./demo-requirements.txt
RUN pip install --no-cache-dir -r requirements.txt -r demo-requirements.txt

# Bring in the code (flydesk package, fixtures, demo/).
COPY . .

ENV PYTHONPATH=/app
EXPOSE 8500
CMD ["uvicorn", "demo.app:app", "--host", "0.0.0.0", "--port", "8500"]
