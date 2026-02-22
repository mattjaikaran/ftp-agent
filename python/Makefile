# ============================================================================
#  FTP Agent — Python Backend + React Frontend
# ============================================================================

GREEN  := \033[0;32m
YELLOW := \033[0;33m
CYAN   := \033[0;36m
RED    := \033[0;31m
BOLD   := \033[1m
RESET  := \033[0m

.PHONY: help setup dev test test-cov lint format check typecheck serve run dry-run \
        frontend-dev frontend-build test-frontend docker-build docker-up docker-down docker-logs ci clean

help: ## Show available commands
	@printf "$(BOLD)$(CYAN)============================================================\n"
	@printf "  FTP Agent (Python) — Build Commands\n"
	@printf "============================================================$(RESET)\n\n"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-20s$(RESET) %s\n", $$1, $$2}'
	@printf "\n"

setup: ## Install all dependencies (backend + frontend)
	@printf "$(CYAN)[setup]$(RESET) Installing Python dependencies...\n"
	uv sync --all-extras
	@printf "$(GREEN)[setup]$(RESET) Python deps installed.\n"
	@printf "$(CYAN)[setup]$(RESET) Installing frontend dependencies...\n"
	cd frontend && bun install
	@printf "$(GREEN)[setup]$(RESET) Frontend deps installed.\n"

dev: ## Install dev dependencies only
	@printf "$(CYAN)[dev]$(RESET) Installing dev dependencies...\n"
	uv sync --extra dev
	@printf "$(GREEN)[dev]$(RESET) Done.\n"

test: ## Run Python tests
	@printf "$(CYAN)[test]$(RESET) Running tests...\n"
	uv run pytest -x --tb=short
	@printf "$(GREEN)[test]$(RESET) All tests passed.\n"

test-cov: ## Run tests with coverage (fail under 70%)
	@printf "$(CYAN)[test-cov]$(RESET) Running tests with coverage...\n"
	uv run pytest tests/ --cov=ftp_agent --cov-report=term-missing --cov-report=html --cov-fail-under=65
	@printf "$(GREEN)[test-cov]$(RESET) Coverage report in htmlcov/\n"

lint: ## Run ruff linter
	@printf "$(CYAN)[lint]$(RESET) Linting...\n"
	uv run ruff check ftp_agent/ tests/
	@printf "$(GREEN)[lint]$(RESET) Clean.\n"

format: ## Format code with ruff
	@printf "$(CYAN)[format]$(RESET) Formatting...\n"
	uv run ruff format ftp_agent/ tests/
	uv run ruff check --fix ftp_agent/ tests/
	@printf "$(GREEN)[format]$(RESET) Done.\n"

typecheck: ## Run mypy strict type checking
	@printf "$(CYAN)[typecheck]$(RESET) Type checking...\n"
	uv run mypy --strict ftp_agent/
	@printf "$(GREEN)[typecheck]$(RESET) Clean.\n"

check: lint typecheck ## Lint + type check
	@printf "$(GREEN)[check]$(RESET) All checks passed.\n"

serve: ## Start FastAPI server (development)
	@printf "$(CYAN)[serve]$(RESET) Starting server on :8000...\n"
	uv run ftp-agent serve --host 0.0.0.0 --port 8000

run: ## Run migration agent
	@printf "$(CYAN)[run]$(RESET) Starting migration agent...\n"
	uv run ftp-agent run

dry-run: ## Run agent in dry-run mode
	@printf "$(CYAN)[dry-run]$(RESET) Starting agent (dry-run)...\n"
	uv run ftp-agent run --dry-run

frontend-dev: ## Start Vite dev server
	@printf "$(CYAN)[frontend-dev]$(RESET) Starting Vite on :5173...\n"
	cd frontend && bun run dev

frontend-build: ## Build frontend for production
	@printf "$(CYAN)[frontend-build]$(RESET) Building frontend...\n"
	cd frontend && bun run build
	@printf "$(GREEN)[frontend-build]$(RESET) Built to static/\n"

test-frontend: ## Run frontend tests (Vitest)
	@printf "$(CYAN)[test-frontend]$(RESET) Running frontend tests...\n"
	cd frontend && bun run test
	@printf "$(GREEN)[test-frontend]$(RESET) All tests passed.\n"

docker-build: ## Build Docker image
	@printf "$(CYAN)[docker-build]$(RESET) Building Docker image...\n"
	docker compose build
	@printf "$(GREEN)[docker-build]$(RESET) Done.\n"

docker-up: ## Start all services via Docker Compose
	@printf "$(CYAN)[docker-up]$(RESET) Starting services...\n"
	docker compose up -d
	@printf "$(GREEN)[docker-up]$(RESET) Running at http://localhost:8000\n"

docker-down: ## Stop Docker services
	docker compose down

docker-logs: ## Tail Docker service logs
	docker compose logs -f

ci: lint typecheck test-cov frontend-build test-frontend ## Run all CI checks
	@printf "$(GREEN)$(BOLD)[ci]$(RESET) $(GREEN)All CI checks passed.$(RESET)\n"

clean: ## Remove build artifacts
	@printf "$(CYAN)[clean]$(RESET) Cleaning...\n"
	rm -rf .venv __pycache__ .pytest_cache .mypy_cache htmlcov .coverage
	rm -rf frontend/node_modules static
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@printf "$(GREEN)[clean]$(RESET) Done.\n"
