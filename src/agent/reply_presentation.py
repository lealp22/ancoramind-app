"""Terminal presentation tool; no canonical writes or additional inference."""

from agno.models.response import ToolExecution
from agno.run import RunContext
from agno.run.agent import RunOutput
from agno.tools.function import Function

from src.agent.instructions import load_prompt
from src.domain.interactions.reply import AgentReply, InvalidPresentationOutputError

PRESENT_REPLY_TOOL = "present_reply"


def build_reply_presentation_tool() -> Function:
    """Create a fresh terminal adapter for each Agent, with a versioned contract."""

    async def present_reply(run_context: RunContext, answer: str, proposal_text: str) -> str:
        """Validate the presentation partition and end the current Agent run."""
        return AgentReply(answer=answer, proposal_text=proposal_text).model_dump_json()

    function = Function.from_callable(present_reply)
    function.description = load_prompt("skills/presentation.md")
    function.stop_after_tool_call = True
    function.show_result = False
    return function


def reply_from_run(output: RunOutput) -> AgentReply:
    """Accept only the validated result of one successful terminal tool call.

    Neither assistant prose, a JSON-shaped completion nor tool arguments alone
    prove that the presentation adapter ran. A premature textual completion
    must not be delivered as a promise of work that will never run.
    """
    executions = getattr(output, "tools", None) or []
    presentations = [item for item in executions if item.tool_name == PRESENT_REPLY_TOOL]
    if (
        len(presentations) != 1
        or executions[-1] is not presentations[0]
        or presentations[0].tool_call_error
        or not isinstance(presentations[0].result, str)
    ):
        raise InvalidPresentationOutputError("Agent run returned invalid presentation output")
    return AgentReply.model_validate_json(presentations[0].result)


def domain_tool_executions(output: RunOutput) -> list[ToolExecution]:
    """Presentation is control flow, not a domain capability in eval verdicts."""
    return [item for item in (output.tools or []) if item.tool_name != PRESENT_REPLY_TOOL]
