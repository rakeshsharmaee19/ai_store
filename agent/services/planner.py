"""
The Planner turns raw OpenAI tool-call requests into validated, executable
steps. Kept separate from the agent loop itself so the "decide what to run
next" concern is testable in isolation from the HTTP/LLM plumbing.
"""
from dataclasses import dataclass

from .llm_service import ToolCallRequest


@dataclass
class PlannedStep:
    tool_call_id: str
    tool_name: str
    arguments: dict


def plan_from_tool_calls(tool_calls: list[ToolCallRequest]) -> list[PlannedStep]:
    return [PlannedStep(tool_call_id=tc.id, tool_name=tc.name, arguments=tc.arguments) for tc in tool_calls]
