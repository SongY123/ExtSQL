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


@dataclass(frozen=True)
class ChatCompletionResult:
    content: str
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    inference_time_ms: float


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
        return self.complete_with_metrics(
            prompt=prompt,
            system_prompt=system_prompt,
        ).content

    def complete_with_metrics(
        self,
        *,
        prompt: str,
        system_prompt: str,
    ) -> ChatCompletionResult:
        last_error: Exception | None = None
        attempts = max(1, self.config.retries)
        messages = []
        if system_prompt.strip():
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        started = time.perf_counter()
        for attempt in range(1, attempts + 1):
            try:
                response = self._client.chat.completions.create(
                    model=self.config.model,
                    messages=messages,
                    temperature=self.config.temperature,
                    max_tokens=self.config.max_tokens,
                    timeout=self.config.request_timeout,
                )
                inference_time_ms = (time.perf_counter() - started) * 1000.0
                input_tokens, output_tokens, total_tokens = _extract_usage(response)
                return ChatCompletionResult(
                    content=_extract_message_content(response),
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=total_tokens,
                    inference_time_ms=inference_time_ms,
                )
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


def _extract_usage(response: Any) -> tuple[int | None, int | None, int | None]:
    usage = getattr(response, "usage", None)
    if usage is None and isinstance(response, dict):
        usage = response.get("usage")

    input_tokens = _usage_int(usage, "prompt_tokens", "input_tokens")
    output_tokens = _usage_int(usage, "completion_tokens", "output_tokens")
    reported_total = _usage_int(usage, "total_tokens")
    total_tokens = (
        input_tokens + output_tokens
        if input_tokens is not None and output_tokens is not None
        else reported_total
    )
    return input_tokens, output_tokens, total_tokens


def _usage_int(usage: Any, *names: str) -> int | None:
    if usage is None:
        return None
    for name in names:
        value = usage.get(name) if isinstance(usage, dict) else getattr(usage, name, None)
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                return None
    return None
