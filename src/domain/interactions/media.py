"""Safe, recoverable Telegram attachment metadata and resolved media data.

The admission ledger stores only the encrypted reference metadata required to
download an attachment after a durable interaction claim. Raw bytes never enter
the ledger, logs, telemetry, or runtime configuration.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class TelegramAttachment(BaseModel):
    """One trusted-shape but untrusted-content reference from a Telegram update."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["photo", "document", "voice"]
    file_id: str = Field(min_length=1, max_length=255)
    filename: str | None = Field(default=None, max_length=255)
    mime_type: str | None = Field(default=None, max_length=127)
    size_bytes: int | None = Field(default=None, ge=0)
    duration_seconds: int | None = Field(default=None, ge=0, strict=True)


@dataclass(frozen=True)
class ResolvedTelegramMedia:
    """Attachment bytes resolved transiently after the interaction is claimed."""

    content: bytes
    filename: str
    mime_type: str
    is_image: bool


class AttachmentResolutionError(RuntimeError):
    """Bounded media-resolution failure safe to record in interaction metadata."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code
