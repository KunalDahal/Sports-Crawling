# syntax=docker/dockerfile:1.7

FROM node:20-bookworm-slim AS frontend-builder
WORKDIR /src
COPY frontend/package.json ./frontend/package.json
WORKDIR /src/frontend
RUN npm install
COPY frontend ./
RUN npm run build

FROM golang:1.22-bookworm AS go-builder
WORKDIR /src
COPY backend ./backend
WORKDIR /src/backend
RUN CGO_ENABLED=0 GOOS=linux go build -o /out/spcrawler-backend ./cmd/server

FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ADDR=:8080 \
    STATIC_DIR=/app/frontend/dist \
    SPCRAWLER_PYTHON=python3 \
    SPCRAWLER_RUNNER=/app/backend/scripts/run_scraper.py

WORKDIR /app

COPY --from=go-builder /out/spcrawler-backend /usr/local/bin/spcrawler-backend
COPY backend/scripts ./backend/scripts
COPY spcrawler ./spcrawler
COPY --from=frontend-builder /src/frontend/dist ./frontend/dist

RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r /app/backend/scripts/requirements.txt \
    && python -m pip install --no-cache-dir -e /app/spcrawler \
    && python -m playwright install --with-deps chromium

EXPOSE 8080

CMD ["spcrawler-backend"]