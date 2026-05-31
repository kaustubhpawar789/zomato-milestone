"""Phase 5 validation tests — mock LLM JSON, hallucinated IDs, partial responses.

These tests verify the guardrails in ``RecommendationEngine`` and the
orchestrator without making any live LLM calls.
"""

from __future__ import annotations

import json
import pytest
from unittest.mock import MagicMock, patch

from src.models.preferences import Budget, UserPreferences
from src.models.recommendation import Recommendation, RecommendationResponse
from src.models.restaurant import Restaurant
from src.services.filter import FilterResult
from src.services.recommendation_engine import RecommendationEngine, _extract_json_text
from src.services.orchestrator import empty_response_with_hints, get_recommendations
from src.services.validation import ValidationError


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_restaurants() -> list[Restaurant]:
    """Three valid restaurants for testing."""
    return [
        Restaurant(
            id="rest_001",
            name="Pizzeria Roma",
            location="Koramangala",
            city="Bangalore",
            cuisines="Italian",
            rating=4.5,
            approximate_cost=400,
            address="123 Main Street, Bangalore",
            cost_for_two="₹600-800",
            location_normalized="koramangala",
            city_normalized="bangalore",
            cuisines_normalized="italian",
            listed_area="Church Street",
            votes=1200,
        ),
        Restaurant(
            id="rest_002",
            name="Spice House",
            location="Indiranagar",
            city="Bangalore",
            cuisines="Indian",
            rating=4.2,
            approximate_cost=300,
            address="456 Park Road, Bangalore",
            cost_for_two="₹400-600",
            location_normalized="indiranagar",
            city_normalized="bangalore",
            cuisines_normalized="indian",
            listed_area="Koramangala",
            votes=980,
        ),
        Restaurant(
            id="rest_003",
            name="Sushi Paradise",
            location="Whitefield",
            city="Bangalore",
            cuisines="Japanese",
            rating=4.8,
            approximate_cost=800,
            address="789 Tech Park, Bangalore",
            cost_for_two="₹1200-1500",
            location_normalized="whitefield",
            city_normalized="bangalore",
            cuisines_normalized="japanese",
            listed_area="Whitefield",
            votes=1500,
        ),
    ]


@pytest.fixture
def user_prefs() -> UserPreferences:
    return UserPreferences(
        location="Bangalore",
        budget=Budget.MEDIUM,
        cuisine="Italian",
        min_rating=4.0,
    )


@pytest.fixture
def mock_llm():
    mock = MagicMock()
    return mock


@pytest.fixture
def engine(mock_llm) -> RecommendationEngine:
    return RecommendationEngine(llm_client=mock_llm, timeout=5.0)


# ---------------------------------------------------------------------------
# 1. Hallucinated IDs are dropped
# ---------------------------------------------------------------------------

class TestHallucinatedIDGuardrail:
    """No recommendation should ever surface an ID that wasn't in the candidate set."""

    def test_all_hallucinated_ids_dropped(self, engine, sample_restaurants):
        """Every ID returned by the LLM is fabricated → empty results."""
        llm_response = {
            "recommendations": [
                {"restaurant_id": "fake_999", "rank": 1, "explanation": "Invented"},
                {"restaurant_id": "fake_888", "rank": 2, "explanation": "Also fake"},
            ],
            "summary": "Top picks",
        }

        response = engine.validate_and_enrich(llm_response, sample_restaurants)

        assert response.result_count == 0
        assert response.metadata.get("dropped_hallucinated_ids") == [
            "fake_999",
            "fake_888",
        ]

    def test_mixed_real_and_hallucinated(self, engine, sample_restaurants):
        """Mix of valid and fabricated IDs → only valid IDs survive."""
        llm_response = {
            "recommendations": [
                {"restaurant_id": "rest_001", "rank": 1, "explanation": "Great"},
                {"restaurant_id": "hallucinated_777", "rank": 2, "explanation": "Fake"},
                {"restaurant_id": "rest_003", "rank": 3, "explanation": "Nice"},
            ],
        }

        response = engine.validate_and_enrich(llm_response, sample_restaurants)

        returned_ids = [r.restaurant_id for r in response.recommendations]
        assert "rest_001" in returned_ids
        assert "rest_003" in returned_ids
        assert "hallucinated_777" not in returned_ids
        assert response.result_count == 2

    def test_hallucinated_id_logged_in_metadata(self, engine, sample_restaurants):
        """Dropped IDs are recorded in metadata for observability."""
        llm_response = {
            "recommendations": [
                {"restaurant_id": "rest_001", "rank": 1, "explanation": "ok"},
                {"restaurant_id": "DOES_NOT_EXIST", "rank": 2, "explanation": "nope"},
            ],
        }

        response = engine.validate_and_enrich(llm_response, sample_restaurants)
        assert "DOES_NOT_EXIST" in response.metadata["dropped_hallucinated_ids"]


