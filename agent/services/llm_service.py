"""
Thin wrapper around the OpenAI API. This is the ONLY module allowed to
import the `openai` SDK. It knows nothing about Django models -- it just
turns a list of chat messages + tool schemas into a completion, using
OpenAI's function/tool calling.
"""
import json
import logging
from dataclasses import dataclass

from django.conf import settings

logger = logging.getLogger("agent")


@dataclass
class ToolCallRequest:
    id: str
    name: str
    arguments: dict


@dataclass
class LLMResponse:
    content: str | None
    tool_calls: list[ToolCallRequest]


class LLMService:
    def __init__(self, model: str | None = None):
        self.model = model or settings.OPENAI_MODEL

    def _client(self):
        from openai import OpenAI

        return OpenAI(api_key=settings.OPENAI_API_KEY)

    def get_completion(self, *, messages: list[dict], tools: list[dict]) -> LLMResponse:
        client = self._client()
        response = client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=tools,
            tool_choice="auto",
        )
        choice = response.choices[0]
        message = choice.message

        tool_calls = []
        for tc in (message.tool_calls or []):
            try:
                arguments = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                logger.warning("llm_returned_invalid_json_arguments tool=%s", tc.function.name)
                arguments = {}
            tool_calls.append(ToolCallRequest(id=tc.id, name=tc.function.name, arguments=arguments))

        return LLMResponse(content=message.content, tool_calls=tool_calls)
