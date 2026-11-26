# Makefile for AYZER Webapp Backend
.PHONY: help dev test lint build up down logs clean migrate perf perf-ui perf-report benchmark

# Default target
help:
	@echo "AYZER Webapp Backend - Available Commands"
	@echo "======================================="
	@echo ""
	@echo "Development:"
	@echo "  make dev          - Start development environment with Docker"
	@echo "  make up           - Start all Docker services"
	@echo "  make down         - Stop all Docker services"
	@echo "  make logs         - View Docker service logs"
	@echo "  make restart      - Restart all Docker services"
	@echo ""
	@echo "Testing:"
	@echo "  make test         - Run all tests"
	@echo "  make test-cov     - Run tests with coverage report"
	@echo "  make test-fast    - Run tests in parallel"
	@echo ""
	@echo "Code Quality:"
	@echo "  make lint         - Run linters (ruff, mypy)"
	@echo "  make format       - Format code with black"
	@echo ""
	@echo "Database:"
	@echo "  make migrate      - Run database migrations"
	@echo "  make migrate-new msg=\"description\" - Create a new migration"
	@echo "  make seed         - Seed first tenant"
	@echo ""
	@echo "Performance:"
	@echo "  make perf         - Run Locust load tests (headless)"
	@echo "  make perf-ui      - Run Locust with web UI"
	@echo "  make perf-report  - Show results location"
	@echo "  make benchmark    - Run pytest-benchmark micro-benchmarks"
	@echo ""
	@echo "Build:"
	@echo "  make build        - Build Docker images"
	@echo "  make build-prod   - Build production Docker images"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean        - Remove Python cache files"
	@echo "  make clean-docker - Remove Docker volumes and images"

# Development
dev:
	docker-compose up -d postgres redis
	@echo "Waiting for services..."
	@sleep 3
	uvicorn main:app --reload --host 0.0.0.0 --port 8000

up:
	docker-compose up -d

down:
	docker-compose down

logs:
	docker-compose logs -f

restart:
	docker-compose restart

# Testing
test:
	pytest tests/ -v --tb=short -n 8

test-cov:
	pytest tests/ -v --cov=src --cov-report=html --cov-report=term-missing

test-fast:
	pytest tests/ -v -n auto

# Code Quality
lint:
	ruff check src/ tests/
	mypy src/ --ignore-missing-imports

format:
	black src/ tests/
	ruff check src/ tests/ --fix

# Database
migrate:
	alembic upgrade head

migrate-new:
ifndef msg
	$(error Usage: make migrate-new msg="your_migration_message")
endif
	alembic revision --autogenerate -m "$(msg)"

seed:
	python scripts/seed_first_tenant.py

# Performance Testing
PERF_USERS?=50
PERF_SPAWN_RATE?=5
PERF_RUN_TIME?=5m

perf:
	cd perf && locust -f locustfile.py --headless \
		-u $(PERF_USERS) -r $(PERF_SPAWN_RATE) \
		-t $(PERF_RUN_TIME) --csv=results/run

perf-ui:
	cd perf && locust -f locustfile.py

perf-report:
	@echo "Results in app/backend/perf/results/"

benchmark:
	pytest tests/benchmarks/ -v --benchmark-only \
		--benchmark-json=results/benchmark.json \
		--benchmark-compare=results/baseline.json

# Build
build:
	docker-compose build

build-prod:
	docker-compose -f docker-compose.prod.yml build

# Cleanup
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type f -name "*.pyo" -delete 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name ".coverage" -delete 2>/dev/null || true

clean-docker:
	docker-compose down -v --rmi local
