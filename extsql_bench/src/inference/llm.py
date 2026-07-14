"""OpenAI-compatible chat-completion client for SQL inference."""

from __future__ import annotations

from dataclasses import dataclass
import re
import time
from typing import Any


@dataclass(frozen=True)
class ChatConfig:
    model: str
    api_key: str
    base_url: str | None = None
    temperature: float = 0.0
    max_tokens: int = 512
    request_timeout: float = 120.0
    retries: int = 3
    retry_sleep: float = 2.0


class OpenAICompatibleChatClient:
    """Small wrapper around the OpenAI Python client.

    Use ``base_url`` to target vLLM, LiteLLM, or another OpenAI-compatible
    endpoint. For local vLLM servers, any non-empty API key is usually accepted.
    """

    def __init__(self, config: ChatConfig):
        if not config.model:
            raise ValueError("model is required")
        self.config = config
        self._client = self._build_client(config)

    def complete(self, *, prompt: str, system_prompt: str) -> str:
        last_error: Exception | None = None
        attempts = max(1, self.config.retries)
        messages = []
        if system_prompt.strip():
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        for attempt in range(1, attempts + 1):
            try:
                response = self._client.chat.completions.create(
                    model=self.config.model,
                    messages=messages,
                    temperature=self.config.temperature,
                    max_tokens=self.config.max_tokens,
                    timeout=self.config.request_timeout,
                )
                return _extract_message_content(response)
            except Exception as exc:  # noqa: BLE001 - retry external API failures
                last_error = exc
                if attempt < attempts:
                    time.sleep(self.config.retry_sleep * attempt)
        raise RuntimeError(f"LLM request failed after {attempts} attempt(s): {last_error}")

    @staticmethod
    def _build_client(config: ChatConfig):
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError(
                "Missing dependency: install openai or run `pip install -r requirements.txt`."
            ) from exc

        kwargs: dict[str, Any] = {"api_key": config.api_key or "EMPTY"}
        if config.base_url:
            kwargs["base_url"] = config.base_url
        return OpenAI(**kwargs)


def clean_sql_response(text: str) -> str:
    sql = str(text or "").strip()
    fenced = re.findall(r"```(?:sql|postgresql|postgres)?\s*(.*?)```", sql, flags=re.I | re.S)
    if fenced:
        sql = fenced[-1].strip()

    sql = re.sub(r"^\s*(?:SQL|PostgreSQL SQL|Answer)\s*:\s*", "", sql, flags=re.I).strip()
    if sql.startswith("```"):
        sql = re.sub(r"^```[A-Za-z0-9_-]*\s*", "", sql).strip()
    if sql.endswith("```"):
        sql = sql[:-3].strip()
    return sql


def _extract_message_content(response: Any) -> str:
    try:
        content = response.choices[0].message.content
    except (AttributeError, IndexError, TypeError) as exc:
        raise RuntimeError(f"Unexpected chat completion response: {response!r}") from exc

    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                value = item.get("text") or item.get("content")
                if value:
                    parts.append(str(value))
            else:
                parts.append(str(item))
        return "\n".join(parts)
    return str(content or "")
