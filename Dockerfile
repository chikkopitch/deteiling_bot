FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN addgroup --system bot && adduser --system --ingroup bot bot
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir ".[dev]"
COPY . .
RUN chown -R bot:bot /app
USER bot
CMD ["sh", "-c", "alembic upgrade head && python -m app.seed && exec python -m app.main"]
