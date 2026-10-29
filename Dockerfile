FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# Шрифт с кириллицей для PDF-отчёта: встроенные шрифты fpdf2 знают только latin-1.
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
RUN uv sync --frozen --no-dev

# Метаданные сборки из CI (docker.yml); объявлены в конце, чтобы не ломать кэш слоёв.
ARG BUILD_TIME=unknown \
    BUILD_BRANCH=unknown \
    BUILD_COMMIT=unknown \
    BUILD_TAG=dev
ENV BUILD_TIME=${BUILD_TIME} \
    BUILD_BRANCH=${BUILD_BRANCH} \
    BUILD_COMMIT=${BUILD_COMMIT} \
    BUILD_TAG=${BUILD_TAG}

CMD ["uv", "run", "python", "-m", "apps.api"]
