# ==================== STAGE 1: Build Frontend ====================
#FROM node:20-alpine AS frontend-builder
#WORKDIR /app/frontend
#COPY frontend/package*.json ./
#RUN npm ci && npm cache clean --force
#COPY frontend/ ./
#RUN npm run build

# ==================== STAGE 2: Python Runtime ====================
FROM python:3.11-slim

# Устанавливаем системные зависимости
RUN apt-get update && apt-get install -y --no-install-recommends \
    supervisor \
    ca-certificates \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Установка зависимостей Python
COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    rm -rf /root/.cache/pip

# Копируем исходники бэкенда (соблюдая новую структуру src)
COPY src/ ./src/
COPY migrations/ ./migrations/
COPY scripts/ ./scripts/
COPY supervisord.conf /etc/supervisord.conf

# Копируем билд фронтенда в статику бэкенда
# (Убедись, что в FastAPI app смонтирована папка /app/static)
#COPY --from=frontend-builder /app/frontend/dist ./static

# Очистка
RUN find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true && \
    find . -name "*.pyc" -delete 2>/dev/null || true

EXPOSE 8000

CMD ["/usr/bin/supervisord", "-c", "/etc/supervisord.conf"]