"""Presentation-only Agent output; never evidence of a proposal or consent."""

from pydantic import BaseModel, ConfigDict, model_validator


class AgentReply(BaseModel):
    """Separate independent answers from replaceable proposal narration.

    Field semantics live in the versioned Telegram prompt, not in schema
    descriptions. Only persisted proposals let the Core replace proposal_text.
    Neither field grants authority, identifies a target, or changes a payload.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    answer: str
    proposal_text: str

    @model_validator(mode="after")
    def require_visible_content(self) -> "AgentReply":
        """Reject a final presentation that would become a silent reply.

        A reviewable proposal is only real after its ``propose_*`` tool ran.
        The Core can then replace the non-empty ``proposal_text`` with its
        canonical block, but a model must never use two empty fields to skip
        that tool call or to finish a read request without an answer.
        """
        if not self.answer.strip() and not self.proposal_text.strip():
            raise ValueError("AgentReply requires non-empty answer or proposal_text")
        return self

    def text(self) -> str:
        """Render the raw partition for evals; delivery must verify proposals."""
        return "\n\n".join(
            part.strip() for part in (self.answer, self.proposal_text) if part.strip()
        )
