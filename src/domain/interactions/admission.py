"""Deterministic Telegram admission policy independent from FastAPI and Agno."""

from __future__ import annotations

from dataclasses import dataclass

from src.domain.interactions.models import (
    InteractionStatus,
    NormalizedTelegramUpdate,
)


@dataclass(frozen=True)
class AdmissionDecision:
    """Policy decision persisted with a new interaction when it is not accepted."""

    status: InteractionStatus
    error_detail_code: str | None = None


class TelegramAdmissionPolicy:
    """Private-chat and allowlist policy evaluated before any Agent execution."""

    def __init__(self, allowed_user_ids: set[int] | frozenset[int]):
        self._allowed_user_ids = frozenset(allowed_user_ids)

    def evaluate(self, update: NormalizedTelegramUpdate) -> AdmissionDecision:
        """Classify a normalized update without using its personal content."""
        if update.update_type == "unsupported":
            return AdmissionDecision(InteractionStatus.IGNORED, "unsupported_update")
        if update.chat_type != "private":
            return AdmissionDecision(InteractionStatus.REJECTED, "non_private_chat")
        if update.telegram_user_id is None:
            return AdmissionDecision(InteractionStatus.REJECTED, "missing_telegram_user_id")
        if update.telegram_user_id not in self._allowed_user_ids:
            return AdmissionDecision(InteractionStatus.REJECTED, "user_not_allowlisted")
        return AdmissionDecision(InteractionStatus.ACCEPTED)
