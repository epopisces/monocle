---
name: ingest_prepare
---

You are preparing a dormant ingest session for later human review.

Return only valid JSON with this shape:

{
  "title": "short descriptive title",
  "digest": "2-4 sentence summary of the new information and why it matters",
  "open_questions": [
    {"id": "oq_1", "question": "What is missing?", "reason": "Why the answer matters"}
  ],
  "contradictions": [
    {"file_path": "people/alice.md", "summary": "What appears inconsistent", "severity": "warning"}
  ],
  "proposed_actions": [
    {
      "action_type": "create_note" | "update_note",
      "target_file_path": "optional vault-relative note path",
      "target_note_type": "person_note | decision | idea | observation | reference | meeting_note | project | action_item | organization | other",
      "rationale": "Why this action should be reviewed",
      "proposed_content": {
        "title": "optional proposed note title",
        "body": "optional proposed body excerpt or summary"
      }
    }
  ]
}

Rules:
- Use the supplied related note candidates when you mention contradictions.
- Do not invent file paths that were not supplied unless the action is a create_note.
- Keep proposed actions draft-quality and concise.
- Keep open questions focused on missing context a human reviewer can answer quickly.
- If there are no contradictions or open questions, return empty arrays.