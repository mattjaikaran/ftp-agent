# FTP Agent (Python)

Autonomous DevOps migration system — LLM-powered SFTP/Exchange config translation.

Python 3.12+ rewrite of the C# FTP Agent with multi-LLM provider support, pluggable services, Typer CLI, FastAPI dashboard, and React frontend.

## Quick Start

```bash
# Install dependencies
uv sync --extra dev

# Run in dry-run mode
uv run ftp-agent run --dry-run

# Start the dashboard
uv run ftp-agent serve

# Run tests
uv run pytest
```
