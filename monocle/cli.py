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


#endregion

# ---------------------------------------------------------------------------
#region #*   Helpers
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


#endregion

# ---------------------------------------------------------------------------
#region #*   serve
# ---------------------------------------------------------------------------


@app.command()
def serve(
    host: str | None = typer.Option(None, help="Override server.host from config"),
    port: int | None = typer.Option(None, help="Override server.port from config"),
    separate_processes: bool = typer.Option(
        False,
        "--separate-processes",
        help="Run watcher and scheduler as separate OS processes (Phase 3+)",
    ),
) -> None:
    """Start the unified Monocle server (API + MCP + watcher + scheduler)."""
    import uvicorn

    if separate_processes:
        os.environ["MONOCLE_SEPARATE_PROCESSES"] = "1"

    settings = _load_settings()
    uvicorn.run(
        "monocle.main:app",
        host=host or settings.server.host,
        port=port or settings.server.port,
        reload=False,
    )


#endregion

# ---------------------------------------------------------------------------
#region #*   dev
# ---------------------------------------------------------------------------


@app.command()
def dev(
    host: str | None = typer.Option(None, help="Override server.host from config"),
    port: int | None = typer.Option(None, help="Override server.port from config"),
    separate_processes: bool = typer.Option(
        False,
        "--separate-processes",
        help="Run watcher and scheduler as separate OS processes (Phase 3+)",
    ),
) -> None:
    """Start Monocle in development mode (prefixed logging, auto-restart on crash)."""
    import uvicorn

    os.environ["MONOCLE_DEV"] = "true"
    if separate_processes:
        os.environ["MONOCLE_SEPARATE_PROCESSES"] = "1"
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


#endregion

# ---------------------------------------------------------------------------
#region #*   reindex
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


#endregion

# ---------------------------------------------------------------------------
#region #*   pull-models
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
    failed_count = 0
    for model_name in models_to_pull:
        typer.echo(f"  → {model_name} …", nl=False)
        try:
            ollama.pull(model_name)
            typer.echo(" done")
        except Exception as exc:
            typer.echo(f" FAILED: {exc}", err=True)
            failed_count += 1
    
    if failed_count > 0:
        typer.echo(f"\n[ERROR] {failed_count}/{len(models_to_pull)} pull(s) failed.", err=True)
        raise typer.Exit(code=1)


#endregion

