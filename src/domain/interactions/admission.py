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

    def is_technical_allowlisted(self, telegram_user_id: int) -> bool:
        """Return whether configuration explicitly authorizes this Telegram identity."""
        return telegram_user_id in self._allowed_user_ids

    def evaluate(
        self,
        update: NormalizedTelegramUpdate,
        *,
        has_active_authorization: bool = False,
        permits_pairing: bool = False,
    ) -> AdmissionDecision:
        """Classify a normalized update without using its personal content."""
        if update.update_type == "unsupported":
            return AdmissionDecision(InteractionStatus.IGNORED, "unsupported_update")
        if update.chat_type != "private":
            return AdmissionDecision(InteractionStatus.REJECTED, "non_private_chat")
        if update.telegram_user_id is None:
            return AdmissionDecision(InteractionStatus.REJECTED, "missing_telegram_user_id")
        if self.is_technical_allowlisted(update.telegram_user_id):
            return AdmissionDecision(InteractionStatus.ACCEPTED)
        if has_active_authorization:
            return AdmissionDecision(InteractionStatus.ACCEPTED)
        if permits_pairing:
            # This narrowly permits deterministic onboarding only; it never
            # authorizes an Agent/LLM run for an otherwise unknown identity.
            return AdmissionDecision(InteractionStatus.ACCEPTED)
        return AdmissionDecision(InteractionStatus.REJECTED, "user_not_allowlisted")
