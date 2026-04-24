"""Application activity counters used for idle-gated background work."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from threading import Lock
from typing import Iterator


@dataclass(frozen=True)
class ActivitySnapshot:
    active_chat_streams: int
    active_foreground_writes: int
    active_ingest_reviews: int

    @property
    def is_idle(self) -> bool:
        return (
            self.active_chat_streams == 0
            and self.active_foreground_writes == 0
            and self.active_ingest_reviews == 0
        )


class ActivityMonitor:
    def __init__(self) -> None:
        self._lock = Lock()
        self._active_chat_streams = 0
        self._active_foreground_writes = 0
        self._active_ingest_reviews = 0

    @contextmanager
    def track_chat_stream(self) -> Iterator[None]:
        self._increment("chat")
        try:
            yield
        finally:
            self._decrement("chat")

    @contextmanager
    def track_foreground_write(self) -> Iterator[None]:
        self._increment("write")
        try:
            yield
        finally:
            self._decrement("write")

    def snapshot(self) -> ActivitySnapshot:
        with self._lock:
            return ActivitySnapshot(
                active_chat_streams=self._active_chat_streams,
                active_foreground_writes=self._active_foreground_writes,
                active_ingest_reviews=self._active_ingest_reviews,
            )

    def is_idle(self) -> bool:
        return self.snapshot().is_idle

    def _increment(self, kind: str) -> None:
        with self._lock:
            if kind == "chat":
                self._active_chat_streams += 1
            elif kind == "write":
                self._active_foreground_writes += 1
            elif kind == "ingest_review":
                self._active_ingest_reviews += 1

    def _decrement(self, kind: str) -> None:
        with self._lock:
            if kind == "chat":
                self._active_chat_streams = max(0, self._active_chat_streams - 1)
            elif kind == "write":
                self._active_foreground_writes = max(0, self._active_foreground_writes - 1)
            elif kind == "ingest_review":
                self._active_ingest_reviews = max(0, self._active_ingest_reviews - 1)