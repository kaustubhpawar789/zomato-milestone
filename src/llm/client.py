"""LLM client abstraction and Groq implementation."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Optional

from groq import Groq

from src import config

logger = logging.getLogger(__name__)


class LLMClient(ABC):
    """Abstract interface for LLM providers."""

    @abstractmethod
    def complete(self, prompt: str, system: str = "") -> str:
        """
        Generate a completion for the given prompt.

        Args:
            prompt: The user message / content to complete.
            system: Optional system message defining role/constraints.

        Returns:
            The LLM's text response.

        Raises:
            RuntimeError: On API failure, timeout, or invalid response.
        """


class GroqLLMClient(LLMClient):
    """Groq-backed LLM client using the Groq API."""

    def __init__(
        self,
        api_key: str,
        model: str = "llama-3.3-70b-versatile",
        timeout: Optional[float] = 30.0,
    ):
        """
        Initialize Groq client.

        Args:
            api_key: Groq API key. If empty, will try to use GROQ_API_KEY env var.
            model: Model name to use (default: llama-3.3-70b-versatile).
            timeout: Timeout in seconds for API calls (default: 30).

        Raises:
            ValueError: If API key is not provided or available.
        """
        if not api_key:
            raise ValueError(
                "LLM_API_KEY is required for Groq client. "
                "Set it in .env or environment variables."
            )
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.client = Groq(api_key=api_key)

    def complete(self, prompt: str, system: str = "") -> str:
        """
        Call Groq API to generate a completion.

        Args:
            prompt: The user message to complete.
            system: Optional system message.

        Returns:
            The completion text.

        Raises:
            RuntimeError: If API call fails or times out.
        """
        try:
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})

            logger.debug(f"Calling Groq API with model {self.model}")
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,  # type: ignore
                timeout=self.timeout,
            )

            completion = response.choices[0].message.content
            if not completion:
                raise RuntimeError("Groq API returned empty completion")

            logger.debug(f"Groq API returned completion (len={len(completion)})")
            return completion

        except Exception as exc:
            logger.exception(f"Groq API call failed: {exc}")
            raise RuntimeError(f"LLM call failed: {exc}") from exc


def get_llm_client(
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> LLMClient:
    """
    Factory function to get an LLM client based on provider.

    Args:
        provider: LLM provider name (default: from config.LLM_PROVIDER, usually 'groq').
        api_key: API key (default: from config.LLM_API_KEY).
        model: Model name (default: from config.LLM_MODEL).

    Returns:
        Configured LLMClient instance.

    Raises:
        ValueError: If provider is unknown or credentials are missing.
    """
    provider = provider or config.LLM_PROVIDER
    api_key = api_key or config.LLM_API_KEY
    model = model or config.LLM_MODEL

    provider_lower = provider.strip().lower()

    if provider_lower == "groq":
        return GroqLLMClient(api_key=api_key, model=model)

    raise ValueError(
        f"Unknown LLM provider '{provider}'. Supported: 'groq' "
        "(extensible for future providers like openai)."
    )
