from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any


def _post_json(url: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def chat_json(system: str, user: str) -> dict[str, Any]:
    """Call OpenAI-compatible APIs if keys exist. Raises if none work."""
    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    ollama = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
    ollama_model = os.getenv("OLLAMA_MODEL", "llama3.1")

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]

    errors: list[str] = []

    if groq_key:
        try:
            out = _post_json(
                "https://api.groq.com/openai/v1/chat/completions",
                {
                    "model": os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
                    "temperature": 0.7,
                    "response_format": {"type": "json_object"},
                    "messages": messages,
                },
                {
                    "Authorization": f"Bearer {groq_key}",
                    "Content-Type": "application/json",
                },
            )
            return _parse_content(out["choices"][0]["message"]["content"])
        except Exception as exc:  # noqa: BLE001
            errors.append(f"groq: {exc}")

    if openai_key:
        try:
            base = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
            out = _post_json(
                f"{base}/chat/completions",
                {
                    "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                    "temperature": 0.7,
                    "response_format": {"type": "json_object"},
                    "messages": messages,
                },
                {
                    "Authorization": f"Bearer {openai_key}",
                    "Content-Type": "application/json",
                },
            )
            return _parse_content(out["choices"][0]["message"]["content"])
        except Exception as exc:  # noqa: BLE001
            errors.append(f"openai: {exc}")

    try:
        out = _post_json(
            f"{ollama}/api/chat",
            {
                "model": ollama_model,
                "stream": False,
                "format": "json",
                "messages": messages,
            },
            {"Content-Type": "application/json"},
        )
        return _parse_content(out.get("message", {}).get("content", "{}"))
    except Exception as exc:  # noqa: BLE001
        errors.append(f"ollama: {exc}")

    raise RuntimeError("No LLM available. " + " | ".join(errors))


def _parse_content(text: str) -> dict[str, Any]:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    return json.loads(text)