# ---------------------------------------------------------------------------
# 2. Partial / malformed LLM responses
# ---------------------------------------------------------------------------

class TestPartialResponses:
    """Handle LLM output that is syntactically valid JSON but structurally odd."""

    def test_missing_recommendations_key(self, engine, sample_restaurants):
        """JSON without 'recommendations' key raises ValueError."""
        llm_response = {"summary": "I recommend all of them"}

        with pytest.raises(ValueError, match="missing 'recommendations' field"):
            engine.validate_and_enrich(llm_response, sample_restaurants)

    def test_recommendations_is_not_a_list(self, engine, sample_restaurants):
        """'recommendations' that's a dict instead of list."""
        llm_response = {"recommendations": {"restaurant_id": "rest_001"}}

        with pytest.raises(ValueError, match="must be a list"):
            engine.validate_and_enrich(llm_response, sample_restaurants)

    def test_recommendation_missing_rank(self, engine, sample_restaurants):
        """Entries without 'rank' should be silently skipped."""
        llm_response = {
            "recommendations": [
                {"restaurant_id": "rest_001", "explanation": "no rank field"},
                {"restaurant_id": "rest_002", "rank": 1, "explanation": "ok"},
            ],
        }

        response = engine.validate_and_enrich(llm_response, sample_restaurants)
        assert response.result_count == 1
        assert response.recommendations[0].restaurant_id == "rest_002"

    def test_empty_recommendations_list(self, engine, sample_restaurants):
        """LLM returns empty recommendations list → valid but empty response."""
        llm_response = {"recommendations": [], "summary": "Nothing fits"}

        response = engine.validate_and_enrich(llm_response, sample_restaurants)

        assert response.result_count == 0
        assert response.summary == "Nothing fits"

    def test_recommendation_missing_explanation_gets_default(
        self, engine, sample_restaurants
    ):
        """Missing explanation defaults to empty string."""
        llm_response = {
            "recommendations": [
                {"restaurant_id": "rest_001", "rank": 1},
            ],
        }

        response = engine.validate_and_enrich(llm_response, sample_restaurants)
        assert response.recommendations[0].explanation == ""

    def test_summary_field_optional(self, engine, sample_restaurants):
        """Response without 'summary' should still succeed."""
        llm_response = {
            "recommendations": [
                {"restaurant_id": "rest_001", "rank": 1, "explanation": "ok"},
            ],
        }

        response = engine.validate_and_enrich(llm_response, sample_restaurants)
        assert response.summary is None


# ---------------------------------------------------------------------------
# 3. Mock LLM JSON → full flow
# ---------------------------------------------------------------------------

class TestMockLLMFullFlow:
    """Exercise ``get_recommendations_for_candidates`` with mocked LLM output."""

    def test_full_flow_valid_json(
        self, engine, mock_llm, user_prefs, sample_restaurants
    ):
        """Happy path: LLM returns well-formed JSON."""
        mock_llm.complete.return_value = json.dumps(
            {
                "summary": "Here are the best picks",
                "recommendations": [
                    {
                        "restaurant_id": "rest_001",
                        "rank": 1,
                        "explanation": "Italian cuisine as requested",
                    },
                    {
                        "restaurant_id": "rest_003",
                        "rank": 2,
                        "explanation": "Highly rated",
                    },
                ],
            }
        )

        response = engine.get_recommendations_for_candidates(
            user_prefs, sample_restaurants, request_id="test-001"
        )

        assert response.result_count == 2
        assert response.recommendations[0].restaurant_id == "rest_001"
        assert response.recommendations[0].restaurant.name == "Pizzeria Roma"
        assert response.summary == "Here are the best picks"
        assert response.metadata["request_id"] == "test-001"
        # Latency should be tracked
        assert "llm_latency_ms" in response.metadata

    def test_full_flow_json_in_markdown_fence(
        self, engine, mock_llm, user_prefs, sample_restaurants
    ):
        """LLM wraps JSON in ```json ... ``` → still parsed correctly."""
        inner_json = json.dumps(
            {
                "recommendations": [
                    {
                        "restaurant_id": "rest_002",
                        "rank": 1,
                        "explanation": "Good spice level",
                    },
                ],
            }
        )
        mock_llm.complete.return_value = f"```json\n{inner_json}\n```"

        response = engine.get_recommendations_for_candidates(
            user_prefs, sample_restaurants[:2]
        )

        assert response.result_count == 1
        assert response.recommendations[0].restaurant_id == "rest_002"

    def test_full_flow_retry_on_malformed_json(
        self, engine, mock_llm, user_prefs, sample_restaurants
    ):
        """First call returns garbage, retry returns valid JSON."""
        valid = json.dumps(
            {
                "recommendations": [
                    {"restaurant_id": "rest_001", "rank": 1, "explanation": "ok"},
                ],
            }
        )
        mock_llm.complete.side_effect = ["this is not json at all", valid]

        response = engine.get_recommendations_for_candidates(
            user_prefs, sample_restaurants[:1]
        )

        assert response.result_count == 1
        assert mock_llm.complete.call_count == 2

    def test_full_flow_empty_candidates(self, engine, user_prefs):
        """Empty candidate list → empty response without calling LLM."""
        response = engine.get_recommendations_for_candidates(user_prefs, [])

        assert response.result_count == 0
        assert response.metadata["candidate_count"] == 0

    def test_full_flow_llm_exception_raises_runtime_error(
        self, engine, mock_llm, user_prefs, sample_restaurants
    ):
        """LLM raises an exception → RuntimeError with user-friendly message."""
        mock_llm.complete.side_effect = Exception("API key expired")

        with pytest.raises(RuntimeError):
            engine.get_recommendations_for_candidates(
                user_prefs, sample_restaurants
            )


