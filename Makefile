# ============================================================================
#  _____ _            _                    _
# |  ___| |_ _ __   / \   __ _  ___ _ __ | |_
# | |_  | __| '_ \ / _ \ / _` |/ _ \ '_ \| __|
# |  _| | |_| |_) / ___ \ (_| |  __/ | | | |_
# |_|    \__| .__/_/   \_\__, |\___|_| |_|\__|
#           |_|          |___/
#
#  Build Automation for FtpAgent (.NET 8)
# ============================================================================

# Colors
GREEN  := \033[0;32m
YELLOW := \033[0;33m
CYAN   := \033[0;36m
RED    := \033[0;31m
BOLD   := \033[1m
RESET  := \033[0m

# Paths
SOLUTION     := FtpAgent.sln
PROJECT      := src/FtpAgent/FtpAgent.csproj
TEST_PROJECT := src/FtpAgent.Tests/FtpAgent.Tests.csproj
CONFIG       := config/appsettings.json
PUBLISH_DIR  := publish

# .NET settings
CONFIGURATION := Release
RUNTIME       := linux-x64

.PHONY: help setup build test test-coverage run dry-run clean format format-check publish docker-build

# Default target
help: ## Show available commands
	@printf "$(BOLD)$(CYAN)"
	@printf "============================================================\n"
	@printf "  FtpAgent - Build Commands\n"
	@printf "============================================================$(RESET)\n"
	@printf "\n"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-20s$(RESET) %s\n", $$1, $$2}'
	@printf "\n"

setup: ## Install .NET 8 SDK (if needed) and restore packages
	@printf "$(CYAN)[setup]$(RESET) Checking environment...\n"
	@if ! command -v dotnet >/dev/null 2>&1; then \
		printf "$(YELLOW)[setup]$(RESET) .NET SDK not found. Installing...\n"; \
		curl -sSL https://dot.net/v1/dotnet-install.sh | bash /dev/stdin --channel 8.0; \
		printf "$(GREEN)[setup]$(RESET) .NET SDK installed.\n"; \
	else \
		printf "$(GREEN)[setup]$(RESET) .NET SDK found: $$(dotnet --version)\n"; \
	fi
	@printf "$(CYAN)[setup]$(RESET) Restoring NuGet packages...\n"
	@dotnet restore $(SOLUTION)
	@printf "$(GREEN)[setup]$(RESET) Setup complete.\n"

build: ## Build the solution
	@printf "$(CYAN)[build]$(RESET) Building $(SOLUTION) ($(CONFIGURATION))...\n"
	@dotnet build $(SOLUTION) --configuration $(CONFIGURATION) --no-restore 2>&1 || \
		(printf "$(RED)[build]$(RESET) Build failed. Try running 'make setup' first.\n" && exit 1)
	@printf "$(GREEN)[build]$(RESET) Build succeeded.\n"

test: ## Run all tests with verbose output
	@printf "$(CYAN)[test]$(RESET) Running tests...\n"
	@dotnet test $(SOLUTION) --configuration $(CONFIGURATION) --verbosity normal --logger "console;verbosity=detailed"
	@printf "$(GREEN)[test]$(RESET) All tests passed.\n"

test-coverage: ## Run tests with code coverage and generate report
	@printf "$(CYAN)[test-coverage]$(RESET) Running tests with coverage...\n"
	@dotnet test $(TEST_PROJECT) \
		--configuration $(CONFIGURATION) \
		--collect:"XPlat Code Coverage" \
		--results-directory ./coverage \
		--verbosity normal
	@printf "$(GREEN)[test-coverage]$(RESET) Coverage report generated in ./coverage\n"
	@printf "$(YELLOW)[test-coverage]$(RESET) Tip: Install reportgenerator for HTML reports:\n"
	@printf "  dotnet tool install -g dotnet-reportgenerator-globaltool\n"
	@printf "  reportgenerator -reports:./coverage/**/coverage.cobertura.xml -targetdir:./coverage/report -reporttypes:Html\n"

run: ## Run the agent
	@printf "$(CYAN)[run]$(RESET) Starting FtpAgent...\n"
	@dotnet run --project $(PROJECT) --configuration $(CONFIGURATION)

dry-run: ## Run the agent in dry-run mode
	@printf "$(CYAN)[dry-run]$(RESET) Starting FtpAgent (dry-run)...\n"
	@dotnet run --project $(PROJECT) --configuration $(CONFIGURATION) -- --dry-run

clean: ## Clean build artifacts
	@printf "$(CYAN)[clean]$(RESET) Cleaning build artifacts...\n"
	@dotnet clean $(SOLUTION) --configuration $(CONFIGURATION) 2>/dev/null || true
	@find . -type d \( -name "bin" -o -name "obj" \) -exec rm -rf {} + 2>/dev/null || true
	@rm -rf $(PUBLISH_DIR) coverage TestResults
	@printf "$(GREEN)[clean]$(RESET) Clean complete.\n"

format: ## Format code with dotnet format
	@printf "$(CYAN)[format]$(RESET) Formatting code...\n"
	@dotnet format $(SOLUTION)
	@printf "$(GREEN)[format]$(RESET) Formatting complete.\n"

format-check: ## Check code formatting (CI-friendly, no changes made)
	@printf "$(CYAN)[format-check]$(RESET) Checking code formatting...\n"
	@dotnet format $(SOLUTION) --verify-no-changes || \
		(printf "$(RED)[format-check]$(RESET) Formatting issues found. Run 'make format' to fix.\n" && exit 1)
	@printf "$(GREEN)[format-check]$(RESET) Code formatting is correct.\n"

publish: ## Publish self-contained binary for linux-x64
	@printf "$(CYAN)[publish]$(RESET) Publishing for $(RUNTIME)...\n"
	@dotnet publish $(PROJECT) \
		--configuration $(CONFIGURATION) \
		--runtime $(RUNTIME) \
		--self-contained true \
		--output $(PUBLISH_DIR)/$(RUNTIME) \
		-p:PublishSingleFile=true \
		-p:PublishTrimmed=false \
		-p:IncludeNativeLibrariesForSelfExtract=true
	@printf "$(GREEN)[publish]$(RESET) Published to $(PUBLISH_DIR)/$(RUNTIME)/\n"
	@ls -lh $(PUBLISH_DIR)/$(RUNTIME)/FtpAgent 2>/dev/null || true

docker-build: ## Build Docker image (placeholder)
	@printf "$(YELLOW)[docker-build]$(RESET) Docker support is not yet configured.\n"
	@printf "$(YELLOW)[docker-build]$(RESET) Add a Dockerfile to the project root and update this target.\n"
	@printf "$(YELLOW)[docker-build]$(RESET) Example: docker build -t ftp-agent:latest .\n"
