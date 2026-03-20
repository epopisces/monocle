#!/usr/bin/env python
"""Test BeforeValidator with agent_framework's create_model."""
import asyncio
import json
from pydantic import BeforeValidator, Field
from typing import Annotated, Any
from agent_framework._tools import _create_input_model_from_func, ai_function
from agent_framework import ai_function as ai_fn


def _norm(v: Any) -> Any:
    if v is None or isinstance(v, list):
        return v
    if isinstance(v, str):
        try:
            return json.loads(v)
        except (json.JSONDecodeError, ValueError):
            pass
        try:
            import ast
            return ast.literal_eval(v)
        except (ValueError, SyntaxError):
            pass
        return [t.strip() for t in v.split(",") if t.strip()] or None
    return [str(v)]


@ai_fn
async def test_create(
    title: str,
    tags: Annotated[list[str] | None, BeforeValidator(_norm)] = None,
) -> str:
    return str(tags)


def run_tests() -> bool:
    model = _create_input_model_from_func(test_create.func, "test_create")
    print("Model fields:", list(model.model_fields.keys()))

    test_cases = [
        ({"title": "x", "tags": ["a", "b"]}, "list"),
        ({"title": "x", "tags": '["a","b"]'}, "JSON string"),
        ({"title": "x", "tags": "['a','b']"}, "Python list string"),
        ({"title": "x", "tags": "work, python"}, "comma-separated"),
        ({"title": "x", "tags": None}, "None"),
        ({"title": "x"}, "omitted"),
    ]
    failures = 0
    for args, desc in test_cases:
        try:
            result = model.model_validate(args)
            print(f"OK ({desc}): {result.tags}")
        except Exception as e:
            print(f"FAIL ({desc}): {e}")
            failures += 1
    return failures == 0


if __name__ == "__main__":
    ok = run_tests()
    exit(0 if ok else 1)
