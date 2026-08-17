"""LLM client for generation."""
from __future__ import annotations

import logging
from typing import Any

from anthropic import AsyncAnthropic

from backend.app.config import Settings, get_settings

logger = logging.getLogger(__name__)


class LLMClient:
    """Wrapper around the Anthropic API for answer generation."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        
        # In a real app we might validate that ANTHROPIC_API_KEY is set.
        # But for testability (so the app can boot without it if not doing generation),
        # we defer initialization or allow empty keys if mock generation is used.
        api_key = self._settings.anthropic_api_key or "DUMMY_KEY_FOR_TESTS"
        self._client = AsyncAnthropic(api_key=api_key)

    async def generate_completion(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        """Call the LLM with the provided prompts."""
        logger.info(
            "Calling LLM: model=%s max_tokens=%d temp=%s",
            self._settings.generation_model,
            self._settings.generation_max_tokens,
            self._settings.generation_temperature,
        )

        try:
            response = await self._client.messages.create(
                model=self._settings.generation_model,
                max_tokens=self._settings.generation_max_tokens,
                temperature=self._settings.generation_temperature,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": user_prompt},
                ],
            )
            # The anthropic sdk returns content as a list of TextBlock objects
            text_response = "".join([block.text for block in response.content if hasattr(block, "text")])
            return text_response
        except Exception as exc:
            logger.error("LLM generation failed: %s", exc)
            raise
