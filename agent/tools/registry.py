"""
The Tool Registry: the single source of truth for what the LLM is allowed
to do. Every tool is declared here with its JSON schema, its Django
permission requirement, and whether it is read-only or requires human
confirmation before executing.

CRITICAL SECURITY PROPERTY: this registry is the ONLY way the agent
executor can reach application code. There is no eval(), no exec(), no
dynamic import of arbitrary code. The LLM can only ever select one of the
tool names declared here, with arguments matching the declared schema.
"""
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: dict[str, Any]  # JSON schema, sent to the LLM as the tool's input schema
    handler: Callable[..., dict]
    required_permission: str | None  # e.g. "agent.can_read_order"; None = no extra permission needed
    read_only: bool = True
    requires_confirmation: bool = False
    needs_context: bool = False  # if True, the executor injects conversation_id/requested_by_id


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' is already registered.")
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolDefinition | None:
        return self._tools.get(name)

    def all(self) -> list[ToolDefinition]:
        return list(self._tools.values())

    def as_openai_tools(self) -> list[dict]:
        """Serialize the registry into the OpenAI function-calling tool schema."""
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
            for tool in self._tools.values()
        ]


registry = ToolRegistry()


def _register_all_tools() -> None:
    """
    Imports each tool module, which registers its own ToolDefinitions into
    `registry` as a side effect. Kept in one place so the import order (and
    therefore the full set of available tools) is explicit and auditable.
    """
    from . import (  # noqa: F401
        action_tools,
        order_tools,
        payment_tools,
        product_tools,
        transaction_tools,
        user_tools,
    )


_register_all_tools()
