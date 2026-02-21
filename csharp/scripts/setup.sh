#!/usr/bin/env bash
# ============================================================================
#  FtpAgent - First-Time Setup Script for Linux VMs
#
#  This script is idempotent and safe to re-run. It will:
#    1. Install .NET 8 SDK (if not present)
#    2. Install git (if not present)
#    3. Install GitHub CLI (if not present)
#    4. Restore NuGet packages
#    5. Create development config from template
#    6. Verify the build compiles
# ============================================================================
set -euo pipefail

# Colors
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
RED='\033[0;31m'
BOLD='\033[1m'
RESET='\033[0m'

# Resolve the project root (parent of the scripts/ directory)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

SOLUTION="${PROJECT_ROOT}/FtpAgent.sln"
CONFIG_DIR="${PROJECT_ROOT}/config"
CONFIG_FILE="${CONFIG_DIR}/appsettings.json"
DEV_CONFIG_FILE="${CONFIG_DIR}/appsettings.Development.json"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
info()    { printf "${CYAN}[setup]${RESET} %s\n" "$*"; }
success() { printf "${GREEN}[setup]${RESET} %s\n" "$*"; }
warn()    { printf "${YELLOW}[setup]${RESET} %s\n" "$*"; }
error()   { printf "${RED}[setup]${RESET} %s\n" "$*" >&2; }

header() {
    printf "\n${BOLD}${CYAN}"
    printf "============================================================\n"
    printf "  FtpAgent - Environment Setup\n"
    printf "============================================================${RESET}\n\n"
}

# ---------------------------------------------------------------------------
# Step 1: Install .NET 8 SDK
# ---------------------------------------------------------------------------
install_dotnet() {
    info "Checking for .NET SDK..."

    if command -v dotnet &>/dev/null; then
        local version
        version="$(dotnet --version)"
        if [[ "${version}" == 8.* ]]; then
            success ".NET 8 SDK already installed (${version})."
            return
        else
            warn ".NET SDK found (${version}) but not .NET 8. Installing .NET 8..."
        fi
    else
        info ".NET SDK not found. Installing .NET 8 SDK..."
    fi

    local install_script
    install_script="$(mktemp)"
    curl -sSL https://dot.net/v1/dotnet-install.sh -o "${install_script}"
    chmod +x "${install_script}"
    bash "${install_script}" --channel 8.0
    rm -f "${install_script}"

    # Add to PATH for the current session if installed to the default location
    if [[ -d "${HOME}/.dotnet" ]]; then
        export DOTNET_ROOT="${HOME}/.dotnet"
        export PATH="${DOTNET_ROOT}:${DOTNET_ROOT}/tools:${PATH}"
    fi

    if command -v dotnet &>/dev/null; then
        success ".NET 8 SDK installed ($(dotnet --version))."
    else
        error "Failed to install .NET SDK. Please install manually:"
        error "  https://learn.microsoft.com/en-us/dotnet/core/install/linux"
        exit 1
    fi
}

# ---------------------------------------------------------------------------
# Step 2: Install git
# ---------------------------------------------------------------------------
install_git() {
    info "Checking for git..."

    if command -v git &>/dev/null; then
        success "git already installed ($(git --version))."
        return
    fi

    info "Installing git..."
    if command -v apt-get &>/dev/null; then
        sudo apt-get update -qq && sudo apt-get install -y -qq git
    elif command -v dnf &>/dev/null; then
        sudo dnf install -y git
    elif command -v yum &>/dev/null; then
        sudo yum install -y git
    elif command -v apk &>/dev/null; then
        sudo apk add git
    else
        error "Could not detect package manager. Please install git manually."
        exit 1
    fi

    success "git installed ($(git --version))."
}

