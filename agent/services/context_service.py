"""
Builds the message list sent to the LLM: a system prompt plus a bounded
window of recent conversation history from PostgreSQL. We deliberately do
NOT send the entire conversation forever -- that would blow up token usage
and cost on long-running conversations.
"""
from common.constants import ROLE_ASSISTANT, ROLE_SYSTEM, ROLE_TOOL, ROLE_USER
from ..models import AgentConversation
from ..prompts.support_agent import SUPPORT_AGENT_SYSTEM_PROMPT

MAX_HISTORY_MESSAGES = 20  # recent messages included as context, tune as needed


def build_messages(conversation: AgentConversation) -> list[dict]:
    recent_messages = list(
        conversation.messages.order_by("-created_at")[:MAX_HISTORY_MESSAGES]
    )
    recent_messages.reverse()

    messages = [{"role": ROLE_SYSTEM, "content": SUPPORT_AGENT_SYSTEM_PROMPT}]
    for msg in recent_messages:
        if msg.role in (ROLE_USER, ROLE_ASSISTANT):
            messages.append({"role": msg.role, "content": msg.content})
        elif msg.role == ROLE_TOOL:
            # Tool results are replayed as assistant-visible context; the raw
            # OpenAI tool-call protocol messages are reconstructed live during
            # the loop itself (see agent_service.py) rather than persisted
            # verbatim, keeping storage simple and provider-agnostic.
            messages.append({"role": "assistant", "content": f"[tool result] {msg.content}"})
    return messages
