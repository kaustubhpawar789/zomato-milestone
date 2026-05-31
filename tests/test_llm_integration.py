"""Integration test for Groq LLM client - tests actual API call."""

from __future__ import annotations

import pytest

from src.llm import get_llm_client


@pytest.mark.integration
def test_groq_llm_client_can_complete():
    """Test that GroqLLMClient can make a real API call to Groq."""
    # Get the client (reads from config)
    client = get_llm_client()

    # Simple test prompt
    system_msg = "You are a helpful assistant. Respond with a single sentence only."
    user_prompt = "What is 2 + 2?"

    # Make the API call
    response = client.complete(user_prompt, system=system_msg)

    # Verify we got a response
    assert response is not None
    assert len(response) > 0
    assert isinstance(response, str)
    print(f"\n✓ Groq LLM responded: {response[:100]}...")


@pytest.mark.integration
def test_groq_llm_client_json_response():
    """Test that GroqLLMClient can generate JSON responses."""
    client = get_llm_client()

    system_msg = (
        "You are a JSON generator. Always respond with valid JSON only, no other text."
    )
    user_prompt = (
        'Generate a JSON object with fields "name" (string), "age" (number). '
        'Use example values like John and 25.'
    )

    response = client.complete(user_prompt, system=system_msg)

    # Verify we got a response
    assert response is not None
    assert len(response) > 0
    print(f"\n✓ Groq LLM JSON response:\n{response}")

    # Try to parse as JSON to verify it's valid
    import json

    try:
        parsed = json.loads(response)
        assert "name" in parsed or "age" in parsed
        print(f"✓ Valid JSON parsed: {parsed}")
    except json.JSONDecodeError:
        pytest.fail(f"Response is not valid JSON: {response}")
