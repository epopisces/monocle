"""
monocle/cli.py — Typer CLI entry point.

All commands are fully wired.  Run:
  uv run python -m monocle --help
"""
from __future__ import annotations

import asyncio
import logging
import os
import zipfile
from pathlib import Path

import typer

app = typer.Typer(name="monocle", help="Monocle personal knowledge system")
versions_app = typer.Typer(help="Manage note version history")
app.add_typer(versions_app, name="versions")

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_settings():
    """Load Settings, wiring in config.yaml + .env."""
    from monocle.config import Settings
    return Settings()


def _make_vault(settings):
    """Create a VaultLayer from configuration."""
    from monocle.vault import VaultLayer
    return VaultLayer(settings.vault.path)


def _make_index(settings):
    """Create the configured IndexLayer."""
    from monocle.index import get_index
    return get_index(settings)


# ---------------------------------------------------------------------------
# serve
# ---------------------------------------------------------------------------


@app.command()
def serve(
    host: str | None = typer.Option(None, help="Override server.host from config"),
    port: int | None = typer.Option(None, help="Override server.port from config"),
) -> None:
    """Start the unified Monocle server (API + MCP + watcher + scheduler)."""
    import uvicorn

    settings = _load_settings()
    uvicorn.run(
        "monocle.main:app",
        host=host or settings.server.host,
        port=port or settings.server.port,
        reload=False,
    )


# ---------------------------------------------------------------------------
# dev
# ---------------------------------------------------------------------------


@app.command()
def dev(
    host: str | None = typer.Option(None, help="Override server.host from config"),
    port: int | None = typer.Option(None, help="Override server.port from config"),
) -> None:
    """Start Monocle in development mode (prefixed logging, auto-restart on crash)."""
    import uvicorn

    os.environ["MONOCLE_DEV"] = "true"
    settings = _load_settings()

    # Print telemetry status block before handing off to uvicorn
    if settings.telemetry.enabled:
        otlp_ep = settings.telemetry.otlp_endpoint or "disabled"
    else:
        otlp_ep = "disabled"
    typer.echo(
        f"[TELEMETRY] OTLP endpoint: {otlp_ep} | "
        f"log_level: {settings.telemetry.log_level.upper()} | "
        f"format: {settings.telemetry.log_format}"
    )

    uvicorn.run(
        "monocle.main:app",
        host=host or settings.server.host,
        port=port or settings.server.port,
        reload=True,
        log_level="debug",
    )


# ---------------------------------------------------------------------------
# reindex
# ---------------------------------------------------------------------------


@app.command()
def reindex(
    force: bool = typer.Option(False, "--force", help="Clear index and re-embed all notes"),
) -> None:
    """Re-index the vault (stale detection or full rebuild with --force)."""
    import asyncio

    from monocle.agents.reindex import ReindexAgent

    settings = _load_settings()
    vault = _make_vault(settings)
    index = _make_index(settings)

    # Attempt to wire a real embed function when AI is available.
    embed_fn = None
    try:
        from monocle.ai import get_provider
        ai = get_provider(settings)
        # Wrap the coroutine embed function as a sync callable for ReindexAgent.
        # asyncio.run() creates a fresh event loop per call, which is required
        # when called from a thread-pool thread (asyncio.to_thread) because
        # asyncio.get_event_loop() raises RuntimeError in threads on Python 3.10+.
        def embed_fn(text: str) -> list[float]:  # type: ignore[return-value]
            return asyncio.run(ai.embed(text))
    except Exception as exc:
        typer.echo(f"[WARNING] Could not initialise AI provider for embeddings: {exc}", err=True)
        typer.echo("[INFO] Proceeding with MemoryIndex-compatible mode (no embeddings).", err=True)

    agent = ReindexAgent(embed_fn=embed_fn)

    async def _run() -> int:
        return await agent.run(vault, index, force=force)

    count = asyncio.run(_run())
    typer.echo(f"Re-indexed {count} note(s).")


# ---------------------------------------------------------------------------
# pull-models
# ---------------------------------------------------------------------------


@app.command("pull-models")
def pull_models() -> None:
    """Pull all required Ollama models declared in config."""
    settings = _load_settings()
    if settings.ai.provider != "ollama":
        typer.echo(
            f"Provider is '{settings.ai.provider}', not 'ollama'. Nothing to pull."
        )
        raise typer.Exit()

    try:
        import ollama  # type: ignore[import]
    except ImportError:
        typer.echo("[ERROR] ollama Python package not installed.", err=True)
        raise typer.Exit(code=1)

    models_to_pull = list({settings.ai.chat_model, settings.ai.embed_model})
    typer.echo(f"Pulling {len(models_to_pull)} model(s) from Ollama …")
    for model_name in models_to_pull:
        typer.echo(f"  → {model_name} …", nl=False)
        try:
            ollama.pull(model_name)
            typer.echo(" done")
        except Exception as exc:
            typer.echo(f" FAILED: {exc}", err=True)


# ---------------------------------------------------------------------------
# stats
# ---------------------------------------------------------------------------


