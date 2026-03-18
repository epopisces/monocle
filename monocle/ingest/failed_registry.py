"""
monocle/ingest/failed_registry.py — Failed-ingest registry.

Persists failed-ingest records to ``data/failed_ingests.json`` so the UI
can display a list of errors and offer a retry flow.

Design:
- JSON array of dicts; Python stdlib ``json`` only (no extra dependencies).
- Loaded into memory at startup (``FailedIngestRegistry.__init__``).
- Written atomically (temp file + ``os.replace``) on every mutation.
- Each entry includes: ``id`` (UUID4 hex), ``timestamp`` (ISO 8601),
  ``source``, ``content_preview`` (first 200 chars), ``error_message``,
  ``sidecar_path`` (vault-relative .error.md path), ``step`` (pipeline step
  number where the failure occurred), ``status`` (``"failed"``/``"retried"``).
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_REGISTRY_PATH = Path("data/failed_ingests.json")


class FailedIngestRegistry:
    """In-memory registry of failed ingest records backed by a JSON file.

    Args:
        path: Path to the JSON file.  Created (with parent dirs) on first write
              if it does not exist.
    """

    def __init__(self, path: str | Path = _DEFAULT_REGISTRY_PATH) -> None:
        self._path = Path(path)
        self._lock = threading.Lock()
        self._records: list[dict[str, Any]] = self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add(
        self,
        *,
        source: str,
        content_preview: str,
        error_message: str,
        sidecar_path: str | None,
        step: int,
    ) -> str:
        """Record a new failed ingest.

        Returns:
            The UUID ``id`` of the new record.
        """
        record_id = uuid.uuid4().hex
        record: dict[str, Any] = {
            "id": record_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": source,
            "content_preview": content_preview[:200],
            "error_message": str(error_message)[:1000],
            "sidecar_path": sidecar_path,
            "step": step,
            "status": "failed",
        }
        with self._lock:
            self._records.append(record)
            self._save()
        logger.info(
            "[INGEST] Failed-ingest recorded (id=%s, step=%d, source=%s)",
            record_id,
            step,
            source,
        )
        return record_id

    def get_all(self) -> list[dict[str, Any]]:
        """Return all records newest-first."""
        with self._lock:
            return sorted(self._records, key=lambda r: r.get("timestamp", ""), reverse=True)

    def get(self, record_id: str) -> dict[str, Any] | None:
        """Return the record with *record_id*, or ``None`` if not found."""
        with self._lock:
            for rec in self._records:
                if rec.get("id") == record_id:
                    return rec
        return None

    def mark_retried(self, record_id: str) -> bool:
        """Mark a record as retried (status → ``"retried"``).

        Returns:
            True if the record was found and updated; False otherwise.
        """
        with self._lock:
            for rec in self._records:
                if rec.get("id") == record_id:
                    rec["status"] = "retried"
                    self._save()
                    logger.debug("FailedIngestRegistry: marked %s as retried", record_id)
                    return True
        return False

    def delete(self, record_id: str) -> bool:
        """Remove the record with *record_id* from the list.

        The underlying ``.error.md`` sidecar file is **not** deleted.

        Returns:
            True if found and removed; False otherwise.
        """
        with self._lock:
            original_len = len(self._records)
            self._records = [r for r in self._records if r.get("id") != record_id]
            if len(self._records) < original_len:
                self._save()
                logger.debug("FailedIngestRegistry: deleted record %s", record_id)
                return True
        return False

    def count(self) -> int:
        """Return the total number of records (all statuses)."""
        with self._lock:
            return len(self._records)

    def count_failed(self) -> int:
        """Return the count of records with status ``'failed'``."""
        with self._lock:
            return sum(1 for r in self._records if r.get("status") == "failed")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load(self) -> list[dict[str, Any]]:
        """Load records from disk, returning an empty list on any error."""
        if not self._path.exists():
            return []
        try:
            with open(self._path, encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, list):
                return data
            logger.warning(
                "FailedIngestRegistry: unexpected data type in %s", self._path
            )
            return []
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "FailedIngestRegistry: could not load %s: %s", self._path, exc
            )
            return []

    def _save(self) -> None:
        """Atomically write current records to disk."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(
            suffix=".json", prefix="failed_ingests_tmp_", dir=str(self._path.parent)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(self._records, fh, indent=2, ensure_ascii=False)
            os.replace(tmp, str(self._path))
            tmp = None  # replace succeeded; skip cleanup
        except Exception as exc:  # noqa: BLE001
            logger.error("FailedIngestRegistry: save failed: %s", exc)
        finally:
            if tmp and os.path.exists(tmp):
                os.unlink(tmp)
