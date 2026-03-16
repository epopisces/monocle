"""
monocle/cli.py — Typer CLI entry point.

Commands are wired to real implementations in later milestones.
This module must be importable with no side-effects in M1.
"""
from __future__ import annotations

import logging

import typer

app = typer.Typer(name="monocle", help="Monocle personal knowledge system")
logger = logging.getLogger(__name__)


@app.command()
def serve(
    host: str | None = typer.Option(None, help="Override server.host from config"),
    port: int | None = typer.Option(None, help="Override server.port from config"),
) -> None:
    """Start the unified Monocle server (API + MCP + watcher + scheduler)."""
    import uvicorn
    from monocle.config import Settings

    settings = Settings()
    uvicorn.run(
        "monocle.main:app",
        host=host or settings.server.host,
        port=port or settings.server.port,
        reload=False,
    )


@app.command()
def dev(
    host: str | None = typer.Option(None, help="Override server.host from config"),
    port: int | None = typer.Option(None, help="Override server.port from config"),
) -> None:
    """Start Monocle in development mode (prefixed logging, auto-restart on crash)."""
    import os
    import uvicorn
    from monocle.config import Settings

    os.environ["MONOCLE_DEV"] = "true"
    settings = Settings()
    uvicorn.run(
        "monocle.main:app",
        host=host or settings.server.host,
        port=port or settings.server.port,
        reload=True,
        log_level="debug",
    )


@app.command()
def reindex(
    force: bool = typer.Option(False, "--force", help="Clear index and re-embed all notes"),
) -> None:
    """Re-index the vault (wired in M5)."""
    logger.info("reindex command — wired in M5")


@app.command("pull-models")
def pull_models() -> None:
    """Pull required Ollama models (wired in M6)."""
    logger.info("pull-models command — wired in M6")


@app.command()
def export(
    output: str = typer.Argument("export.zip", help="Output file path"),
) -> None:
    """Export the vault to a zip archive (wired in M14)."""
    logger.info("export command — wired in M14")


@app.command()
def versions(
    path: str = typer.Argument(..., help="Vault-relative path to note"),
) -> None:
    """List available versions for a note (wired in M14)."""
    logger.info("versions command — wired in M14")
