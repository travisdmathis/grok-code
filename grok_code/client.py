"""xAI API client for Grok models"""

import html
import json
import os
from dataclasses import dataclass, field
from typing import Callable

import httpx


def _unescape_html_in_dict(obj):
    """Recursively unescape HTML entities in strings within a dict/list"""
    if isinstance(obj, str):
        return html.unescape(obj)
    elif isinstance(obj, dict):
        return {k: _unescape_html_in_dict(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_unescape_html_in_dict(item) for item in obj]
    return obj


XAI_API_BASE = "https://api.x.ai/v1"
DEFAULT_MODEL = "grok-3-latest"


@dataclass
class ToolCall:
    """Represents a tool call from the model"""

    id: str
    name: str
    arguments: dict


@dataclass
class StreamChunk:
    """A chunk from the streaming response"""

    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str | None = None


@dataclass
class Message:
    """A message in the conversation"""

    role: str
    content: str | None = None
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None
    name: str | None = None

    def to_dict(self) -> dict:
        """Convert to API format"""
        d = {"role": self.role}
        if self.content is not None:
            d["content"] = self.content
        if self.tool_calls:
            d["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
                }
                for tc in self.tool_calls
            ]
        if self.tool_call_id:
            d["tool_call_id"] = self.tool_call_id
        if self.name:
            d["name"] = self.name
        return d


class GrokClient:
    """Client for xAI's Grok API"""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL,
        base_url: str = XAI_API_BASE,
    ):
        self.api_key = api_key or os.environ.get("XAI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "XAI_API_KEY not found. Set it as an environment variable or pass it to GrokClient."
            )
        self.model = model
        self.base_url = base_url
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(120.0, connect=10.0),
        )

    async def close(self):
        """Close the HTTP client"""
        await self._client.aclose()

    async def chat(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        temperature: float = 0.7,
    ) -> Message:
        """Send a chat request and get a complete response"""
        payload = {
            "model": self.model,
            "messages": [m.to_dict() for m in messages],
            "temperature": temperature,
        }
        if tools:
            payload["tools"] = tools

        response = await self._client.post("/chat/completions", json=payload)
        response.raise_for_status()
        data = response.json()

        choice = data["choices"][0]
        msg = choice["message"]

        tool_calls = None
        if msg.get("tool_calls"):
            tool_calls = [
                ToolCall(
                    id=tc["id"],
                    name=tc["function"]["name"],
                    arguments=_unescape_html_in_dict(json.loads(tc["function"]["arguments"])),
                )
                for tc in msg["tool_calls"]
            ]

        return Message(
            role=msg["role"],
            content=msg.get("content"),
            tool_calls=tool_calls,
        )

    async def chat_stream(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        temperature: float = 0.7,
        on_content: Callable[[str], None] | None = None,
        max_retries: int = 2,
    ) -> Message:
        """Send a chat request with streaming response"""
        payload = {
            "model": self.model,
            "messages": [m.to_dict() for m in messages],
            "temperature": temperature,
            "stream": True,
        }
        if tools:
            payload["tools"] = tools

        last_error = None
        for attempt in range(max_retries + 1):
            full_content = ""
            tool_calls_data: dict[int, dict] = {}

            try:
                async with self._client.stream(
                    "POST", "/chat/completions", json=payload
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            break

                        try:
                            data = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue

                        choice = data.get("choices", [{}])[0]
                        delta = choice.get("delta", {})

                        # Handle content
                        if delta.get("content"):
                            content = delta["content"]
                            full_content += content
                            if on_content:
                                on_content(content)

                        # Handle tool calls
                        if delta.get("tool_calls"):
                            for tc in delta["tool_calls"]:
                                idx = tc["index"]
                                if idx not in tool_calls_data:
                                    tool_calls_data[idx] = {
                                        "id": tc.get("id", ""),
                                        "name": "",
                                        "arguments": "",
                                    }
                                if tc.get("id"):
                                    tool_calls_data[idx]["id"] = tc["id"]
                                if tc.get("function", {}).get("name"):
                                    tool_calls_data[idx]["name"] = tc["function"]["name"]
                                if tc.get("function", {}).get("arguments"):
                                    tool_calls_data[idx]["arguments"] += tc["function"]["arguments"]

                # Build tool calls
                tool_calls = None
                if tool_calls_data:
                    tool_calls = []
                    for idx in sorted(tool_calls_data.keys()):
                        tc_data = tool_calls_data[idx]
                        try:
                            args = (
                                _unescape_html_in_dict(json.loads(tc_data["arguments"]))
                                if tc_data["arguments"]
                                else {}
                            )
                        except json.JSONDecodeError:
                            args = {}
                        tool_calls.append(
                            ToolCall(id=tc_data["id"], name=tc_data["name"], arguments=args)
                        )

                return Message(
                    role="assistant",
                    content=full_content if full_content else None,
                    tool_calls=tool_calls,
                )

            except (httpx.RemoteProtocolError, httpx.ReadError, httpx.ConnectError) as e:
                last_error = e
                if attempt < max_retries:
                    # Wait before retry
                    import asyncio

                    await asyncio.sleep(1.0 * (attempt + 1))
                    continue
                # If we got partial content, return what we have
                if full_content:
                    return Message(
                        role="assistant",
                        content=full_content + "\n\n[Response interrupted - connection error]",
                        tool_calls=None,
                    )
                raise RuntimeError(
                    f"API connection failed after {max_retries + 1} attempts: {e}"
                ) from e

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
