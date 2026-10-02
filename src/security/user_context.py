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

        Uses ``run_context.user_id`` (set by the governed runner / AgentOS)
        and, only for the legacy Telegram path, the chat id embedded in the
        session id (``tg:{entity}:{chat_id}[:generation]``).

        Fails closed (specs/023 T2): if neither source yields a trusted
        identity, raises instead of degrading to a shared placeholder such
        as ``"unknown"`` — otherwise unrelated runs would read and write the
        same canonical data.

        Args:
            run_context: Agno RunContext provided automatically to tools.

        Returns:
            Resolved UserContext with trusted identity.

        Raises:
            ValueError: If the RunContext carries no trusted identity.
        """
        if run_context.user_id and run_context.user_id.strip():
            return cls(user_id=run_context.user_id.strip())

        session_id = run_context.session_id or ""
        parts = session_id.split(":")
        if len(parts) >= 3 and parts[0] == "tg" and parts[2].strip():
            return cls(user_id=parts[2].strip())

        raise ValueError("UserContext: no trusted identity in RunContext")


def get_current_user_context() -> UserContext:
    """Placeholder for when RunContext is not available (CLI, tests).

    In production, always use UserContext.from_run_context(run_context)
    from within a tool function.

    Returns:
        A placeholder UserContext for development/testing.
    """
    return UserContext(user_id="dev-user")
