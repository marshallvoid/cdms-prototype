ifeq ($(OS),Windows_NT)
PY := $(CURDIR)/.venv/Scripts/python.exe
else
PY := $(CURDIR)/.venv/bin/python
endif
PIP := $(PY) -m pip
export TEST_DATABASE_URL ?= postgresql+asyncpg://cdms:cdms@localhost:5432/cdms
PSQL_URL ?= postgresql://cdms:cdms@localhost:5432/cdms

.DEFAULT_GOAL := help

.PHONY: help
help:  ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

.PHONY: venv
venv:  ## Create .venv and install all dependencies
	python -m venv .venv
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements-dev.txt

.PHONY: env
env:  ## Create .env from .env.example if it does not exist
	@test -f .env || (cp .env.example .env && echo "created .env")

.PHONY: lint
lint:  ## Run ruff over everything
	$(PY) -m ruff check .

.PHONY: fmt
fmt:  ## Format with ruff and apply safe lint fixes
	$(PY) -m ruff format .
	$(PY) -m ruff check --fix .

.PHONY: fmt-check
fmt-check:  ## Fail if anything is unformatted
	$(PY) -m ruff format --check .

.PHONY: typecheck
typecheck:  ## Run mypy in strict mode over the services
	$(PY) -m mypy services

.PHONY: check
check: lint fmt-check typecheck  ## lint + format check + typecheck

.PHONY: up
up: env  ## Build and start the whole stack
	docker compose up --build -d
	docker compose ps

.PHONY: down
down:  ## Stop the stack (keeps the database volume)
	docker compose down

.PHONY: clean
clean:  ## Stop the stack and delete the database volume
	docker compose down -v

.PHONY: logs
logs:  ## Tail all service logs
	docker compose logs -f

.PHONY: migrate
migrate:  ## Apply database migrations (rebuilds the cdms image, then applies them)
	docker compose up --build -d cdms

.PHONY: demo
demo:  ## Walk the running stack through polling, duplicates and staleness
	$(PY) scripts/demo.py

.PHONY: chaos
chaos:  ## Make the upstream misbehave and check the history survives
	$(PY) scripts/chaos.py

.PHONY: verify
verify:  ## Prove in the database that nothing was stored twice
	$(PY) scripts/verify.py

.PHONY: load
load:  ## Locust, 50 users ramping at 25/s for 10 minutes
	docker compose --profile load run --build --rm loadtest --headless -u 50 -r 25 -t 10m

.PHONY: spike
spike:  ## Locust spike, 200 users instantly, then 3 minutes
	docker compose --profile load run --build --rm loadtest --headless -u 200 -r 200 -t 3m
