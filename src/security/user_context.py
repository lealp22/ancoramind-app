"""User context resolution — trusted identity from the Agent Runtime.

The identity NEVER comes from the LLM. It is resolved from the Agno
RunContext, which carries the Telegram session / user information.
"""

from dataclasses import dataclass

from agno.run import RunContext


@dataclass(frozen=True)
class UserContext:
    """Trusted user context resolved from the agent runtime.

    Created from RunContext provided by Agno. The LLM never provides
    user_id or any identity field.
    """

    user_id: str
    """Internal user identifier. Initially the Telegram chat ID;
    will map to AncoraMind user UUID in a future milestone."""

    channel: str = "telegram"
    """Channel identifier."""

    @classmethod
    def from_run_context(cls, run_context: RunContext) -> "UserContext":
        """Resolve UserContext from an Agno RunContext.

        Extracts the user identifier from the session ID.
        Session format: tg:{entity_id}:{chat_id}

        Args:
            run_context: Agno RunContext provided automatically to tools.

        Returns:
            Resolved UserContext with trusted identity.
        """
        # Try user_id from run_context first (set by AgentOS)
        if run_context.user_id:
            return cls(user_id=run_context.user_id)

        # Fallback: extract from session_id (format: tg:entity:chat_id)
        session_id = run_context.session_id or ""
        parts = session_id.split(":")
        if len(parts) >= 3 and parts[0] == "tg":
            return cls(user_id=parts[2])

        # Last resort: use session_id as identifier
        return cls(user_id=session_id or "unknown")


def get_current_user_context() -> UserContext:
    """Placeholder for when RunContext is not available (CLI, tests).

    In production, always use UserContext.from_run_context(run_context)
    from within a tool function.

    Returns:
        A placeholder UserContext for development/testing.
    """
    return UserContext(user_id="dev-user")