# ---------------------------------------------------------------------------
# 4. Rank re-sorting
# ---------------------------------------------------------------------------

class TestRankSorting:
    """Recommendations should be returned in rank order regardless of LLM order."""

    def test_out_of_order_ranks_sorted(self, engine, sample_restaurants):
        llm_response = {
            "recommendations": [
                {"restaurant_id": "rest_003", "rank": 3, "explanation": "Third"},
                {"restaurant_id": "rest_001", "rank": 1, "explanation": "First"},
                {"restaurant_id": "rest_002", "rank": 2, "explanation": "Second"},
            ],
        }

        response = engine.validate_and_enrich(llm_response, sample_restaurants)
        ranks = [r.rank for r in response.recommendations]
        assert ranks == [1, 2, 3]

    def test_duplicate_ranks_preserved(self, engine, sample_restaurants):
        """If the LLM assigns duplicate ranks, all are kept (sort is stable)."""
        llm_response = {
            "recommendations": [
                {"restaurant_id": "rest_001", "rank": 1, "explanation": "A"},
                {"restaurant_id": "rest_002", "rank": 1, "explanation": "B"},
            ],
        }

        response = engine.validate_and_enrich(llm_response, sample_restaurants)
        assert response.result_count == 2


# ---------------------------------------------------------------------------
# 5. Merged restaurant fields
# ---------------------------------------------------------------------------

class TestMergedFields:
    """Each recommendation carries the full Restaurant object from the candidate set."""

    def test_restaurant_fields_merged(self, engine, sample_restaurants):
        llm_response = {
            "recommendations": [
                {"restaurant_id": "rest_001", "rank": 1, "explanation": "Nice"},
            ],
        }

        response = engine.validate_and_enrich(llm_response, sample_restaurants)
        rec = response.recommendations[0]

        assert rec.restaurant is not None
        assert rec.restaurant.name == "Pizzeria Roma"
        assert rec.restaurant.rating == 4.5
        assert rec.restaurant.cuisines == "Italian"
        assert rec.restaurant.city == "Bangalore"

    def test_each_result_has_rank_explanation_and_restaurant(
        self, engine, sample_restaurants
    ):
        """Exit criterion: each result has rank + explanation + merged fields."""
        llm_response = {
            "recommendations": [
                {
                    "restaurant_id": "rest_001",
                    "rank": 1,
                    "explanation": "Perfect choice",
                },
                {
                    "restaurant_id": "rest_002",
                    "rank": 2,
                    "explanation": "Good alternative",
                },
            ],
        }

        response = engine.validate_and_enrich(llm_response, sample_restaurants)

        for rec in response.recommendations:
            assert rec.rank is not None
            assert isinstance(rec.explanation, str)
            assert rec.restaurant is not None
            assert rec.restaurant.name  # non-empty


# ---------------------------------------------------------------------------
# 6. JSON fence extraction utility
# ---------------------------------------------------------------------------

