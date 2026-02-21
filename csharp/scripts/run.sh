#!/usr/bin/env bash
# ============================================================================
#  FtpAgent - Runner Script
#
#  Wrapper to run the FtpAgent with proper environment checks.
#  Forwards all arguments to the dotnet process.
#
#  Usage:
#    ./scripts/run.sh              # Run normally
#    ./scripts/run.sh --dry-run    # Run in dry-run mode
#    ./scripts/run.sh --help       # Pass --help to the agent
# ============================================================================
set -euo pipefail

# Colors
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
RED='\033[0;31m'
RESET='\033[0m'

# Resolve the project root (parent of the scripts/ directory)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

PROJECT_FILE="${PROJECT_ROOT}/src/FtpAgent/FtpAgent.csproj"
CONFIG_FILE="${PROJECT_ROOT}/config/appsettings.json"
CONFIGURATION="Release"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
info()  { printf "${CYAN}[ftp-agent]${RESET} %s\n" "$*"; }
warn()  { printf "${YELLOW}[ftp-agent]${RESET} %s\n" "$*"; }
error() { printf "${RED}[ftp-agent]${RESET} %s\n" "$*" >&2; }

# ---------------------------------------------------------------------------
# Graceful shutdown on Ctrl+C / SIGTERM
# ---------------------------------------------------------------------------
DOTNET_PID=""

cleanup() {
    printf "\n"
    info "Shutting down FtpAgent..."
    if [[ -n "${DOTNET_PID}" ]] && kill -0 "${DOTNET_PID}" 2>/dev/null; then
        # Send SIGTERM first, then wait briefly, then SIGKILL if still alive
        kill -TERM "${DOTNET_PID}" 2>/dev/null || true
        local waited=0
        while kill -0 "${DOTNET_PID}" 2>/dev/null && [[ ${waited} -lt 10 ]]; do
            sleep 1
            waited=$((waited + 1))
        done
        if kill -0 "${DOTNET_PID}" 2>/dev/null; then
            warn "Process did not exit gracefully. Forcing shutdown..."
            kill -KILL "${DOTNET_PID}" 2>/dev/null || true
        fi
    fi
    info "Stopped."
    exit 0
}

trap cleanup SIGINT SIGTERM

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------
preflight() {
    # Check .NET SDK
    if ! command -v dotnet &>/dev/null; then
        error ".NET SDK is not installed or not in PATH."
        error "Run './scripts/setup.sh' or 'make setup' to install it."

        # Check the default install location
        if [[ -d "${HOME}/.dotnet" ]]; then
            warn "Found .NET at ~/.dotnet -- try running:"
            warn "  export PATH=\"\${HOME}/.dotnet:\${PATH}\""
        fi

        exit 1
    fi

    # Check config file
    if [[ ! -f "${CONFIG_FILE}" ]]; then
        error "Configuration file not found: ${CONFIG_FILE}"
        error "Create it before running the agent."
        exit 1
    fi

    # Check project file
    if [[ ! -f "${PROJECT_FILE}" ]]; then
        error "Project file not found: ${PROJECT_FILE}"
        error "Are you running this script from the correct repository?"
        exit 1
    fi
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
    preflight

    local args=("$@")

    info "Starting FtpAgent..."
    info "Project:  ${PROJECT_FILE}"
    info "Config:   ${CONFIG_FILE}"
    if [[ ${#args[@]} -gt 0 ]]; then
        info "Args:     ${args[*]}"
    fi
    printf "\n"

    # Run dotnet in the background so we can capture its PID for cleanup
    cd "${PROJECT_ROOT}"
    if [[ ${#args[@]} -gt 0 ]]; then
        dotnet run --project "${PROJECT_FILE}" --configuration "${CONFIGURATION}" -- "${args[@]}" &
    else
        dotnet run --project "${PROJECT_FILE}" --configuration "${CONFIGURATION}" &
    fi
    DOTNET_PID=$!

    # Wait for the process (preserves exit code)
    wait "${DOTNET_PID}"
    exit_code=$?
    DOTNET_PID=""

    if [[ ${exit_code} -ne 0 ]]; then
        error "FtpAgent exited with code ${exit_code}."
    else
        info "FtpAgent finished successfully."
    fi

    exit ${exit_code}
}

main "$@"