@app.command()
def stats() -> None:
    """Print vault and index statistics to stdout."""
    import asyncio

    settings = _load_settings()
    vault = _make_vault(settings)
    index = _make_index(settings)

    async def _gather() -> dict:
        index_stats = await asyncio.to_thread(index.get_stats)
        page = await asyncio.to_thread(vault.list_notes, None, None, None, "updated", 100_000, 0)
        by_type: dict[str, int] = {}
        by_domain: dict[str, int] = {}
        pending = 0
        for ref in page.items:
            by_type[ref.type] = by_type.get(ref.type, 0) + 1
            by_domain[ref.domain] = by_domain.get(ref.domain, 0) + 1
            if ref.review_status == "pending":
                pending += 1
        return {
            "total_notes": page.total,
            "total_chunks": index_stats.total_chunks,
            "by_type": by_type,
            "by_domain": by_domain,
            "pending_review": pending,
        }

    data = asyncio.run(_gather())

    typer.echo(f"Notes          : {data['total_notes']}")
    typer.echo(f"Index chunks   : {data['total_chunks']}")
    typer.echo(f"Pending review : {data['pending_review']}")
    if data["by_type"]:
        typer.echo("By type        :")
        for k, v in sorted(data["by_type"].items()):
            typer.echo(f"  {k:<20} {v}")
    if data["by_domain"]:
        typer.echo("By domain      :")
        for k, v in sorted(data["by_domain"].items()):
            typer.echo(f"  {k:<20} {v}")


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------


@app.command()
def search(
    query: str = typer.Argument(..., help="Search query"),
    limit: int = typer.Option(5, "--limit", "-n", help="Number of results to return"),
) -> None:
    """Semantic search across the vault; pretty-print results."""
    import asyncio

    settings = _load_settings()
    index = _make_index(settings)

    async def _search() -> list[dict]:
        try:
            from monocle.ai import get_provider
            ai = get_provider(settings)
            embedding = await ai.embed(query)
        except Exception as exc:
            typer.echo(f"[ERROR] Could not embed query: {exc}", err=True)
            raise typer.Exit(code=1)

        return await asyncio.to_thread(index.search, embedding, limit)

    results = asyncio.run(_search())

    if not results:
        typer.echo("No results found.")
        return

    for i, hit in enumerate(results, 1):
        file_path = hit.get("file_path", "?")
        score = hit.get("score", 0.0)
        snippet = (hit.get("text") or "")[:160].replace("\n", " ")
        typer.echo(f"{i}. [{score:.3f}] {file_path}")
        if snippet:
            typer.echo(f"   {snippet}")


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------


@app.command()
def export(
    output: str = typer.Option("export.zip", "--output", "-o", help="Destination zip file path"),
) -> None:
    """Export the vault to a zip archive (excludes .versions/, .trash/, data/)."""
    settings = _load_settings()
    vault_root = Path(settings.vault.path).resolve()

    # Directories to exclude (relative prefixes inside vault root)
    excluded_top = {".versions", ".trash"}

    output_path = Path(output).resolve()
    total = 0

    with zipfile.ZipFile(str(output_path), "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file in vault_root.rglob("*"):
            if not file.is_file():
                continue
            rel = file.relative_to(vault_root)
            # Exclude hidden system directories
            if rel.parts[0] in excluded_top:
                continue
            # Exclude macOS cruft
            if rel.name == ".DS_Store":
                continue
            # Use forward slashes in arcnames so archives are portable across
            # platforms (Windows Path.relative_to returns backslash separators).
            zf.write(str(file), str(rel).replace(os.sep, "/"))
            total += 1

    typer.echo(f"Exported {total} file(s) to {output_path}")


# ---------------------------------------------------------------------------
# versions subcommands
# ---------------------------------------------------------------------------


@versions_app.command("list")
def versions_list(
    file_path: str = typer.Argument(..., help="Vault-relative path to the note"),
) -> None:
    """List all stored version timestamps for a note (oldest first)."""
    settings = _load_settings()
    vault = _make_vault(settings)

    try:
        timestamps = vault.list_versions(file_path)
    except Exception as exc:
        typer.echo(f"[ERROR] {exc}", err=True)
        raise typer.Exit(code=1)

    if not timestamps:
        typer.echo(f"No versions found for '{file_path}'.")
        return

    typer.echo(f"Versions for '{file_path}' ({len(timestamps)} total):")
    for ts in timestamps:
        typer.echo(f"  {ts}")


@versions_app.command("restore")
def versions_restore(
    file_path: str = typer.Argument(..., help="Vault-relative path to the note"),
    timestamp: str = typer.Argument(..., help="Timestamp string from 'versions list'"),
) -> None:
    """Restore a note from a historical version."""
    settings = _load_settings()
    vault = _make_vault(settings)

    try:
        vault.restore_version(file_path, timestamp)
    except Exception as exc:
        typer.echo(f"[ERROR] {exc}", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"Restored '{file_path}' from version {timestamp}.")


# ---------------------------------------------------------------------------
# Reserved stubs (future optional process separation)
# ---------------------------------------------------------------------------


@app.command()
def watch() -> None:
    """[RESERVED] Start only the inbox watcher process (future use)."""
    typer.echo("[INFO] 'watch' is reserved for future optional process separation.")


@app.command()
def capture() -> None:
    """[RESERVED] Start only the capture server process (future use)."""
    typer.echo("[INFO] 'capture' is reserved for future optional process separation.")
