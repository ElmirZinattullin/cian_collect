# syntax=docker/dockerfile:1.7
############################################
# Stage 1: build deps with uv
############################################
FROM ghcr.io/astral-sh/uv:python3.12-bookworm AS builder

# Не тянем бинарные питоны (они уже есть в образе uv) и кладём виртуалку отдельно
ENV UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/py_sourse

WORKDIR /app

# Только файлы зависимостей — чтобы кешировалось
COPY pyproject.toml uv.lock ./

# Синхронизируем зависимости (без установки кода проекта)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project

# При желании можно поставить сам проект (если он как пакет)
# RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen

############################################
# Stage 2: runtime
############################################
FROM python:3.12-slim-bookworm AS runtime

# Локаль/таймзона/сертификаты (tzdata опционален, если TZ важен)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Europe/Moscow

RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates tzdata \
    && rm -rf /var/lib/apt/lists/*

# Копируем готовое виртуальное окружение из builder-стадии
COPY --from=builder /py_sourse /py_sourse

# Подключаем виртуалку в PATH
ENV VIRTUAL_ENV=/py_sourse
ENV PATH="${VIRTUAL_ENV}/bin:${PATH}"

# Создаём непривилегированного пользователя
RUN useradd -ms /bin/bash appuser
USER appuser

WORKDIR /app

# Копируем исходники
# (Если используете docker compose с volume ./:/app — можно опустить COPY, но оставлю на случай прода)
COPY --chown=appuser:appuser . /app

# Значения по умолчанию переопределяются в docker-compose.yml
CMD ["bash", "-lc", "python -V && celery -A cian_celery_tasks worker -l info"]
