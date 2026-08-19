"""OmniRoute LLM client for clinical answer generation.

Every call is instrumented: request latency, retries, token usage as reported
by the gateway, finish reason, and — for streaming — time to first token and
inter-token throughput. Those are the numbers that explain a slow answer, so
they are logged whether the call succeeds or fails.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx

from backend.app.config import Settings, get_settings
from backend.app.errors import ConfigurationError, PipelineError
from backend.app.monitoring import REGISTRY, estimate_tokens, trace_span

logger = logging.getLogger(__name__)


MAX_ATTEMPTS = 3
BACKOFF_BASE_SECONDS = 1.0
REQUEST_TIMEOUT_SECONDS = 60.0
RETRY_STATUS = {408, 409, 429, 500, 502, 503, 504}


def _usage_fields(usage: dict[str, Any] | None) -> dict[str, Any]:
    """Normalize the gateway's usage block into flat log fields."""
    if not isinstance(usage, dict):
        return {}
    return {
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
    }


class LLMClient:
    """Async client for the OmniRoute OpenAI-compatible chat completions API."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._api_key = self._settings.openrouter_api_key
        self._base_url = self._settings.openrouter_base_url.rstrip("/")

        # Populated after each call so the caller (and its RagTrace) can log
        # what the generation actually cost without re-parsing the response.
        self.last_usage: dict[str, Any] = {}
        self.last_latency_ms: float = 0.0
        self.last_ttft_ms: float | None = None
        self.last_finish_reason: str | None = None
        self.last_attempts: int = 0

    def _require_key(self) -> None:
        if not self._api_key:
            raise ConfigurationError(
                "OMNIROUTE_API_KEY is not set. Set it in .env to enable LLM generation."
            )

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://eva-ai.local",
            "X-Title": "Eva AI",
        }

    def _payload(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        return {
            "model": self._settings.generation_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": self._settings.generation_max_tokens,
            "temperature": self._settings.generation_temperature,
            # Explicit: some OmniRoute routes default to SSE when `stream` is absent,
            # which breaks the non-streaming JSON parse in generate_completion().
            "stream": False,
        }

    def _log_request(self, system_prompt: str, user_prompt: str, streaming: bool) -> dict[str, Any]:
        """Log the outbound call and return shared fields for the result line."""
        prompt_chars = len(system_prompt) + len(user_prompt)
        fields = {
            "provider": "omniroute",
            "model": self._settings.generation_model,
            "streaming": streaming,
            "prompt_chars": prompt_chars,
            "est_prompt_tokens": estimate_tokens(system_prompt + user_prompt),
            "max_tokens": self._settings.generation_max_tokens,
            "temperature": self._settings.generation_temperature,
        }
        logger.info(
            "llm.request %s model=%s prompt_chars=%d max_tokens=%d temp=%.2f",
            "stream" if streaming else "sync",
            self._settings.generation_model,
            prompt_chars,
            self._settings.generation_max_tokens,
            self._settings.generation_temperature,
            extra={"event": "llm.request", **fields},
        )
        if self._settings.log_prompt_preview:
            limit = self._settings.log_preview_chars
            logger.debug(
                "llm.prompt preview",
                extra={
                    "event": "llm.prompt",
                    "system_preview": system_prompt[:limit],
                    "user_preview": user_prompt[:limit],
                },
            )
        return fields

    async def generate_completion(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        """Call the OmniRoute chat completions API with exponential backoff."""
        with trace_span(op="llm.generate", description="OmniRoute Chat Completion"):
            self._require_key()

            endpoint = f"{self._base_url}/chat/completions"
            headers = self._headers()
            payload = self._payload(system_prompt, user_prompt)
            log_fields = self._log_request(system_prompt, user_prompt, streaming=False)
            call_started = time.perf_counter()
            self.last_usage = {}
            self.last_ttft_ms = None
            self.last_finish_reason = None
            self.last_attempts = 0

            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
                last_error: Exception | None = None
                for attempt in range(1, MAX_ATTEMPTS + 1):
                    self.last_attempts = attempt
                    attempt_started = time.perf_counter()
                    try:
                        response = await client.post(endpoint, json=payload, headers=headers)

                        if response.status_code == 200:
                            data = response.json()
                            choices = data.get("choices", [])
                            if not choices:
                                self._log_failure(
                                    log_fields,
                                    call_started,
                                    attempt,
                                    "empty_choices",
                                )
                                raise PipelineError("OmniRoute returned an empty choices list.")
                            message = choices[0].get("message", {})
                            content = message.get("content", "")

                            usage = _usage_fields(data.get("usage"))
                            self.last_usage = usage
                            self.last_finish_reason = choices[0].get("finish_reason")
                            self.last_latency_ms = (time.perf_counter() - call_started) * 1000
                            REGISTRY.observe("llm.generate", self.last_latency_ms)
                            REGISTRY.increment("llm.calls")
                            if usage.get("total_tokens"):
                                REGISTRY.increment("llm.total_tokens", int(usage["total_tokens"]))

                            completion_tokens = usage.get("completion_tokens") or estimate_tokens(
                                content
                            )
                            tps = (
                                completion_tokens / (self.last_latency_ms / 1000)
                                if self.last_latency_ms > 0
                                else 0.0
                            )
                            logger.info(
                                "llm.response ok in %.0f ms (attempt %d, %s chars, "
                                "%s completion tokens, %.1f tok/s, finish=%s)",
                                self.last_latency_ms,
                                attempt,
                                len(content),
                                completion_tokens,
                                tps,
                                self.last_finish_reason,
                                extra={
                                    "event": "llm.response",
                                    **log_fields,
                                    **usage,
                                    "ok": True,
                                    "attempt": attempt,
                                    "duration_ms": round(self.last_latency_ms, 2),
                                    "answer_chars": len(content),
                                    "tokens_per_second": round(tps, 2),
                                    "finish_reason": self.last_finish_reason,
                                },
                            )
                            # A truncated answer is a silent quality failure:
                            # surface it rather than letting it look normal.
                            if self.last_finish_reason == "length":
                                logger.warning(
                                    "llm.truncated: completion hit max_tokens=%d - "
                                    "the answer is cut off.",
                                    self._settings.generation_max_tokens,
                                    extra={
                                        "event": "llm.truncated",
                                        **log_fields,
                                        **usage,
                                    },
                                )
                            if self._settings.log_prompt_preview:
                                logger.debug(
                                    "llm.answer preview",
                                    extra={
                                        "event": "llm.answer",
                                        "preview": content[: self._settings.log_preview_chars],
                                    },
                                )
                            return content

                        if response.status_code in RETRY_STATUS and attempt < MAX_ATTEMPTS:
                            delay = BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))
                            REGISTRY.increment("llm.retries")
                            logger.warning(
                                "OmniRoute HTTP %d on attempt %d/%d; retrying in %.1fs: %s",
                                response.status_code,
                                attempt,
                                MAX_ATTEMPTS,
                                delay,
                                response.text[:300],
                                extra={
                                    "event": "llm.retry",
                                    **log_fields,
                                    "attempt": attempt,
                                    "max_attempts": MAX_ATTEMPTS,
                                    "status_code": response.status_code,
                                    "retry_in_s": delay,
                                    "attempt_ms": round(
                                        (time.perf_counter() - attempt_started) * 1000, 2
                                    ),
                                },
                            )
                            await asyncio.sleep(delay)
                            continue

                        response.raise_for_status()

                    except (httpx.TimeoutException, httpx.NetworkError) as exc:
                        last_error = exc
                        if attempt < MAX_ATTEMPTS:
                            delay = BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))
                            REGISTRY.increment("llm.retries")
                            logger.warning(
                                "Network/timeout error on attempt %d/%d; retrying in %.1fs: %s",
                                attempt,
                                MAX_ATTEMPTS,
                                delay,
                                exc,
                                extra={
                                    "event": "llm.retry",
                                    **log_fields,
                                    "attempt": attempt,
                                    "max_attempts": MAX_ATTEMPTS,
                                    "error": str(exc),
                                    "retry_in_s": delay,
                                },
                            )
                            await asyncio.sleep(delay)
                            continue
                        self._log_failure(log_fields, call_started, attempt, f"network: {exc}")
                        raise PipelineError(
                            f"OmniRoute gateway unreachable after {MAX_ATTEMPTS} attempts: {exc}"
                        ) from exc
                    except httpx.HTTPStatusError as exc:
                        self._log_failure(
                            log_fields,
                            call_started,
                            attempt,
                            f"http_{exc.response.status_code}",
                            status_code=exc.response.status_code,
                        )
                        raise PipelineError(
                            f"OmniRoute API error {exc.response.status_code}: {exc.response.text}"
                        ) from exc
                    except PipelineError:
                        raise
                    except Exception as exc:
                        self._log_failure(log_fields, call_started, attempt, str(exc))
                        raise PipelineError(f"Generation error: {exc}") from exc

                self._log_failure(log_fields, call_started, MAX_ATTEMPTS, str(last_error))
                raise PipelineError(
                    f"Generation failed after {MAX_ATTEMPTS} attempts: {last_error}"
                )

    def _log_failure(
        self,
        log_fields: dict[str, Any],
        call_started: float,
        attempt: int,
        reason: str,
        **extra: Any,
    ) -> None:
        duration_ms = (time.perf_counter() - call_started) * 1000
        self.last_latency_ms = duration_ms
        REGISTRY.observe("llm.generate", duration_ms)
        REGISTRY.increment("llm.errors")
        logger.error(
            "llm.response failed after %.0f ms on attempt %d: %s",
            duration_ms,
            attempt,
            reason,
            extra={
                "event": "llm.response",
                **log_fields,
                "ok": False,
                "attempt": attempt,
                "duration_ms": round(duration_ms, 2),
                "error": reason,
                **extra,
            },
        )

    async def stream_completion(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> AsyncIterator[str]:
        """Stream chat completion content deltas (OpenAI-compatible SSE).

        Time to first token is logged separately from total duration: for a
        streamed answer TTFT is what the user actually perceives as latency.
        """
        self._require_key()

        endpoint = f"{self._base_url}/chat/completions"
        payload = self._payload(system_prompt, user_prompt)
        payload["stream"] = True
        log_fields = self._log_request(system_prompt, user_prompt, streaming=True)

        started = time.perf_counter()
        ttft_ms: float | None = None
        deltas = 0
        chars = 0
        finish_reason: str | None = None
        usage: dict[str, Any] = {}
        self.last_usage = {}
        self.last_ttft_ms = None
        self.last_finish_reason = None
        self.last_attempts = 1

        timeout = httpx.Timeout(REQUEST_TIMEOUT_SECONDS, connect=10.0)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream(
                    "POST", endpoint, json=payload, headers=self._headers()
                ) as response:
                    if response.status_code != 200:
                        body = await response.aread()
                        self._log_failure(
                            log_fields,
                            started,
                            1,
                            f"http_{response.status_code}",
                            status_code=response.status_code,
                        )
                        raise PipelineError(
                            f"OmniRoute API error {response.status_code}: "
                            f"{body.decode(errors='replace')[:300]}"
                        )

                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data = line[len("data:") :].strip()
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        if isinstance(chunk.get("usage"), dict):
                            usage = _usage_fields(chunk["usage"])
                        choices = chunk.get("choices") or []
                        if not choices:
                            continue
                        if choices[0].get("finish_reason"):
                            finish_reason = choices[0]["finish_reason"]
                        delta = choices[0].get("delta", {}).get("content")
                        if delta:
                            if ttft_ms is None:
                                ttft_ms = (time.perf_counter() - started) * 1000
                                REGISTRY.observe("llm.stream.ttft", ttft_ms)
                                logger.info(
                                    "llm.ttft first token after %.0f ms",
                                    ttft_ms,
                                    extra={
                                        "event": "llm.ttft",
                                        **log_fields,
                                        "ttft_ms": round(ttft_ms, 2),
                                    },
                                )
                            deltas += 1
                            chars += len(delta)
                            yield delta
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            self._log_failure(log_fields, started, 1, f"network: {exc}")
            raise PipelineError(f"OmniRoute stream failed: {exc}") from exc
        finally:
            total_ms = (time.perf_counter() - started) * 1000
            self.last_latency_ms = total_ms
            self.last_ttft_ms = ttft_ms
            self.last_usage = usage
            self.last_finish_reason = finish_reason
            REGISTRY.observe("llm.stream.total", total_ms)
            REGISTRY.increment("llm.stream.calls")
            completion_tokens = usage.get("completion_tokens") or (chars // 4)
            logger.info(
                "llm.stream done in %.0f ms (ttft=%s ms, %d deltas, %d chars, finish=%s)",
                total_ms,
                f"{ttft_ms:.0f}" if ttft_ms is not None else "n/a",
                deltas,
                chars,
                finish_reason,
                extra={
                    "event": "llm.stream",
                    **log_fields,
                    **usage,
                    "duration_ms": round(total_ms, 2),
                    "ttft_ms": round(ttft_ms, 2) if ttft_ms is not None else None,
                    # Time spent streaming after the first token: separates
                    # gateway queueing (TTFT) from generation throughput.
                    "stream_ms": round(total_ms - ttft_ms, 2) if ttft_ms is not None else None,
                    "deltas": deltas,
                    "answer_chars": chars,
                    "est_completion_tokens": completion_tokens,
                    "finish_reason": finish_reason,
                    "ok": deltas > 0,
                },
            )
