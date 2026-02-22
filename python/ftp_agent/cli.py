"""Typer CLI for FTP Agent."""

from __future__ import annotations

import asyncio

import structlog
import typer

from ftp_agent import __version__

log = structlog.get_logger()

app = typer.Typer(
    name="ftp-agent",
    help="Autonomous DevOps migration agent — LLM-powered config translation.",
    no_args_is_help=True,
)
llm_app = typer.Typer(name="llm", help="LLM provider management.")
app.add_typer(llm_app)


def _configure_logging(verbose: bool = False, *, serve_mode: bool = False) -> None:
    import logging

    processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
    ]
    if serve_mode:
        from ftp_agent.server import ws_log_processor

        processors.append(ws_log_processor)
    processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.DEBUG if verbose else logging.INFO,
        ),
    )


@app.callback()
def callback(
    version: bool = typer.Option(False, "--version", "-V", help="Show version and exit."),
) -> None:
    if version:
        typer.echo(f"ftp-agent {__version__}")
        raise typer.Exit


@app.command()
def run(
    dry_run: bool = typer.Option(False, "--dry-run", help="Stub all external services."),
    batch_size: int | None = typer.Option(None, "--batch-size", "-b", help="Override batch size."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Debug logging."),
) -> None:
    """Run the autonomous migration agent."""
    _configure_logging(verbose)

    async def _run() -> None:
        from ftp_agent.app import create_app
        from ftp_agent.config.settings import AppSettings

        settings = AppSettings()
        if batch_size is not None:
            settings.agent.batch_size = batch_size

        app_instance = create_app(settings, dry_run=dry_run)

        try:
            report = await app_instance.orchestrator.run()
            typer.echo(report.to_summary())
        finally:
            await app_instance.state_store.close()
            await app_instance.close()

    asyncio.run(_run())


@app.command()
def status(
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Show current migration status from the database."""
    _configure_logging(verbose)

    async def _status() -> None:
        from ftp_agent.config.settings import AppSettings
        from ftp_agent.state.store import StateStore

        settings = AppSettings()
        async with StateStore(settings.agent.state_database_path) as store:
            report = await store.generate_report()
            typer.echo(report.to_summary())

    asyncio.run(_status())


@app.command()
def report(
    format: str = typer.Option("table", "--format", "-f", help="Output format: table or json."),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Generate a migration report."""
    _configure_logging(verbose)

    async def _report() -> None:
        import json as json_mod

        from ftp_agent.config.settings import AppSettings
        from ftp_agent.state.store import StateStore

        settings = AppSettings()
        async with StateStore(settings.agent.state_database_path) as store:
            rpt = await store.generate_report()

            if format == "json":
                data = {
                    "generated_at": rpt.generated_at.isoformat(),
                    "total_files": rpt.total_files,
                    "succeeded": rpt.succeeded,
                    "failed": rpt.failed,
                    "pending": rpt.pending,
                    "success_rate": rpt.success_rate,
                }
                typer.echo(json_mod.dumps(data, indent=2))
            else:
                typer.echo(rpt.to_summary())

    asyncio.run(_report())


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Bind address."),
    port: int = typer.Option(8000, "--port", "-p", help="Port."),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Start the FastAPI dashboard server."""
    _configure_logging(verbose, serve_mode=True)

    import uvicorn

    uvicorn.run(
        "ftp_agent.server:create_fastapi_app",
        host=host,
        port=port,
        factory=True,
        log_level="debug" if verbose else "info",
    )


@llm_app.command("test")
def llm_test(
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Test the configured LLM provider with a simple prompt."""
    _configure_logging(verbose)

    async def _test() -> None:
        from ftp_agent.config.settings import AppSettings
        from ftp_agent.llm.factory import create_llm_provider
        from ftp_agent.llm.protocol import LLMMessage

        settings = AppSettings()
        provider = create_llm_provider(settings.llm)

        typer.echo(f"Provider: {provider.provider_name}")
        typer.echo(f"Model: {provider.model_name}")

        healthy = await provider.health()
        typer.echo(f"Health: {'OK' if healthy else 'FAILED'}")

        if healthy:
            resp = await provider.chat(
                [
                    LLMMessage(role="user", content="Say hello in one sentence."),
                ]
            )
            typer.echo(f"Response: {resp.content}")
            typer.echo(f"Tokens: {resp.usage.total_tokens}")

        if hasattr(provider, "close"):
            await provider.close()

    asyncio.run(_test())


@llm_app.command("list-models")
def llm_list_models(
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """List available models (Ollama only)."""
    _configure_logging(verbose)

    async def _list() -> None:
        from ftp_agent.config.settings import AppSettings, LLMProviderType

        settings = AppSettings()
        if settings.llm.provider != LLMProviderType.OLLAMA:
            typer.echo("list-models is only supported for the Ollama provider.")
            raise typer.Exit(1)

        from ftp_agent.llm.ollama import OllamaProvider

        provider = OllamaProvider(settings.llm.ollama)
        models = await provider.list_models()
        if models:
            typer.echo("Available models:")
            for m in models:
                typer.echo(f"  - {m}")
        else:
            typer.echo("No models found. Pull one with: ollama pull llama3.3")
        await provider.close()

    asyncio.run(_list())


def main() -> None:
    app()