# ---------------------------------------------------------------------------
# Step 3: Install GitHub CLI
# ---------------------------------------------------------------------------
install_gh() {
    info "Checking for GitHub CLI (gh)..."

    if command -v gh &>/dev/null; then
        success "GitHub CLI already installed ($(gh --version | head -n1))."
        return
    fi

    info "Installing GitHub CLI..."
    if command -v apt-get &>/dev/null; then
        # Official GitHub CLI repo for Debian/Ubuntu
        (type -p wget >/dev/null || (sudo apt-get update -qq && sudo apt-get install -y -qq wget)) \
            && sudo mkdir -p -m 755 /etc/apt/keyrings \
            && wget -qO- https://cli.github.com/packages/githubcli-archive-keyring.gpg \
                | sudo tee /etc/apt/keyrings/githubcli-archive-keyring.gpg >/dev/null \
            && sudo chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg \
            && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
                | sudo tee /etc/apt/sources.list.d/github-cli.list >/dev/null \
            && sudo apt-get update -qq \
            && sudo apt-get install -y -qq gh
    elif command -v dnf &>/dev/null; then
        sudo dnf install -y 'dnf-command(config-manager)' \
            && sudo dnf config-manager --add-repo https://cli.github.com/packages/rpm/gh-cli.repo \
            && sudo dnf install -y gh
    elif command -v yum &>/dev/null; then
        sudo yum-config-manager --add-repo https://cli.github.com/packages/rpm/gh-cli.repo \
            && sudo yum install -y gh
    else
        warn "Could not auto-install GitHub CLI. Install manually:"
        warn "  https://github.com/cli/cli/blob/trunk/docs/install_linux.md"
        return
    fi

    if command -v gh &>/dev/null; then
        success "GitHub CLI installed ($(gh --version | head -n1))."
    else
        warn "GitHub CLI installation may have failed. Install manually if needed."
    fi
}

# ---------------------------------------------------------------------------
# Step 4: Restore NuGet packages
# ---------------------------------------------------------------------------
restore_packages() {
    info "Restoring NuGet packages..."
    dotnet restore "${SOLUTION}"
    success "NuGet packages restored."
}

# ---------------------------------------------------------------------------
# Step 5: Create development config
# ---------------------------------------------------------------------------
create_dev_config() {
    info "Checking for development config..."

    if [[ -f "${DEV_CONFIG_FILE}" ]]; then
        success "Development config already exists: ${DEV_CONFIG_FILE}"
        return
    fi

    if [[ ! -f "${CONFIG_FILE}" ]]; then
        error "Base config not found: ${CONFIG_FILE}"
        error "Cannot create development config."
        exit 1
    fi

    info "Creating development config from ${CONFIG_FILE}..."
    cp "${CONFIG_FILE}" "${DEV_CONFIG_FILE}"
    success "Created ${DEV_CONFIG_FILE}"
    warn "Edit this file with your local development settings."
}

# ---------------------------------------------------------------------------
# Step 6: Verify build
# ---------------------------------------------------------------------------
verify_build() {
    info "Verifying the solution builds..."
    if dotnet build "${SOLUTION}" --configuration Release --no-restore; then
        success "Build verification passed."
    else
        error "Build failed. Please check the errors above."
        exit 1
    fi
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
    header

    cd "${PROJECT_ROOT}"

    install_dotnet
    printf "\n"
    install_git
    printf "\n"
    install_gh
    printf "\n"
    restore_packages
    printf "\n"
    create_dev_config
    printf "\n"
    verify_build

    printf "\n"
    printf "${BOLD}${GREEN}============================================================${RESET}\n"
    printf "${BOLD}${GREEN}  Setup complete!${RESET}\n"
    printf "${BOLD}${GREEN}============================================================${RESET}\n"
    printf "\n"
    printf "  ${BOLD}Next steps:${RESET}\n"
    printf "    1. Edit ${CYAN}config/appsettings.Development.json${RESET} with your settings\n"
    printf "    2. Run tests:       ${CYAN}make test${RESET}\n"
    printf "    3. Start the agent: ${CYAN}make run${RESET}\n"
    printf "    4. Try dry-run:     ${CYAN}make dry-run${RESET}\n"
    printf "    5. See all targets: ${CYAN}make help${RESET}\n"
    printf "\n"
}

main "$@"
