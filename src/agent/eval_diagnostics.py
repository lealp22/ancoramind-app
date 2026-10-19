"""Content-free terminal diagnostics for isolated evals, never a reply fallback."""

from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from src.domain.interactions.reply import InvalidPresentationOutputError

if TYPE_CHECKING:
    from agno.run.agent import RunOutput


class TerminalDiagnostic(BaseModel):
    """Only fixed reason/status labels and counters may reach eval summaries."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    reason: Literal[
        "missing_terminal", "multiple_terminals", "terminal_not_last",
        "terminal_tool_error", "terminal_result_not_string", "invalid_terminal_payload",
    ]
    presentation_count: int = Field(ge=0)
    tool_execution_count: int = Field(ge=0)
    run_status: Literal[
        "PENDING", "RUNNING", "COMPLETED", "PAUSED", "CANCELLED", "ERROR", "REGENERATED", "UNKNOWN",
    ]


class EvalPresentationError(InvalidPresentationOutputError):
    """Preserve structural facts, never provider text, arguments or rejected prose."""

    def __init__(self, diagnostic: TerminalDiagnostic):
        super().__init__("Eval run returned invalid terminal presentation")
        self.diagnostic = diagnostic


def terminal_diagnostic(output: "RunOutput") -> TerminalDiagnostic:
    """Describe a rejected result without changing the production acceptance rules."""
    from src.agent.reply_presentation import PRESENT_REPLY_TOOL

    tools = output.tools or []
    presentations = [item for item in tools if item.tool_name == PRESENT_REPLY_TOOL]
    reason = "invalid_terminal_payload"
    if not presentations:
        reason = "missing_terminal"
    elif len(presentations) != 1:
        reason = "multiple_terminals"
    elif tools[-1] is not presentations[0]:
        reason = "terminal_not_last"
    elif presentations[0].tool_call_error:
        reason = "terminal_tool_error"
    elif not isinstance(presentations[0].result, str):
        reason = "terminal_result_not_string"
    raw_status = getattr(output.status, "value", output.status)
    status = raw_status if isinstance(raw_status, str) and raw_status in {
        "PENDING", "RUNNING", "COMPLETED", "PAUSED", "CANCELLED", "ERROR", "REGENERATED",
    } else "UNKNOWN"
    return TerminalDiagnostic.model_validate({
        "reason": reason, "presentation_count": len(presentations),
        "tool_execution_count": len(tools), "run_status": status,
    })


def safe_terminal_diagnostic(value: object) -> dict[str, object] | None:
    """Revalidate stored metadata; malformed/extra fields never become public output."""
    try:
        return TerminalDiagnostic.model_validate(value).model_dump()
    except ValidationError:
        return None


def safe_error_class(value: object) -> str | None:
    """Historical checkpoints may have arbitrary exception class names; do not echo them."""
    if value is None:
        return None
    return value if isinstance(value, str) and value in {
        "InvalidPresentationOutputError", "ValueError", "ValidationError", "TimeoutError",
        "CancelledError", "RuntimeError", "OSError", "FileExistsError", "PermissionError",
        "ExecutionBudgetExceededError", "ModelProviderError", "HTTPStatusError", "ConnectError",
        "EvalSessionError",
    } else "OtherError"
