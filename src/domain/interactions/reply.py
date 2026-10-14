"""Presentation-only Agent output; never evidence of a proposal or consent."""

from pydantic import BaseModel, ConfigDict


class AgentReply(BaseModel):
    """Separate independent answers from replaceable proposal narration.

    Field semantics live in the versioned Telegram prompt, not in schema
    descriptions. Only persisted proposals let the Core replace proposal_text.
    Neither field grants authority, identifies a target, or changes a payload.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    answer: str
    proposal_text: str

    def text(self) -> str:
        """Render both parts when no Core proposal block replaces the second."""
        return "\n\n".join(
            part.strip() for part in (self.answer, self.proposal_text) if part.strip()
        )
