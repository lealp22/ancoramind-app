"""Models and invariants for the durable Telegram interaction ledger."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.domain.interactions.media import TelegramAttachment


class InteractionStatus(StrEnum):
    """States allowed by the specs/013 interaction state machine."""

    ACCEPTED = "accepted"
    IGNORED = "ignored"
    REJECTED = "rejected"
    AGENT_STARTED = "agent_started"
    RESPONSE_READY = "response_ready"
    DELIVERY_STARTED = "delivery_started"
    COMPLETED = "completed"
    FAILED_CONTROLLED = "failed_controlled"
    FAILED_DEFINITIVE = "failed_definitive"
    FAILED_AMBIGUOUS = "failed_ambiguous"


TERMINAL_INTERACTION_STATUSES = frozenset(
    {
        InteractionStatus.IGNORED,
        InteractionStatus.REJECTED,
        InteractionStatus.COMPLETED,
        InteractionStatus.FAILED_CONTROLLED,
        InteractionStatus.FAILED_DEFINITIVE,
        InteractionStatus.FAILED_AMBIGUOUS,
    }
)


class TelegramInteractionCreate(BaseModel):
    """Trusted metadata plus encrypted payload required to create an interaction."""

    model_config = ConfigDict(frozen=True)

    bot_id: int
    telegram_update_id: int
    telegram_message_id: int | None = None
    chat_id: int | None = None
    telegram_user_id: int | None = None
    update_type: str = Field(min_length=1, max_length=63)
    status: InteractionStatus = InteractionStatus.ACCEPTED
    payload_ciphertext: bytes | None = None
    payload_key_version: int | None = Field(default=None, ge=1)
    payload_fingerprint: str | None = Field(default=None, min_length=64, max_length=128)
    error_class: str | None = Field(default=None, max_length=127)
    error_detail_code: str | None = Field(default=None, max_length=127)

    @field_validator("update_type")
    @classmethod
    def normalize_update_type(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("update_type must not be blank")
        return normalized


class TelegramDeliveryCreate(BaseModel):
    """One HTTP delivery audit row for a Telegram update."""

    model_config = ConfigDict(frozen=True)

    railway_request_id: str | None = Field(default=None, max_length=255)
    http_status: int | None = Field(default=None, ge=100, le=599)
    delivery_status: str = Field(default="received", min_length=1, max_length=31)

    @field_validator("railway_request_id", "delivery_status")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class TelegramInteraction(BaseModel):
    """Durable interaction metadata. ``id`` is the stable correlation ID."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: UUID
    bot_id: int
    telegram_update_id: int
    telegram_message_id: int | None = None
    chat_id: int | None = None
    telegram_user_id: int | None = None
    update_type: str
    status: InteractionStatus
    payload_ciphertext: bytes | None = None
    payload_key_version: int | None = None
    payload_fingerprint: str | None = None
    error_class: str | None = None
    error_detail_code: str | None = None
    agno_session_id: str | None = None
    agno_run_id: str | None = None
    received_at: datetime
    accepted_at: datetime | None = None
    agent_started_at: datetime | None = None
    response_ready_at: datetime | None = None
    delivery_started_at: datetime | None = None
    completed_at: datetime | None = None
    updated_at: datetime

    @property
    def correlation_id(self) -> UUID:
        """Return the product-wide stable identifier for this interaction."""
        return self.id


class TelegramAdmissionResult(BaseModel):
    """Outcome of atomically recording an interaction and its HTTP delivery."""

    model_config = ConfigDict(frozen=True)

    interaction: TelegramInteraction
    duplicate: bool


class TelegramAdmissionLimits(BaseModel):
    """Durable admission limits from the approved initial specs/013 defaults."""

    model_config = ConfigDict(frozen=True)

    user_burst: int = Field(ge=1)
    burst_window_seconds: int = Field(ge=1)
    user_requests_per_minute: int = Field(ge=1)
    user_requests_per_hour: int = Field(ge=1)
    pending_global: int = Field(ge=1)
    queued_per_chat: int = Field(ge=1)