class TestExtractJsonText:
    """Unit tests for the _extract_json_text helper."""

    def test_plain_json_unchanged(self):
        raw = '{"key": "value"}'
        assert _extract_json_text(raw) == raw

    def test_json_in_code_fence(self):
        raw = '```json\n{"key": "value"}\n```'
        assert _extract_json_text(raw) == '{"key": "value"}'

    def test_json_in_plain_fence(self):
        raw = '```\n{"key": "value"}\n```'
        assert _extract_json_text(raw) == '{"key": "value"}'

    def test_surrounding_text_stripped(self):
        raw = 'Here is the result:\n```json\n{"a": 1}\n```\nHope this helps!'
        assert _extract_json_text(raw) == '{"a": 1}'


# ---------------------------------------------------------------------------
# 7. LLM latency tracking
# ---------------------------------------------------------------------------

class TestLatencyTracking:
    """Latency metadata is attached to the response."""

    def test_latency_in_metadata(self, engine, sample_restaurants):
        """When llm_latency_ms is provided it appears in metadata."""
        llm_response = {
            "recommendations": [
                {"restaurant_id": "rest_001", "rank": 1, "explanation": "ok"},
            ],
        }

        response = engine.validate_and_enrich(
            llm_response, sample_restaurants, llm_latency_ms=123.456
        )

        assert response.metadata["llm_latency_ms"] == 123.5

    def test_latency_absent_when_not_provided(self, engine, sample_restaurants):
        llm_response = {"recommendations": []}
        response = engine.validate_and_enrich(llm_response, sample_restaurants)
        assert "llm_latency_ms" not in response.metadata


# ---------------------------------------------------------------------------
# 8. Orchestrator-level validation failures
# ---------------------------------------------------------------------------

class TestOrchestratorValidation:
    """Preference validation fires before any expensive work."""

    def test_empty_location_raises_validation_error(self):
        prefs = UserPreferences(location="", budget=Budget.MEDIUM)
        with pytest.raises(ValidationError, match="location"):
            get_recommendations(prefs)

    def test_invalid_rating_raises_validation_error(self):
        prefs = UserPreferences(
            location="Bangalore", budget=Budget.LOW, min_rating=6.0
        )
        with pytest.raises(ValidationError, match="rating"):
            get_recommendations(prefs)

    def test_overly_long_cuisine_raises_validation_error(self):
        prefs = UserPreferences(
            location="Bangalore",
            budget=Budget.HIGH,
            cuisine="x" * 201,
        )
        with pytest.raises(ValidationError, match="cuisine"):
            get_recommendations(prefs)


# ---------------------------------------------------------------------------
# 9. Orchestrator empty-response hints
# ---------------------------------------------------------------------------

class TestOrchestratorEmptyHints:
    """empty_response_with_hints covers all edge cases."""

    def test_cuisine_hint(self):
        prefs = UserPreferences(
            location="Bangalore", budget=Budget.LOW, cuisine="Thai"
        )
        resp = empty_response_with_hints(prefs)
        assert resp.result_count == 0
        assert "Thai" in resp.summary

    def test_rating_hint(self):
        prefs = UserPreferences(
            location="Bangalore", budget=Budget.HIGH, min_rating=4.9
        )
        resp = empty_response_with_hints(prefs)
        assert "4.9" in resp.summary

    def test_default_hint_when_no_specific_filters(self):
        prefs = UserPreferences(location="Bangalore", budget=Budget.MEDIUM)
        resp = empty_response_with_hints(prefs)
        assert "criteria" in resp.summary.lower()

    def test_both_cuisine_and_rating_hints(self):
        prefs = UserPreferences(
            location="Bangalore",
            budget=Budget.LOW,
            cuisine="Greek",
            min_rating=4.8,
        )
        resp = empty_response_with_hints(prefs)
        assert resp.metadata["candidate_count"] == 0
        hints = resp.metadata.get("hints", [])
        assert len(hints) >= 2


# ---------------------------------------------------------------------------
# 10. LLM failure → clear error, no crash
# ---------------------------------------------------------------------------

class TestLLMFailurePath:
    """Exit criterion: LLM failure returns clear error (no crash)."""

    def test_llm_connection_error(self, engine, mock_llm, user_prefs, sample_restaurants):
        mock_llm.complete.side_effect = ConnectionError("Network unreachable")
        with pytest.raises(RuntimeError, match="try again"):
            engine.get_recommendations_for_candidates(user_prefs, sample_restaurants)

    def test_llm_returns_invalid_json_twice(
        self, engine, mock_llm, user_prefs, sample_restaurants
    ):
        """Two malformed responses → RuntimeError with JSON detail."""
        mock_llm.complete.return_value = "NOT JSON AT ALL"
        with pytest.raises(RuntimeError, match="not valid JSON"):
            engine.get_recommendations_for_candidates(user_prefs, sample_restaurants)
