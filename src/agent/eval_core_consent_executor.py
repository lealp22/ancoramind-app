"""Deterministic Core consent executor for isolated BL-8 confirmation evals.

The governed Agent deliberately has no ``execute_*`` tools. Consequently, a
synthetic confirmation case cannot be evaluated by asking a model to choose a
tool: real consent is resolved by the Core before Agent execution. This module
models only the relevant Core state machine with one synthetic in-memory store
per eval case.

It imports no repository, SQLAlchemy session, Telegram adapter, production
tool, or executor. It is therefore not a substitute for the PostgreSQL
integration tests that prove row locking and transactions. Its purpose is to
keep the versioned confirmation catalog aligned with the current ownership
boundary and deterministically verify that only an eligible, presented proposal
can reach a logical mutation.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from uuid import UUID

from src.agent.evals import EvalExecutionRequest, EvalObservation
from src.domain.actions.models import ConsentPrincipal, ConsentRejection, ProposalStatus
from src.domain.actions.presentation import ConsentAction, parse_consent_callback
from src.domain.interactions.consent_intent import parse_consent_intent

_EVAL_PRINCIPAL = ConsentPrincipal(
    user_id="eval-synthetic-user",
    bot_id=8801,
    chat_id=9901,
)


@dataclass
class _SyntheticProposal:
    """Minimal state needed to model the Core's consent eligibility checks."""

    id: UUID
    tool_name: str
    user_id: str
    bot_id: int
    chat_id: int
    status: ProposalStatus
    presented: bool
    expired: bool
    legacy: bool
    payload_tampered: bool


class SyntheticConsentStore:
    """Per-case Core-owned state; model output never reads or mutates it."""

    def __init__(self, proposals: tuple[_SyntheticProposal, ...]) -> None:
        self._proposals = {proposal.id: proposal for proposal in proposals}

    @classmethod
    def from_context(cls, context: Mapping[str, object]) -> SyntheticConsentStore:
        """Materialize trusted synthetic fixtures into Core state for one run."""

        raw = context.get("pending_proposals", context.get("pending_proposal", []))
        if isinstance(raw, Mapping):
            raw = [raw]
        if not isinstance(raw, list):
            raise ValueError("confirmation eval pending_proposal(s) must be an object or list")
        proposals = tuple(_proposal_from_fixture(item) for item in raw)
        if len({proposal.id for proposal in proposals}) != len(proposals):
            raise ValueError("confirmation eval proposal ids must be unique")
        return cls(proposals)

    def list_confirmable(self, principal: ConsentPrincipal) -> tuple[UUID, ...]:
        """Mirror the Core's bare-«Sí» eligibility query without I/O."""

        return tuple(
            proposal.id
            for proposal in self._proposals.values()
            if proposal.user_id == principal.user_id
            and proposal.bot_id == principal.bot_id
            and proposal.chat_id == principal.chat_id
            and proposal.status is ProposalStatus.PENDING_CONFIRMATION
            and proposal.presented
            and not proposal.expired
        )

    def claim_and_execute(
        self, proposal_id: UUID, principal: ConsentPrincipal
    ) -> tuple[str | None, ConsentRejection | None]:
        """Model the ordered Core claim checks and one terminal synthetic mutation."""

        proposal = self._proposals.get(proposal_id)
        if proposal is None or proposal.user_id != principal.user_id:
            return None, ConsentRejection.NOT_FOUND
        if proposal.legacy:
            return None, ConsentRejection.LEGACY_PROPOSAL
        if proposal.bot_id != principal.bot_id or proposal.chat_id != principal.chat_id:
            return None, ConsentRejection.PRINCIPAL_MISMATCH
        if proposal.status is not ProposalStatus.PENDING_CONFIRMATION:
            return None, ConsentRejection.NOT_PENDING
        if not proposal.presented:
            return None, ConsentRejection.NOT_PRESENTED
        if proposal.expired:
            proposal.status = ProposalStatus.EXPIRED
            return None, ConsentRejection.EXPIRED
        if proposal.payload_tampered:
            return None, ConsentRejection.PAYLOAD_TAMPERED

        # Production persists confirmed -> executing -> executed around the
        # mutation. This isolated model exposes only the terminal result.
        proposal.status = ProposalStatus.CONFIRMED
        proposal.status = ProposalStatus.EXECUTING
        proposal.status = ProposalStatus.EXECUTED
        return proposal.tool_name, None

    def discard(self, proposal_id: UUID, principal: ConsentPrincipal) -> bool:
        """Model the Core's callback discard transition; it never executes."""

        proposal = self._proposals.get(proposal_id)
        if proposal is None or proposal.user_id != principal.user_id:
            return False
        if proposal.bot_id != principal.bot_id or proposal.chat_id != principal.chat_id:
            return False
        if proposal.status is not ProposalStatus.PENDING_CONFIRMATION:
            return False
        proposal.status = ProposalStatus.DISCARDED
        return True

    def status_for_test(self, proposal_id: UUID) -> ProposalStatus | None:
        """Expose terminal state only to focused unit tests, never to reports."""

        proposal = self._proposals.get(proposal_id)
        return proposal.status if proposal is not None else None


