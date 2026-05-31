"""LLM integration module for Groq-backed recommendations."""

from __future__ import annotations

from src.llm.client import LLMClient, get_llm_client

__all__ = ["LLMClient", "get_llm_client"]
