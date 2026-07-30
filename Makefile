.PHONY: up down logs restart clean config build verify test lint typecheck format

up:
	docker compose up --build --detach

down:
	docker compose down --remove-orphans

logs:
	docker compose logs --follow --tail=200

restart:
	docker compose restart

clean:
	docker compose down --volumes --remove-orphans

config:
	docker compose config --quiet

build:
	docker compose build

verify:
	docker compose --profile tools run --rm verify

test:
	docker compose run --rm --no-deps backend pytest
	docker compose run --rm --no-deps frontend corepack pnpm --filter @fashion-network/frontend test
	docker compose run --rm --no-deps dashboard corepack pnpm --filter @fashion-network/dashboard test

lint:
	docker compose run --rm --no-deps backend black --check app tests
	docker compose run --rm --no-deps backend ruff check app tests
	docker compose run --rm --no-deps frontend corepack pnpm --filter @fashion-network/frontend lint
	docker compose run --rm --no-deps dashboard corepack pnpm --filter @fashion-network/dashboard lint
	docker compose run --rm --no-deps frontend corepack pnpm format:check

typecheck:
	docker compose run --rm --no-deps backend mypy app tests
	docker compose run --rm --no-deps frontend corepack pnpm --filter @fashion-network/frontend typecheck
	docker compose run --rm --no-deps dashboard corepack pnpm --filter @fashion-network/dashboard typecheck

format:
	docker compose run --rm --no-deps backend black app tests
	docker compose run --rm --no-deps backend ruff check --fix app tests
	docker compose run --rm --no-deps frontend corepack pnpm format
