.PHONY: up down logs health ingest test lint format security

# ─── Services ─────────────────────────────────────────────────
up:
	docker-compose up -d
	@echo "Services starting..."
	@echo "Dashboard: http://localhost"
	@echo "API:       http://localhost:8010/docs"
	@echo "Prefect:   http://localhost:4200"
	@echo "Qdrant:    http://localhost:6333/dashboard"

down:
	docker-compose down

logs:
	docker-compose logs -f

health:
	@curl -sf http://localhost:8010/health | python3 -m json.tool

# ─── Ingestion ────────────────────────────────────────────────
ingest:
	docker-compose run --rm ingestion python -m flows.ingest_flow

ingest-local:
	python -m flows.ingest_flow

# ─── Testing ──────────────────────────────────────────────────
test:
	pytest tests/ -v

test-cov:
	pytest tests/ --cov=. --cov-report=html -v

test-api:
	pytest tests/test_api.py -v

test-ingestion:
	pytest tests/test_ingestion.py -v

# ─── Code Quality ─────────────────────────────────────────────
lint:
	flake8 . --max-line-length=120 --exclude=.venv,__pycache__

format:
	black . --line-length=120
	isort . --profile=black

security:
	bandit -r . -x .venv,tests
	safety check

# ─── Setup ────────────────────────────────────────────────────
setup:
	cp .env.example .env
	@echo "Edit .env with your API keys before running 'make up'"