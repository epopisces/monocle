"""
monocle/agents/weekly_summary.py — Weekly summary agent.

Pipeline (M11):
1. Retrieve notes modified in the last 7 days from the vault.
2. Fetch their pre-computed 1536-dim embeddings from the index (no re-embedding).
3. Build a numpy embedding matrix; cluster with scikit-learn KMeans or
   AgglomerativeClustering.
4. Fallback: when the batch is very small (< _MIN_NOTES_FOR_CLUSTERING) *or*
   the index has no embeddings (MemoryIndex in tests), use LLM-based grouping
   via a structured prompt instead of model-based clustering.
5. For each cluster: call AIProvider.chat with prompts/weekly_review.md to
   generate a paragraph summary.
6. Optionally segment by domain if ``agents.weekly_summary.domains`` is
   configured.
7. Write ``summaries/YYYY-WW.md`` (ISO week number) with auto-approved
   frontmatter.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from monocle.prompts import load_prompt

if TYPE_CHECKING:
    from monocle.ai.base import AIProvider
    from monocle.config import Settings
    from monocle.index.base import IndexLayer
    from monocle.vault import VaultLayer

logger = logging.getLogger(__name__)

# Minimum number of notes required to run model-based clustering.
# Batches smaller than this fall back to LLM-based grouping.
_MIN_NOTES_FOR_CLUSTERING: int = 4

# Target number of clusters (n // 3, bounded below).
_DEFAULT_N_CLUSTERS: int = 5

# Hard upper bound on cluster count regardless of note volume.
# Must be >= _DEFAULT_N_CLUSTERS to be reachable.
_MAX_CLUSTERS: int = 8


#endregion

# ---------------------------------------------------------------------------
#region #*   Internal helpers
# ---------------------------------------------------------------------------


def _iso_week_label(dt: datetime) -> str:
    """Return an ISO year-week string like ``2026-12`` for the given datetime."""
    iso = dt.isocalendar()
    return f"{iso.year}-{iso.week:02d}"


def _compute_clusters_sklearn(
    embeddings: list[list[float]],
    n_clusters: int,
) -> list[int]:
    """Cluster embeddings using AgglomerativeClustering.

    Returns a list of integer cluster labels (one per embedding).
    Falls back to assigning each note to its own cluster if sklearn fails.
    """
    try:
        import numpy as np
        from sklearn.cluster import AgglomerativeClustering

        matrix = np.array(embeddings, dtype=np.float32)
        # Guard against requesting more clusters than samples
        k = min(n_clusters, len(matrix))
        model = AgglomerativeClustering(n_clusters=k, metric="cosine", linkage="average")
        labels: list[int] = model.fit_predict(matrix).tolist()
        return labels
    except Exception as exc:  # pragma: no cover
        logger.warning("sklearn clustering failed, falling back to LLM grouping: %s", exc)
        return list(range(len(embeddings)))  # each note its own "cluster" → triggers LLM fallback


async def _llm_group_notes(
    ai: "AIProvider",
    note_summaries: list[str],
) -> list[list[str]]:
    """Ask the LLM to group notes into thematic clusters.

    Returns a list of groups, each group being a list of note-summary strings.
    Used as a fallback when clustering is not possible or the batch is tiny.
    """
    prompt = (
        "You are organising a set of notes into thematic groups.\n\n"
        "Notes:\n"
        + "\n".join(f"{i + 1}. {s}" for i, s in enumerate(note_summaries))
        + "\n\nReturn a JSON object: {\"groups\": [[<indices>], ...]}\n"
        "Each inner list contains the 1-based indices of notes in that group.\n"
        "Use as few groups as make thematic sense (1–5).\n"
        "Return ONLY the JSON object, no other text."
    )
    try:
        response = await ai.chat([{"role": "user", "content": prompt}])
        content = response.content if hasattr(response, "content") else str(response)
        # Extract JSON from the response
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if not match:
            raise ValueError("No JSON object in LLM response")
        data = json.loads(match.group(0))
        groups_indices: list[list[int]] = data.get("groups", [[]])
        # Convert indices to groups of summaries; skip groups that become empty
        # after discarding out-of-range indices.
        n = len(note_summaries)
        groups: list[list[str]] = []
        for grp in groups_indices:
            if not grp:
                continue
            filtered = [note_summaries[i - 1] for i in grp if 1 <= i <= n]
            if filtered:
                groups.append(filtered)
        # Guarantee at least one group — if the model returned empty/garbage
        # groups, treat all notes as a single group rather than propagating an
        # empty list that would cause run() to raise "No notes modified".
        return groups if groups else [note_summaries]
    except Exception as exc:
        logger.warning("LLM grouping failed, using single group: %s", exc)
        return [note_summaries]


async def _summarise_cluster(
    ai: "AIProvider",
    cluster_notes: list[str],
    cluster_label: str,
    prompt_template: str,
) -> str:
    """Generate a paragraph summary for a single cluster via AIProvider.chat."""
    cluster_text = "\n\n".join(
        f"### Note {i + 1}\n{note}" for i, note in enumerate(cluster_notes)
    )
    filled = prompt_template.replace("{{clusters}}", f"## {cluster_label}\n\n{cluster_text}")
    try:
        response = await ai.chat([{"role": "user", "content": filled}])
        return response.content if hasattr(response, "content") else str(response)
    except Exception as exc:
        logger.warning("Cluster summarisation failed for '%s': %s", cluster_label, exc, exc_info=True)
        return f"*Summary generation failed for cluster '{cluster_label}' — see server logs*"


#endregion

# ---------------------------------------------------------------------------
#region #*   WeeklySummaryAgent
# ---------------------------------------------------------------------------


class WeeklySummaryAgent:
    """Generates a weekly summary note from the past 7 days of vault activity.

    Usage::

        agent = WeeklySummaryAgent()
        file_path = await agent.run(vault, index, ai, settings)

    The agent writes ``summaries/YYYY-WW.md`` with ``review_status: approved``
    and ``confidence: 1.0`` so it never lands in the review queue.
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(
        self,
        vault: "VaultLayer",
        index: "IndexLayer",
        ai: "AIProvider",
        settings: "Settings",
    ) -> str:
        """Run the weekly summary pipeline.

        Returns the vault-relative file path of the written summary note.
        Raises ``RuntimeError`` if no recent notes are found.
        """
        now = datetime.now(timezone.utc)
        week_label = _iso_week_label(now)
        cutoff = now - timedelta(days=7)

        domains: list[str | None] = settings.agents.weekly_summary.domains or [None]

        all_section_texts: list[str] = []
        producing_domains: list[str] = []

        for domain in domains:
            section = await self._run_domain(
                vault=vault,
                index=index,
                ai=ai,
                settings=settings,
                cutoff=cutoff,
                domain=domain,
            )
            if section:
                if domain:
                    all_section_texts.append(f"# {domain.capitalize()} Notes\n\n{section}")
                    producing_domains.append(domain)
                else:
                    all_section_texts.append(section)

        if not all_section_texts:
            raise RuntimeError(
                f"No notes modified in the last 7 days — skipping summary for week {week_label}"
            )

        summary_domain = producing_domains[0] if len(producing_domains) == 1 else "mixed"
        body = "\n\n---\n\n".join(all_section_texts)
        file_path = await asyncio.to_thread(
            self._write_summary, vault, week_label, now, body, summary_domain
        )
        logger.info("[AGENT] Weekly summary written: %s", file_path)
        return file_path

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _run_domain(
        self,
        vault: "VaultLayer",
        index: "IndexLayer",
        ai: "AIProvider",
        settings: "Settings",
        cutoff: datetime,
        domain: str | None,
    ) -> str:
        """Run the pipeline for a single domain (or all domains if domain=None)."""
        # Step 1 — collect recently-modified notes
        notes = await asyncio.to_thread(
            self._collect_recent_notes, vault, cutoff, domain
        )
        if not notes:
            return ""

        logger.info(
            "[AGENT] Weekly summary: %d notes found for domain=%s", len(notes), domain
        )

        # Step 2 — build note text summaries (title + first 300 chars of body)
        note_summaries = [self._note_summary(n) for n in notes]

        # Step 3 — attempt clustering or fallback
        groups: list[list[str]]
        use_llm_grouping = len(notes) < _MIN_NOTES_FOR_CLUSTERING

        if not use_llm_grouping:
            # Try to fetch embeddings from index
            file_paths = [n["file_path"] for n in notes]
            embeddings_map = await asyncio.to_thread(
                index.get_embeddings_by_file, file_paths
            )
            # Filter to notes that have embeddings; fall back if too few
            eligible = [
                (n, embeddings_map.get(n["file_path"]))
                for n in notes
                if n["file_path"] in embeddings_map
            ]
            if len(eligible) < _MIN_NOTES_FOR_CLUSTERING:
                use_llm_grouping = True
            else:
                emb_list = [e for _, e in eligible]
                note_list_for_emb = [n for n, _ in eligible]
                n_clusters = min(
                    max(2, len(eligible) // 3, _DEFAULT_N_CLUSTERS), _MAX_CLUSTERS
                )
                labels = await asyncio.to_thread(
                    _compute_clusters_sklearn, emb_list, n_clusters
                )
                # Group by cluster label
                cluster_map: dict[int, list[str]] = {}
                for note_item, label in zip(note_list_for_emb, labels):
                    cluster_map.setdefault(label, []).append(
                        self._note_summary(note_item)
                    )
                groups = list(cluster_map.values())

        if use_llm_grouping:
            groups = await _llm_group_notes(ai, note_summaries)

        # Step 4 — summarise each cluster via LLM
        prompt_template = load_prompt("weekly_review")
        cluster_summaries: list[str] = []
        for i, group in enumerate(groups):
            label = f"Cluster {i + 1}"
            summary = await _summarise_cluster(ai, group, label, prompt_template)
            cluster_summaries.append(summary)

        return "\n\n".join(cluster_summaries)

    def _collect_recent_notes(
        self,
        vault: "VaultLayer",
        cutoff: datetime,
        domain: str | None,
    ) -> list[dict]:
        """Return dicts with file_path, title, body for notes modified since cutoff."""
        page = vault.list_notes(
            domain=domain,
            sort="updated",
            limit=500,  # generous upper bound; weekly reviews handle hundreds of notes
        )
        result: list[dict] = []
        for ref in page.items:
            updated = ref.updated or ref.created
            if updated is None:
                continue
            # Ensure timezone-aware for comparison
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)
            if updated < cutoff:
                continue
            try:
                note = vault.read_note(ref.file_path)
                result.append(
                    {
                        "file_path": ref.file_path,
                        "title": note.title,
                        "body": note.body or "",
                    }
                )
            except Exception as exc:
                logger.warning("Failed to read note %s for summary: %s", ref.file_path, exc)
        return result

    def _note_summary(self, note_dict: dict) -> str:
        """Return a short text representation of a note for the LLM context."""
        title = note_dict.get("title") or note_dict.get("file_path", "Untitled")
        body = (note_dict.get("body") or "").strip()
        excerpt = body[:300].replace("\n", " ")
        return f"**{title}**: {excerpt}"

    def _write_summary(
        self,
        vault: "VaultLayer",
        week_label: str,
        now: datetime,
        body: str,
        domain: str,
    ) -> str:
        """Write the summary note to the vault. Returns the vault-relative file path."""
        from monocle.models import Note, NoteMetadata

        file_path = f"summaries/{week_label}.md"
        metadata = NoteMetadata(
            type="weekly_summary",
            template="weekly_summary",
            domain=domain,
            confidence=1.0,
            review_status="approved",
            approval_mode="auto",
            approved_by="system:weekly-summary",
            approved_at=now,
            created=now,
            updated=now,
            tags=["weekly-summary"],
            source="agent",
        )
        note = Note(
            file_path=file_path,
            title=f"Weekly Summary {week_label}",
            body=body,
            metadata=metadata,
        )
        vault.write_note(file_path, note)
        return file_path
