"""OmniRoute / OpenRouter LLM client for clinical answer generation."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from backend.app.config import Settings, get_settings
from backend.app.errors import ConfigurationError, PipelineError

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
BACKOFF_BASE_SECONDS = 1.0
REQUEST_TIMEOUT_SECONDS = 60.0
RETRY_STATUS = {408, 409, 429, 500, 502, 503, 504}


class LLMClient:
    """Async client for OmniRoute / OpenRouter OpenAI-compatible chat completions."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._api_key = self._settings.openrouter_api_key
        self._base_url = self._settings.openrouter_base_url.rstrip("/")

    async def generate_completion(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        """Call the OmniRoute chat completions API with exponential backoff."""
        if not self._api_key:
            raise ConfigurationError(
                "OMNIROUTE_API_KEY is not set. Set it in .env to enable LLM generation."
            )

        endpoint = f"{self._base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://eva-ai.local",
            "X-Title": "Eva AI",
        }

        payload: dict[str, Any] = {
            "model": self._settings.generation_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": self._settings.generation_max_tokens,
            "temperature": self._settings.generation_temperature,
        }

        logger.info(
            "Calling OmniRoute LLM: model=%s max_tokens=%d temp=%.2f endpoint=%s",
            self._settings.generation_model,
            self._settings.generation_max_tokens,
            self._settings.generation_temperature,
            endpoint,
        )

        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            last_error: Exception | None = None
            for attempt in range(1, MAX_ATTEMPTS + 1):
                try:
                    response = await client.post(endpoint, json=payload, headers=headers)
                    
                    if response.status_code == 200:
                        data = response.json()
                        choices = data.get("choices", [])
                        if not choices:
                            raise PipelineError("OmniRoute returned an empty choices list.")
                        message = choices[0].get("message", {})
                        content = message.get("content", "")
                        return content

                    if response.status_code in RETRY_STATUS and attempt < MAX_ATTEMPTS:
                        delay = BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))
                        logger.warning(
                            "OmniRoute HTTP %d on attempt %d/%d; retrying in %.1fs: %s",
                            response.status_code,
                            attempt,
                            MAX_ATTEMPTS,
                            delay,
                            response.text,
                        )
                        await asyncio.sleep(delay)
                        continue

                    response.raise_for_status()

                except (httpx.TimeoutException, httpx.NetworkError) as exc:
                    last_error = exc
                    if attempt < MAX_ATTEMPTS:
                        delay = BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))
                        logger.warning(
                            "Network/timeout error on attempt %d/%d; retrying in %.1fs: %s",
                            attempt,
                            MAX_ATTEMPTS,
                            delay,
                            exc,
                        )
                        await asyncio.sleep(delay)
                        continue
                    raise PipelineError(f"OmniRoute gateway unreachable after {MAX_ATTEMPTS} attempts: {exc}") from exc
                except httpx.HTTPStatusError as exc:
                    raise PipelineError(f"OmniRoute API error {exc.response.status_code}: {exc.response.text}") from exc
                except Exception as exc:
                    raise PipelineError(f"Generation error: {exc}") from exc

            raise PipelineError(f"Generation failed after {MAX_ATTEMPTS} attempts: {last_error}")
