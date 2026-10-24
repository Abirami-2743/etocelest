"""Groq (OpenAI-compatible) chat-completions client with retries and validated JSON output."""

from __future__ import annotations

import asyncio
import json
import logging
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.config import BEST_EFFORT_SCHEMA_MODELS, STRICT_SCHEMA_MODELS, Settings

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)

RetryNotifier = Callable[[str], Awaitable[None]]


class LLMError(Exception):
    """Retryable-exhausted or otherwise failed LLM call."""


class LLMFatalError(LLMError):
    """Configuration problem (bad key, bad model). Retrying cannot help."""


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0

    def add(self, other: Usage) -> None:
        self.prompt_tokens += other.prompt_tokens
        self.completion_tokens += other.completion_tokens


@dataclass
class Completion:
    content: str
    usage: Usage
    finish_reason: str | None


class GroqClient:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._s = settings
        self._http = httpx.AsyncClient(
            base_url=settings.groq_base_url.rstrip("/"),
            headers={
                "Authorization": f"Bearer {settings.require_llm_key()}",
                "Content-Type": "application/json",
            },
            timeout=settings.llm_timeout_seconds,
            transport=transport,
        )
        self._sem = asyncio.Semaphore(settings.llm_max_concurrency)

    async def aclose(self) -> None:
        await self._http.aclose()

    # -- request shaping ---------------------------------------------------
    def response_format(self, model: str, name: str, schema: dict[str, Any]) -> dict[str, Any]:
        mode = self._s.groq_structured_mode
        if mode == "auto":
            if model in STRICT_SCHEMA_MODELS:
                mode, strict = "json_schema", True
            elif model in BEST_EFFORT_SCHEMA_MODELS:
                mode, strict = "json_schema", False
            else:
                mode, strict = "json_object", False
        else:
            strict = model in STRICT_SCHEMA_MODELS
        if mode == "json_object":
            return {"type": "json_object"}
        return {"type": "json_schema", "json_schema": {"name": name, "strict": strict, "schema": schema}}

    # -- single HTTP call with retry --------------------------------------
    async def complete(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        response_format: dict[str, Any],
        on_retry: RetryNotifier | None = None,
    ) -> Completion:
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_completion_tokens": max_tokens,
            "response_format": response_format,
        }
        if self._s.groq_reasoning_effort:
            body["reasoning_effort"] = self._s.groq_reasoning_effort

        attempts = self._s.llm_max_retries + 1
        last_reason = "unknown error"
        for attempt in range(attempts):
            delay: float | None = None
            try:
                async with self._sem:
                    resp = await self._http.post("/chat/completions", json=body)
            except httpx.HTTPError as exc:
                last_reason = f"network error ({type(exc).__name__})"
                delay = self._backoff(attempt, None)
            else:
                if resp.status_code == 200:
                    return self._parse(resp)
                if resp.status_code in (401, 403):
                    raise LLMFatalError(f"Groq rejected the API key (HTTP {resp.status_code})")
                if resp.status_code == 429 or resp.status_code >= 500:
                    last_reason = f"HTTP {resp.status_code}"
                    delay = self._backoff(attempt, resp.headers.get("retry-after"))
                else:
                    detail = self._error_detail(resp)
                    if resp.status_code in (400, 404):
                        raise LLMFatalError(f"Groq rejected the request (HTTP {resp.status_code}): {detail}")
                    raise LLMError(f"Groq returned HTTP {resp.status_code}: {detail}")

            if attempt == attempts - 1:
                break
            assert delay is not None
            logger.warning("groq retry model=%s attempt=%d reason=%s delay=%.1fs", model, attempt + 1, last_reason, delay)
            if on_retry:
                await on_retry(f"Groq {last_reason}; retrying in {delay:.0f}s")
            await asyncio.sleep(delay)
        raise LLMError(f"Groq unavailable after {attempts} attempts: {last_reason}")

    def _backoff(self, attempt: int, retry_after: str | None) -> float:
        cap = self._s.llm_max_backoff_seconds
        if retry_after:
            try:
                return min(cap, max(0.0, float(retry_after))) + random.uniform(0, 0.5)  # noqa: S311
            except ValueError:
                pass
        return min(cap, 2.0 * (2**attempt)) * random.uniform(0.75, 1.25)  # noqa: S311

    @staticmethod
    def _error_detail(resp: httpx.Response) -> str:
        try:
            err = resp.json().get("error", {})
            return str(err.get("message") or err)[:300]
        except Exception:  # noqa: BLE001
            return resp.text[:300]

    @staticmethod
    def _parse(resp: httpx.Response) -> Completion:
        try:
            data = resp.json()
            choice = data["choices"][0]
            content = choice["message"]["content"] or ""
            u = data.get("usage") or {}
            return Completion(
                content=content,
                usage=Usage(int(u.get("prompt_tokens", 0)), int(u.get("completion_tokens", 0))),
                finish_reason=choice.get("finish_reason"),
            )
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise LLMError(f"Malformed Groq response: {exc}") from exc

    # -- validated structured output --------------------------------------
    async def structured(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        output: type[T],
        schema_name: str,
        schema: dict[str, Any],
        temperature: float,
        max_tokens: int,
        validate: Callable[[T], None] | None = None,
        on_retry: RetryNotifier | None = None,
    ) -> tuple[T, Usage]:
        """Call the model and return a validated `output`, re-asking on invalid output."""
        usage = Usage()
        convo = list(messages)
        rf = self.response_format(model, schema_name, schema)
        problem = ""
        for attempt in range(self._s.llm_validation_attempts):
            comp = await self.complete(
                model=model, messages=convo, temperature=temperature,
                max_tokens=max_tokens, response_format=rf, on_retry=on_retry,
            )
            usage.add(comp.usage)
            try:
                if comp.finish_reason == "length":
                    raise ValueError("the response was cut off (token limit); be more concise")
                parsed = output.model_validate(json.loads(comp.content))
                if validate:
                    validate(parsed)
                return parsed, usage
            except (json.JSONDecodeError, ValidationError, ValueError) as exc:
                problem = _short(exc)
                logger.warning("invalid model output model=%s attempt=%d problem=%s", model, attempt + 1, problem)
                convo = [
                    *messages,
                    {"role": "assistant", "content": comp.content[:4000]},
                    {
                        "role": "user",
                        "content": "Your previous reply was rejected: "
                        f"{problem}\nReply again with ONLY a corrected JSON object that satisfies the schema.",
                    },
                ]
        raise LLMError(f"Model produced invalid output {self._s.llm_validation_attempts} times: {problem}")


def _short(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        return "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())[:500]
    return str(exc)[:500]
