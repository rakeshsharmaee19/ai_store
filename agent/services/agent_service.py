"""
AgentService: orchestrates the full agentic loop described in the project
README --

    User -> DRF View -> AgentService -> LLM -> tool call? -> Tool Registry
    -> Permission check -> Tool Handler -> Django Service -> DB/Stripe/Web3
    -> Tool Result -> LLM -> next tool OR final answer

This is intentionally the ONLY place that ties the LLM, the tool executor,
and conversation persistence together.
"""
import logging

from django.conf import settings

from common.constants import ROLE_ASSISTANT, ROLE_TOOL, ROLE_USER
from common.exceptions import ApplicationError, ToolExecutionError

from ..models import AgentConversation, AgentMessage
from .context_service import build_messages
from .executor import execute_tool
from .llm_service import LLMService
from .planner import plan_from_tool_calls

logger = logging.getLogger("agent")


class AgentService:
    def __init__(self, llm_service: LLMService | None = None):
        self.llm_service = llm_service or LLMService()

    def handle_message(self, *, user, conversation: AgentConversation | None, message: str) -> dict:
        if conversation is None:
            conversation = AgentConversation.objects.create(user=user, title=message[:80])

        AgentMessage.objects.create(conversation=conversation, role=ROLE_USER, content=message)

        from ..tools.registry import registry

        tools_schema = registry.as_openai_tools()

        # Live OpenAI-protocol message list for this turn (system + history +
        # the new user message + any tool round-trips). This is separate from
        # what we persist to AgentMessage, which stores a simpler human-
        # readable transcript.
        live_messages = build_messages(conversation)

        final_answer = None
        iterations = 0

        while iterations < settings.AGENT_MAX_ITERATIONS:
            iterations += 1
            llm_response = self.llm_service.get_completion(messages=live_messages, tools=tools_schema)

            if not llm_response.tool_calls:
                final_answer = llm_response.content or ""
                break

            # Record the assistant's tool-call turn so a real OpenAI-protocol
            # conversation could be replayed if needed.
            live_messages.append(
                {
                    "role": "assistant",
                    "content": llm_response.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.name, "arguments": "{}"},
                        }
                        for tc in llm_response.tool_calls
                    ],
                }
            )

            steps = plan_from_tool_calls(llm_response.tool_calls)
            for step in steps:
                try:
                    result = execute_tool(
                        conversation=conversation, user=user, tool_name=step.tool_name, arguments=step.arguments
                    )
                    tool_message_content = {"ok": True, "result": result}
                except ApplicationError as exc:
                    tool_message_content = {"ok": False, "error": {"code": exc.code, "message": exc.message}}

                AgentMessage.objects.create(
                    conversation=conversation, role=ROLE_TOOL, content=str(tool_message_content)
                )
                live_messages.append(
                    {"role": "tool", "tool_call_id": step.tool_call_id, "content": str(tool_message_content)}
                )

        if final_answer is None:
            final_answer = (
                "I reached the maximum number of tool iterations without producing a final answer. "
                "Please refine your request or try again."
            )
            logger.warning("agent_max_iterations_reached conversation_id=%s", conversation.id)

        AgentMessage.objects.create(conversation=conversation, role=ROLE_ASSISTANT, content=final_answer)

        return {
            "conversation_id": conversation.id,
            "message": final_answer,
            "iterations": iterations,
        }
