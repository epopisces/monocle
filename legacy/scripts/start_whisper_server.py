"""Start a local whisper.cpp HTTP server for transcription.

Reads the server binary path and model path from environment variables,
falling back to workspace-relative defaults.  Works on Windows, macOS,
and Linux without any shell-specific syntax.

Environment variables (both optional):
    WHISPER_CPP_SERVER   absolute path to the whisper-server binary
    WHISPER_CPP_MODEL    absolute path to the Whisper model file
                         (e.g. GGML ``.bin`` or GGUF ``.gguf``)

Defaults:
    Windows  — <workspace>/tools/whisper-server.exe
    macOS    — <workspace>/tools/whisper-server
    Linux    — <workspace>/tools/whisper-server

Usage (from workspace root)::

    uv run python scripts/start_whisper_server.py

Or via the VS Code task: **whisper.cpp: start server**

Prerequisites:
  1. Build whisper.cpp: https://github.com/ggerganov/whisper.cpp
     (``cmake -B build && cmake --build build --config Release``)
  2. Copy the resulting ``server`` / ``server.exe`` binary to ``tools/``.
  3. Download a Whisper model (GGML ``.bin`` example), e.g.::
       curl -L -o tools/models/ggml-base.en.bin \\
         https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin
  4. Set ``ai.transcribe_backend: whisper_cpp`` in ``config.yaml``.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_workspace = Path(__file__).resolve().parent.parent
_default_binary = "whisper-server.exe" if sys.platform == "win32" else "whisper-server"

server = os.environ.get(
    "WHISPER_CPP_SERVER",
    str(_workspace / "tools" / _default_binary),
)
model = os.environ.get(
    "WHISPER_CPP_MODEL",
    str(_workspace / "tools" / "models" / "ggml-base.en.bin"),
)

cmd = [server, "--model", model, "--host", "127.0.0.1", "--port", "9000"]
print(f"[WHISPER] Starting: {' '.join(cmd)}", flush=True)
sys.exit(subprocess.run(cmd).returncode)
