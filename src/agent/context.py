"""AncoraMind — Runtime user context resolution.

Resolves Telegram chat identity to AncoraMind UserContext.
The identity NEVER comes from the LLM.
"""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class UserContext:
    """Trusted user context resolved from the channel.

    This is created by the runtime from channel-provided identity,
    never from LLM output.
    """

    user_id: UUID
    channel: str  # e.g., "telegram"
    external_chat_id: str  # e.g., Telegram chat ID

    def __repr__(self) -> str:
        return (
            f"UserContext(user_id={self.user_id}, "
            f"channel={self.channel}, "
            f"external_chat_id={self.external_chat_id})"
        )