class LogicalResponse(BaseModel):
    """Persisted final response waiting for deterministic outbound delivery."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: UUID
    interaction_id: UUID
    response_kind: str
    content_ciphertext: bytes | None = None
    content_key_version: int | None = None
    content_length: int
    chunk_count: int
    status: str
    created_at: datetime


class TelegramResponseDelivery(BaseModel):
    """Durable state for one deterministic Telegram response chunk."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: UUID
    logical_response_id: UUID
    chunk_index: int
    status: str
    telegram_message_id: int | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_class: str | None = None


class NormalizedTelegramUpdate(BaseModel):
    """Minimal recoverable representation of a Telegram update, treated as data."""

    model_config = ConfigDict(frozen=True)

    update_id: int
    update_type: str
    message_id: int | None = None
    chat_id: int | None = None
    telegram_user_id: int | None = None
    chat_type: str | None = None
    text: str | None = None
    attachments: tuple[TelegramAttachment, ...] = ()


def normalize_telegram_update(update: dict[str, Any]) -> NormalizedTelegramUpdate:
    """Extract minimal data needed for a later processor from an untrusted update.

    Attachment references are deliberately narrow and encrypted in the ledger:
    only the Bot API file identifier and bounded display metadata survive. Raw
    document bytes and unknown nested structures are never persisted here.
    """
    update_id = update.get("update_id")
    if not isinstance(update_id, int):
        raise ValueError("Telegram update_id must be an integer")

    for update_type in ("message", "edited_message", "channel_post", "callback_query"):
        candidate = update.get(update_type)
        if isinstance(candidate, dict):
            if update_type == "callback_query":
                message = candidate.get("message")
                message_data = message if isinstance(message, dict) else {}
                sender = candidate.get("from")
                text = candidate.get("data")
            else:
                message_data = candidate
                sender = candidate.get("from")
                text = candidate.get("text") or candidate.get("caption")

            chat = message_data.get("chat")
            return NormalizedTelegramUpdate(
                update_id=update_id,
                update_type=update_type,
                message_id=_integer_or_none(message_data.get("message_id")),
                chat_id=_integer_or_none(chat.get("id")) if isinstance(chat, dict) else None,
                telegram_user_id=_integer_or_none(sender.get("id"))
                if isinstance(sender, dict)
                else None,
                chat_type=chat.get("type")
                if isinstance(chat, dict) and isinstance(chat.get("type"), str)
                else None,
                text=text if isinstance(text, str) else None,
                attachments=_normalize_attachments(message_data),
            )

    return NormalizedTelegramUpdate(update_id=update_id, update_type="unsupported")


def _integer_or_none(value: object) -> int | None:
    return value if isinstance(value, int) else None


def _normalize_attachments(message: dict[str, Any]) -> tuple[TelegramAttachment, ...]:
    """Keep one bounded attachment reference; Telegram photos have many sizes."""
    photos = message.get("photo")
    if isinstance(photos, list):
        for photo in reversed(photos):
            if isinstance(photo, dict) and isinstance(photo.get("file_id"), str):
                return (
                    TelegramAttachment(
                        kind="photo",
                        file_id=photo["file_id"],
                        size_bytes=_integer_or_none(photo.get("file_size")),
                    ),
                )

    document = message.get("document")
    if isinstance(document, dict) and isinstance(document.get("file_id"), str):
        filename = document.get("file_name")
        mime_type = document.get("mime_type")
        return (
            TelegramAttachment(
                kind="document",
                file_id=document["file_id"],
                filename=filename if isinstance(filename, str) else None,
                mime_type=mime_type if isinstance(mime_type, str) else None,
                size_bytes=_integer_or_none(document.get("file_size")),
            ),
        )

    return ()
