.PHONY: install format lint typecheck test build dev-backend dev-frontend dev-dashboard

install:
	poetry --directory backend install
	corepack enable
	corepack pnpm install

format:
	poetry --directory backend run black app tests
	poetry --directory backend run ruff check --fix app tests
	corepack pnpm format

lint:
	poetry --directory backend run black --check app tests
	poetry --directory backend run ruff check app tests
	corepack pnpm lint
	corepack pnpm format:check

typecheck:
	poetry --directory backend run mypy app tests
	corepack pnpm typecheck

test:
	poetry --directory backend run pytest
	corepack pnpm test

build:
	corepack pnpm build

dev-backend:
	poetry --directory backend run uvicorn app.main:app --reload

dev-frontend:
	corepack pnpm dev:frontend

dev-dashboard:
	corepack pnpm dev:dashboard