# ---------------------------------------------------------------------------
#region #*   stats
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
        # Fetch all notes using pagination (limit 100k per page)
        by_type: dict[str, int] = {}
        by_domain: dict[str, int] = {}
        pending = 0
        total_notes = 0
        offset = 0
        page_size = 100_000
        
        while offset == 0 or offset < total_notes:
            page = await asyncio.to_thread(vault.list_notes, None, None, None, "updated", page_size, offset)
            if offset == 0:
                total_notes = page.total
            
            for ref in page.items:
                by_type[ref.type] = by_type.get(ref.type, 0) + 1
                by_domain[ref.domain] = by_domain.get(ref.domain, 0) + 1
                if ref.review_status == "pending":
                    pending += 1
            
            offset += len(page.items)
            if len(page.items) < page_size:
                break  # Last page; fewer items than page_size
        
        return {
            "total_notes": total_notes,
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


#endregion

# ---------------------------------------------------------------------------
#region #*   search
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


#endregion

# ---------------------------------------------------------------------------
#region #*   export
# ---------------------------------------------------------------------------


@app.command()
def export(
    output: str = typer.Option("export.zip", "--output", "-o", help="Destination zip file path"),
) -> None:
    """Export the vault to a zip archive (excludes .versions/, .trash/, macOS metadata)."""
    settings = _load_settings()
    vault_root = Path(settings.vault.path).resolve()

    output_path = Path(output).resolve()

    # Prevent output path from being inside vault (avoid self-referential archive)
    try:
        output_path.relative_to(vault_root)
        typer.echo(
            f"[ERROR] Output path must be outside the vault directory.\n"
            f"  vault root: {vault_root}\n"
            f"  output path: {output_path}",
            err=True,
        )
        raise typer.Exit(code=1)
    except ValueError:
        # This is expected — output_path is NOT inside vault_root
        pass

    # Directories to exclude (top-level prefixes inside vault root)
    excluded_top = {".versions", ".trash"}

    total = 0

    with zipfile.ZipFile(str(output_path), "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file in vault_root.rglob("*"):
            if not file.is_file():
                continue
            rel = file.relative_to(vault_root)
            # Exclude Monocle system directories
            if rel.parts[0] in excluded_top:
                continue
            # Exclude macOS metadata
            if rel.name == ".DS_Store":
                continue
            # Use forward slashes in arcnames so archives are portable across
            # platforms (Windows Path.relative_to returns backslash separators).
            zf.write(str(file), str(rel).replace(os.sep, "/"))
            total += 1

    typer.echo(f"Exported {total} file(s) to {output_path}")


#endregion

# ---------------------------------------------------------------------------
#region #*   versions subcommands
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


#endregion

# ---------------------------------------------------------------------------
#region #*   watch — standalone inbox watcher (Phase 3+ separate-process entry point)
# ---------------------------------------------------------------------------


@app.command()
def watch() -> None:
    """Start only the inbox file watcher as a standalone process.

    Used by ProcessManager when ``server.separate_processes: true``.
    Can also be launched directly for debugging the ingest pipeline.
    """
    settings = _load_settings()

    if not settings.vault.watch:
        typer.echo("[WATCHER] vault.watch=false in config; nothing to do.")
        raise typer.Exit()

    from monocle.telemetry import configure_telemetry

    configure_telemetry(settings)

    async def _run() -> None:
        from monocle.ingest.failed_registry import FailedIngestRegistry
        from monocle.ingest.plugin import IngestPluginRegistry
        from monocle.ingest.plugins import register_default_plugins
        from monocle.services.ingest_sessions import IngestSessionStore
        from monocle.watcher import InboxWatcher

        vault_ = _make_vault(settings)
        index_ = _make_index(settings)

        ai_ = None
        try:
            from monocle.ai import get_provider

            ai_ = get_provider(settings)
        except Exception as exc:
            typer.echo(f"[WATCHER] AI provider init failed (non-fatal): {exc}", err=True)

        registry_ = IngestPluginRegistry.get()
        if not registry_.plugins:
            register_default_plugins(registry_)

        failed_registry_ = FailedIngestRegistry()
        ingest_session_store = IngestSessionStore(settings)

        def _infer_source(file_path: str) -> str:
            suffix = Path(file_path).suffix.lower()
            if suffix in {".webm", ".mp3", ".wav", ".m4a", ".flac"}:
                return "voice"
            return "web"

        async def _inbox_callback(file_path: str) -> None:
            from pathlib import Path as _Path

            try:
                path = _Path(file_path)
                if path.suffix.lower() == ".md":
                    content = await asyncio.to_thread(path.read_text, encoding="utf-8")
                    if content.startswith("---") and "approval_mode:" in content[:3000]:
                        logger.info("[WATCHER] Skipped re-ingest of Monocle note: %s", file_path)
                        return

                await asyncio.to_thread(
                    ingest_session_store.create_inbox_session,
                    file_path,
                    request_source=_infer_source(file_path),
                )
                logger.info("[WATCHER] Ingest session captured: %s", file_path)
            except Exception as exc:
                logger.error(
                    "[WATCHER] Ingest failed for %s: %s", file_path, exc, exc_info=True
                )

        watcher_ = InboxWatcher(
            inbox_path=settings.vault.inbox_path,
            ingest_callback=_inbox_callback,
            debounce_s=settings.vault.debounce_ms / 1000,
        )
        await watcher_.start()
        typer.echo(
            f"[WATCHER] Watching {settings.vault.inbox_path} — press Ctrl+C to stop"
        )
        try:
            await asyncio.Event().wait()  # block until cancelled
        except asyncio.CancelledError:
            pass
        finally:
            await watcher_.stop()

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        typer.echo("\n[WATCHER] Stopped.")


#endregion

# ---------------------------------------------------------------------------
#region #*   scheduler — standalone APScheduler (Phase 3+ separate-process entry point)
# ---------------------------------------------------------------------------


@app.command()
def scheduler() -> None:
    """Start only the APScheduler as a standalone process.

    Used by ProcessManager when ``server.separate_processes: true``.
    Can also be launched directly for debugging scheduled jobs.
    """
    settings = _load_settings()

    from monocle.telemetry import configure_telemetry

    configure_telemetry(settings)

    async def _run() -> None:
        from monocle.agents.reindex import ReindexAgent
        from monocle.agents.scheduler import MonocleScheduler

        vault_ = _make_vault(settings)
        index_ = _make_index(settings)

        ai_ = None
        try:
            from monocle.ai import get_provider

            ai_ = get_provider(settings)
        except Exception as exc:
            typer.echo(f"[SCHEDULER] AI provider init failed (non-fatal): {exc}", err=True)

        reindex_agent_ = ReindexAgent(
            chunk_size=settings.index.chunk_size_tokens,
            chunk_overlap=settings.index.chunk_overlap_tokens,
            embed_fn=ai_.embed if ai_ is not None else None,
        )

        sched = MonocleScheduler(settings)
        await sched.start()

        if settings.agents.reindex.enabled:

            async def _do_reindex() -> None:
                logger.info("[SCHEDULER] Scheduled re-index starting")
                await reindex_agent_.run(vault_, index_)
                logger.info("[SCHEDULER] Scheduled re-index complete")

            sched.add_cron_job("reindex", _do_reindex, settings.agents.reindex.cron)

        if settings.agents.weekly_summary.enabled:
            from monocle.agents.weekly_summary import WeeklySummaryAgent

            _ws_agent = WeeklySummaryAgent()

            async def _do_weekly() -> None:
                if ai_ is None:
                    logger.warning(
                        "[SCHEDULER] Weekly summary skipped — AI not available"
                    )
                    return
                try:
                    fp = await _ws_agent.run(vault_, index_, ai_, settings)
                    logger.info("[SCHEDULER] Weekly summary written: %s", fp)
                except Exception as exc:
                    logger.error("[SCHEDULER] Weekly summary failed: %s", exc)

            sched.add_cron_job(
                "weekly_summary", _do_weekly, settings.agents.weekly_summary.cron
            )

        typer.echo("[SCHEDULER] APScheduler running — press Ctrl+C to stop")
        try:
            await asyncio.Event().wait()  # block until cancelled
        except asyncio.CancelledError:
            pass
        finally:
            await sched.stop()

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        typer.echo("\n[SCHEDULER] Stopped.")


#endregion

# ---------------------------------------------------------------------------
#region #*   capture — API-only server (Phase 3+ separate-process entry point)
# ---------------------------------------------------------------------------


@app.command()
def capture(
    host: str | None = typer.Option(None, help="Override server.host from config"),
    port: int | None = typer.Option(None, help="Override server.port from config"),
) -> None:
    """Start only the capture API server (no watcher or scheduler).

    Advanced/debug use case: run the API server without any background
    components (inbox watcher, scheduler). The watcher and scheduler can be
    run separately via ``monocle watch`` and ``monocle scheduler``.

    Typical users should use ``monocle serve`` or ``monocle serve --separate-processes``
    instead — those commands handle the full orchestration automatically.
    """
    import uvicorn

    # Signal main.py lifespan to skip creating the inline watcher/scheduler
    # because they are managed externally (by ProcessManager subprocesses or direct launch).
    os.environ["MONOCLE_COMPONENT"] = "capture"

    settings = _load_settings()
    uvicorn.run(
        "monocle.main:app",
        host=host or settings.server.host,
        port=port or settings.server.port,
        reload=False,
    )
