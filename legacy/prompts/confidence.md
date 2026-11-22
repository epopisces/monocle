---
agent: confidence
version: "1.0"
description: >
  DOCUMENTATION PLACEHOLDER ONLY.
  Confidence scoring is deterministic (no LLM call) as of M7.
  Formula: 0.35*template_match + 0.30*metadata_coverage
           + 0.20*tag_plausibility + 0.15*entity_match
  See monocle/ingest/confidence.py for the implementation.
---

# Confidence Scoring — Documentation

This file documents the confidence scoring formula used by the ingest pipeline.
It is NOT loaded by any agent — scoring is computed deterministically in code.

## Formula

```
score = (
    0.35 * template_match      # How well content matches the chosen template
  + 0.30 * metadata_coverage   # Fraction of required frontmatter fields populated
  + 0.20 * tag_plausibility    # Semantic consistency of tags with body content
  + 0.15 * entity_match        # Whether detected people already exist as person notes
)
```

Weights are configurable via `review.confidence_weights` in `config.yaml`.
