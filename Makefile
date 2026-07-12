.PHONY: up down migrate seed test lint typecheck
up:
	docker compose up --build
down:
	docker compose down
migrate:
	docker compose exec bot alembic upgrade head
seed:
	docker compose exec bot python -m app.seed
test:
	pytest
lint:
	ruff check . && ruff format --check .
typecheck:
	mypy app
