FROM python:3.12-slim

WORKDIR /app

# System deps needed to build psycopg2 / Pillow wheels on some platforms
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev libjpeg-dev zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV FLASK_ENV=production \
    PORT=5000

EXPOSE 5000

# gunicorn is the production WSGI server; 3 workers is a sane default for a
# small VM/container, tune with WEB_CONCURRENCY if needed.
CMD ["sh", "-c", "gunicorn server:app --bind 0.0.0.0:${PORT} --workers 3 --threads 4 --timeout 60"]
