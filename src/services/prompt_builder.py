"""Prompt builder for LLM-based restaurant ranking and explanation."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.models.preferences import UserPreferences
from src.models.recommendation import Recommendation
from src.models.restaurant import Restaurant

logger = logging.getLogger(__name__)

# Response schema models for LLM output
@dataclass
class LLMRecommendation:
    """A single recommendation from the LLM response."""

    restaurant_id: str
    rank: int
    explanation: str

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> LLMRecommendation:
        """Parse from JSON dict."""
        return cls(
            restaurant_id=str(data["restaurant_id"]),
            rank=int(data["rank"]),
            explanation=str(data["explanation"]),
        )


@dataclass
class LLMResponse:
    """Parsed LLM response with recommendations and optional summary."""

    recommendations: List[LLMRecommendation] = field(default_factory=list)
    summary: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> LLMResponse:
        """Parse from JSON dict."""
        recommendations = [
            LLMRecommendation.from_dict(rec)
            for rec in data.get("recommendations", [])
        ]
        summary = data.get("summary")
        return cls(recommendations=recommendations, summary=summary)

    @classmethod
    def from_json_str(cls, json_str: str) -> LLMResponse:
        """Parse from JSON string."""
        data = json.loads(json_str)
        return cls.from_dict(data)


class PromptBuilder:
    """Builder for LLM prompts with guardrails for restaurants and JSON output."""

    # Default truncation length for address field (token efficiency)
    ADDRESS_TRUNCATE_LEN = 60

    def __init__(self, top_n: int = 5):
        """
        Initialize prompt builder.

        Args:
            top_n: Number of top recommendations to request from LLM (default: 5).
        """
        self.top_n = top_n

    def build_system_message(self) -> str:
        """
        Build the system message defining role and constraints.

        Returns:
            System message string.
        """
        return (
            "You are a restaurant recommendation expert. "
            "Your task is to rank the provided restaurant candidates and explain why each one fits the user's preferences. "
            "You must return ONLY valid JSON with no additional text or markdown. "
            "Never invent or reference restaurants outside the provided candidate list. "
            "Return JSON in this format:\n"
            "{\n"
            '  "summary": "Optional overview of the recommendations",\n'
            '  "recommendations": [\n'
            "    {\n"
            '      "restaurant_id": "<id>",\n'
            '      "rank": 1,\n'
            '      "explanation": "Why this fits the user\'s preferences"\n'
            "    }\n"
            "  ]\n"
            "}"
        )

    def _serialize_preference_block(self, prefs: UserPreferences) -> str:
        """
        Serialize user preferences into a readable block.

        Args:
            prefs: UserPreferences object.

        Returns:
            Human-readable preferences string.
        """
        parts = [
            f"Location: {prefs.location}",
            f"Budget: {prefs.budget.value}",
            f"Minimum rating: {prefs.min_rating}",
        ]
        if prefs.cuisine:
            parts.append(f"Preferred cuisine: {prefs.cuisine}")
        if prefs.additional_preferences:
            parts.append(
                f"Additional preferences: {', '.join(prefs.additional_preferences)}"
            )
        return "\n".join(parts)

    def _truncate_address(self, address: str, max_len: int = ADDRESS_TRUNCATE_LEN) -> str:
        """
        Truncate long address strings for token efficiency.

        Args:
            address: Full address string.
            max_len: Maximum length before truncation.

        Returns:
            Truncated address (with "..." if necessary).
        """
        if len(address) <= max_len:
            return address
        return address[:max_len].rstrip() + "..."

    def _serialize_candidates(self, candidates: List[Restaurant]) -> str:
        """
        Serialize restaurant candidates into compact JSON.

        Args:
            candidates: List of filtered Restaurant objects.

        Returns:
            JSON string representing candidates.
        """
        candidate_list = []
        for restaurant in candidates:
            candidate_list.append(
                {
                    "restaurant_id": restaurant.id,
                    "name": restaurant.name,
                    "cuisine": restaurant.cuisines,
                    "rating": float(restaurant.rating),
                    "cost_for_two": restaurant.cost_for_two,
                    "location": restaurant.location,
                    "address": self._truncate_address(restaurant.address),
                }
            )
        return json.dumps(candidate_list, indent=2)

    def build_prompt(
        self, preferences: UserPreferences, candidates: List[Restaurant]
    ) -> str:
        """
        Build the full user prompt with preferences and candidates.

        Args:
            preferences: User preferences.
            candidates: Filtered candidate restaurants (should be <= MAX_CANDIDATES_FOR_LLM).

        Returns:
            Complete prompt string.

        Raises:
            ValueError: If candidates list is empty.
        """
        if not candidates:
            raise ValueError("No candidates provided to build prompt")

        pref_block = self._serialize_preference_block(preferences)
        candidates_json = self._serialize_candidates(candidates)

        prompt = (
            "User Preferences:\n"
            f"{pref_block}\n\n"
            "Available Restaurants:\n"
            f"{candidates_json}\n\n"
            f"Please rank the top {self.top_n} restaurants that best match the user's preferences. "
            "Provide a concise explanation for each recommendation. "
            "Return only valid JSON as specified."
        )
        return prompt

    def parse_response(
        self, llm_output: str, candidate_ids: List[str]
    ) -> LLMResponse:
        """
        Parse and validate LLM response.

        Args:
            llm_output: Raw LLM text output.
            candidate_ids: List of valid restaurant IDs from the candidate set.

        Returns:
            Parsed LLMResponse with validated recommendations.

        Raises:
            ValueError: If JSON parsing fails or IDs are not in candidate set.
        """
        try:
            # Try to parse as JSON
            response = LLMResponse.from_json_str(llm_output)

            # Whitelist validate: only keep recommendations with valid IDs
            candidate_id_set = set(candidate_ids)
            validated_recs = []
            for rec in response.recommendations:
                if rec.restaurant_id in candidate_id_set:
                    validated_recs.append(rec)
                else:
                    logger.warning(
                        f"Dropped hallucinated restaurant ID: {rec.restaurant_id}"
                    )

            response.recommendations = validated_recs
            return response

        except json.JSONDecodeError as exc:
            raise ValueError(f"LLM response is not valid JSON: {exc}") from exc
        except (KeyError, TypeError) as exc:
            raise ValueError(f"LLM response missing expected schema: {exc}") from exc

    def build_and_parse_workflow(
        self,
        preferences: UserPreferences,
        candidates: List[Restaurant],
        llm_output: str,
    ) -> LLMResponse:
        """
        Convenience method: build prompt, call LLM, and parse response.

        This is typically called by the recommendation engine.

        Args:
            preferences: User preferences.
            candidates: Filtered candidate restaurants.
            llm_output: Raw LLM output string.

        Returns:
            Parsed LLMResponse.

        Raises:
            ValueError: On any parsing or validation failure.
        """
        # Build prompt (for logging/debugging)
        _prompt = self.build_prompt(preferences, candidates)

        # Extract candidate IDs for whitelist validation
        candidate_ids = [c.id for c in candidates]

        # Parse and validate response
        response = self.parse_response(llm_output, candidate_ids)
        return response
