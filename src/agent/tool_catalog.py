"""Keep deterministic execution capabilities outside the model's tool surface."""

from typing import Any


def proposal_only_tools(tools: list[Any]) -> list[Any]:
    """Exclude legacy execute adapters, including Agno Function wrappers.

    Reads, proposals and approved attachment/export exceptions remain available.
    Human confirmation and execution belong to the Core interaction processor,
    never to either the governed Agent or the transitional AgentOS singleton.
    """
    return [
        tool
        for tool in tools
        if not str(getattr(tool, "__name__", getattr(tool, "name", ""))).startswith("execute_")
    ]
