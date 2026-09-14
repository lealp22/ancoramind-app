"""Canonical HMAC fingerprints for tool calls (specs/013 T8).

Fingerprints detect identical repetitions of a tool call without persisting or
exporting the arguments themselves. The HMAC uses an internal Railway secret
so the digest cannot be brute-forced by dictionary attacks over predictable
tool arguments.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

FINGERPRINT_LENGTH = 32


def canonical_tool_call_json(tool_name: str, arguments: Any) -> str:
    """Serialize a tool call deterministically, independently of dict order."""
    return json.dumps(
        {"tool": tool_name, "args": arguments},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def derive_fingerprint_key(payload_encryption_key: str | None) -> str | None:
    """Derive a dedicated fingerprint key from the payload encryption secret.

    Using a derived subkey keeps the number of required Railway secrets down
    while never reusing the payload-cipher key material directly. An explicit
    ``EXECUTION_BUDGET_FINGERPRINT_KEY`` always takes precedence.
    """
    if not payload_encryption_key:
        return None
    material = payload_encryption_key.encode("utf-8")
    return hashlib.sha256(b"ancoramind/tool-fingerprint/v1" + material).hexdigest()


def compute_tool_fingerprint(fingerprint_key: str, tool_name: str, arguments: Any) -> str:
    """Return the stable HMAC-SHA256 hex digest of one canonical tool call."""
    return hmac.new(
        fingerprint_key.encode("utf-8"),
        canonical_tool_call_json(tool_name, arguments).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:FINGERPRINT_LENGTH]


__all__ = [
    "FINGERPRINT_LENGTH",
    "canonical_tool_call_json",
    "compute_tool_fingerprint",
    "derive_fingerprint_key",
]
