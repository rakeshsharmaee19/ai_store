"""
The Tool Executor: takes a tool name + raw arguments (as produced by the
LLM), and safely runs it through the full authorization + validation
pipeline before ever touching a Django service.

This module is the actual security boundary described in the project's
architecture: the LLM decides WHAT to call, but Django decides WHETHER it
is allowed to happen.
"""
import logging

from common.exceptions import ToolExecutionError, ToolNotFound, UnauthorizedAction
from ..models import AgentToolCall
from ..tools.registry import registry

logger = logging.getLogger("agent")


def execute_tool(*, conversation, user, tool_name: str, arguments: dict) -> dict:
    """
    1. Find tool in registry (raise ToolNotFound if unknown).
    2. Verify the user's Django permission for that tool.
    3. Validate arguments loosely (required keys present).
    4. Execute the Python handler -- never eval/exec.
    5. Persist an AgentToolCall audit row regardless of outcome.
    6. Return the tool result (or raise, which the caller turns into an
       error result fed back to the LLM).
    """
    tool = registry.get(tool_name)
    if tool is None:
        _record_call(conversation, tool_name, arguments, status="FAILED", error="Unknown tool.")
        raise ToolNotFound(f"Tool '{tool_name}' is not registered.")

    if tool.required_permission and not user.has_perm(tool.required_permission):
        _record_call(conversation, tool_name, arguments, status="FAILED", error="Permission denied.")
        raise UnauthorizedAction(f"User lacks permission '{tool.required_permission}' for tool '{tool_name}'.")

    required_keys = set(tool.parameters.get("required", []))
    missing = required_keys - set(arguments.keys())
    if missing:
        _record_call(conversation, tool_name, arguments, status="FAILED", error=f"Missing arguments: {missing}")
        raise ToolExecutionError(f"Missing required arguments for '{tool_name}': {sorted(missing)}")

    call_kwargs = dict(arguments)
    if tool.needs_context:
        call_kwargs.setdefault("conversation_id", conversation.id if conversation else None)
        call_kwargs.setdefault("requested_by_id", user.id if user else None)

    try:
        result = tool.handler(**call_kwargs)
    except (ToolExecutionError, UnauthorizedAction):
        raise
    except Exception as exc:  # noqa: BLE001 - never let a handler crash the agent loop
        logger.exception("tool_execution_unexpected_error tool=%s", tool_name)
        _record_call(conversation, tool_name, arguments, status="FAILED", error=str(exc))
        raise ToolExecutionError(f"Tool '{tool_name}' raised an unexpected error.") from exc

    _record_call(conversation, tool_name, arguments, status="SUCCESS", result=result)
    return result


def _record_call(conversation, tool_name: str, arguments: dict, *, status: str, result: dict | None = None, error: str = "") -> None:
    if conversation is None:
        return
    AgentToolCall.objects.create(
        conversation=conversation,
        tool_name=tool_name,
        arguments=arguments,
        result=result,
        status=status,
        error=error,
    )
