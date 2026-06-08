FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.8 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app

# Слой с зависимостями кэшируется отдельно от кода.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app
COPY gunicorn.conf.py ./
RUN uv sync --frozen --no-dev

EXPOSE 8000
CMD ["uv", "run", "gunicorn", "app.main:app", "-c", "gunicorn.conf.py"]