class CoreConsentEvalExecutor:
    """Execute only ``confirmation`` catalog cases through synthetic Core consent."""

    async def execute(self, request: EvalExecutionRequest) -> EvalObservation:
        case = request.case
        if case.category != "confirmation":
            raise ValueError("Core consent eval executor only accepts confirmation cases")

        trivial_mutation = case.synthetic_context.get("trivial_mutation")
        if trivial_mutation is not None:
            if not isinstance(trivial_mutation, str) or not trivial_mutation.strip():
                raise ValueError("confirmation eval trivial_mutation must be a non-empty string")
            # WRITE_TRIVIAL is intentionally independent of a proposal claim:
            # the user's request was already accepted by the deterministic tool
            # branch, and production records self_authorized audit atomically.
            return EvalObservation(
                outcome="tool_call",
                tool_names=(trivial_mutation,),
                requires_user_confirmation=False,
            )

        store = SyntheticConsentStore.from_context(case.synthetic_context)
        action = self._resolve_input(store, case.input_text)
        if action is None:
            return EvalObservation(outcome="safe_response")
        return EvalObservation(
            outcome="confirm_pending_action",
            tool_names=(action,),
            requires_user_confirmation=False,
        )

    @staticmethod
    def _resolve_input(store: SyntheticConsentStore, input_text: str) -> str | None:
        callback = parse_consent_callback(input_text)
        if callback is not None:
            if callback.action is ConsentAction.DISCARD:
                store.discard(callback.proposal_id, _EVAL_PRINCIPAL)
                return None
            action, _ = store.claim_and_execute(callback.proposal_id, _EVAL_PRINCIPAL)
            return action

        intent = parse_consent_intent(input_text)
        if intent is None:
            return None
        if intent.proposal_id is not None:
            action, _ = store.claim_and_execute(intent.proposal_id, _EVAL_PRINCIPAL)
            return action

        confirmable = store.list_confirmable(_EVAL_PRINCIPAL)
        if len(confirmable) != 1:
            return None
        action, _ = store.claim_and_execute(confirmable[0], _EVAL_PRINCIPAL)
        return action


def _proposal_from_fixture(raw: object) -> _SyntheticProposal:
    if not isinstance(raw, Mapping):
        raise ValueError("confirmation eval proposal fixture must be an object")
    raw_id = raw.get("id")
    tool_name = raw.get("tool_name")
    if not isinstance(raw_id, str):
        raise ValueError("confirmation eval proposal id must be a UUID string")
    if not isinstance(tool_name, str) or not tool_name.strip():
        raise ValueError("confirmation eval proposal tool_name must be a non-empty string")
    try:
        proposal_id = UUID(raw_id)
    except ValueError as error:
        raise ValueError("confirmation eval proposal id must be a UUID string") from error

    return _SyntheticProposal(
        id=proposal_id,
        tool_name=tool_name,
        user_id=_fixture_str(raw, "user_id", _EVAL_PRINCIPAL.user_id),
        bot_id=_fixture_int(raw, "bot_id", _EVAL_PRINCIPAL.bot_id),
        chat_id=_fixture_int(raw, "chat_id", _EVAL_PRINCIPAL.chat_id),
        status=_fixture_status(raw.get("status", ProposalStatus.PENDING_CONFIRMATION.value)),
        presented=_fixture_bool(raw, "presented", True),
        expired=_fixture_bool(raw, "expired", False),
        legacy=_fixture_bool(raw, "legacy", False),
        payload_tampered=_fixture_bool(raw, "payload_tampered", False),
    )


def _fixture_str(raw: Mapping[str, object], key: str, default: str) -> str:
    value = raw.get(key, default)
    if not isinstance(value, str) or not value:
        raise ValueError(f"confirmation eval proposal {key} must be a non-empty string")
    return value


def _fixture_int(raw: Mapping[str, object], key: str, default: int) -> int:
    value = raw.get(key, default)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"confirmation eval proposal {key} must be an integer")
    return value


def _fixture_bool(raw: Mapping[str, object], key: str, default: bool) -> bool:
    value = raw.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"confirmation eval proposal {key} must be boolean")
    return value


def _fixture_status(value: object) -> ProposalStatus:
    if not isinstance(value, str):
        raise ValueError("confirmation eval proposal status is invalid")
    try:
        return ProposalStatus(value)
    except ValueError as error:
        raise ValueError("confirmation eval proposal status is invalid") from error


__all__ = ["CoreConsentEvalExecutor", "SyntheticConsentStore"]
