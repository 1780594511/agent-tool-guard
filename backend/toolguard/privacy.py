"""Audit stores hashes and bounded structured metadata, never document bodies or free text."""

import re

from .db import digest


def redact(text: str) -> str:
    text = re.sub(
        r"(?i)(bearer\s+|sk-[\w-]*|(?:api[_-]?key|password|secret)\s*[:=]\s*)[^\s,;]+", "[REDACTED]", text
    )
    text = re.sub(r"[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}", "[EMAIL]", text)
    text = re.sub(r"\b\d{11,18}\b", "[NUMBER]", text)
    return text


def arguments_preview(tool: str, arguments: dict) -> dict:
    out = {"sha256": digest(arguments), "fields": sorted(redact(str(k))[:40] for k in arguments)[:20]}
    for key in ("document_id", "document_ids", "destination"):
        value = arguments.get(key)
        if isinstance(value, str):
            out[key] = redact(value)[:120]
        elif isinstance(value, list):
            out[key] = [redact(str(item))[:80] for item in value[:10]]
    for key in ("title", "body"):
        if key in arguments:
            out[key] = {"sha256": digest(arguments[key]), "length": len(str(arguments[key]))}
    return out
