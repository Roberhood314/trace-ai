FROM node:20-alpine AS web-build
WORKDIR /web
COPY web/package*.json ./
RUN npm install
COPY web ./
ENV VITE_PI_SANDBOX=true
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    WEB_DIST_DIR=/app/web-dist

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN useradd --create-home --uid 10001 traceai \
    && mkdir -p /data/uploads /app/web-dist \
    && chown -R traceai:traceai /data /app

COPY --chown=traceai:traceai alembic.ini ./alembic.ini
COPY --chown=traceai:traceai alembic ./alembic
COPY --chown=traceai:traceai app ./app
COPY --from=web-build --chown=traceai:traceai /web/dist /app/web-dist

USER traceai
EXPOSE 8000
CMD ["sh","-c","alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
