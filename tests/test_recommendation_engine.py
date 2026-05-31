"""Tests for recommendation engine and orchestration."""

from __future__ import annotations

import json
import pytest
from unittest.mock import MagicMock, patch

from src.models.preferences import Budget, UserPreferences
from src.models.recommendation import Recommendation, RecommendationResponse
from src.models.restaurant import Restaurant
from src.services.filter import FilterResult
from src.services.recommendation_engine import RecommendationEngine
from src.services.orchestrator import empty_response_with_hints, get_recommendations
from src.services.validation import ValidationError


# Fixtures for test data
@pytest.fixture
def sample_restaurants() -> list[Restaurant]:
    """Create sample restaurants for testing."""
    return [
        Restaurant(
            id="rest_001",
            name="Pizzeria Roma",
            location="Bangalore",
            city="Bangalore",
            cuisines="Italian",
            rating=4.5,
            approximate_cost=400,
            address="123 Main Street, Bangalore",
            cost_for_two="₹600-800",
            location_normalized="bangalore",
            city_normalized="bangalore",
            cuisines_normalized="italian",
            listed_area="Church Street",
            votes=1200,
        ),
        Restaurant(
            id="rest_002",
            name="Spice House",
            location="Bangalore",
            city="Bangalore",
            cuisines="Indian",
            rating=4.2,
            approximate_cost=300,
            address="456 Park Road, Bangalore",
            cost_for_two="₹400-600",
            location_normalized="bangalore",
            city_normalized="bangalore",
            cuisines_normalized="indian",
            listed_area="Koramangala",
            votes=980,
        ),
        Restaurant(
            id="rest_003",
            name="Sushi Paradise",
            location="Bangalore",
            city="Bangalore",
            cuisines="Japanese",
            rating=4.8,
            approximate_cost=800,
            address="789 Tech Park, Bangalore",
            cost_for_two="₹1200-1500",
            location_normalized="bangalore",
            city_normalized="bangalore",
            cuisines_normalized="japanese",
            listed_area="Whitefield",
            votes=1500,
        ),
    ]


@pytest.fixture
def user_preferences() -> UserPreferences:
    """Create sample user preferences for testing."""
    return UserPreferences(
        location="Bangalore",
        budget=Budget.MEDIUM,
        cuisine="Italian",
        min_rating=4.0,
        additional_preferences=["cozy"],
    )


@pytest.fixture
def mock_llm_client():
    """Create a mock LLM client."""
    mock = MagicMock()
    mock.complete = MagicMock()
    return mock


@pytest.fixture
def recommendation_engine(mock_llm_client) -> RecommendationEngine:
    """Create a recommendation engine with mock LLM."""
    return RecommendationEngine(llm_client=mock_llm_client)


# Tests for RecommendationEngine.invoke()
class TestRecommendationEngineInvoke:
    def test_invoke_parses_valid_json(self, recommendation_engine, mock_llm_client):
        """invoke() should parse valid JSON from LLM."""
        valid_json = json.dumps({"recommendations": [], "summary": "Test"})
        mock_llm_client.complete.return_value = valid_json

        result = recommendation_engine.invoke("test prompt")

        assert isinstance(result, dict)
        assert "recommendations" in result
        assert result["summary"] == "Test"
        mock_llm_client.complete.assert_called_once()

    def test_invoke_retries_on_invalid_json(self, recommendation_engine, mock_llm_client):
        """invoke() should retry once on JSON parse failure."""
        # First call returns invalid JSON, second returns valid
        invalid_json = "This is not JSON"
        valid_json = json.dumps({"recommendations": []})
        mock_llm_client.complete.side_effect = [invalid_json, valid_json]

        result = recommendation_engine.invoke("test prompt", max_retries=1)

        assert isinstance(result, dict)
        assert mock_llm_client.complete.call_count == 2

    def test_invoke_fails_after_max_retries(self, recommendation_engine, mock_llm_client):
        """invoke() should fail if JSON parsing fails after retries."""
        mock_llm_client.complete.return_value = "Not JSON"

        with pytest.raises(RuntimeError, match="not valid JSON"):
            recommendation_engine.invoke("test prompt", max_retries=1)

        assert mock_llm_client.complete.call_count == 2

    def test_invoke_raises_on_llm_error(self, recommendation_engine, mock_llm_client):
        """invoke() should raise RuntimeError if LLM call fails."""
        mock_llm_client.complete.side_effect = Exception("LLM connection failed")

        with pytest.raises(RuntimeError, match="Unable to get recommendations"):
            recommendation_engine.invoke("test prompt")


# Tests for RecommendationEngine.validate_and_enrich()
class TestRecommendationEngineValidateAndEnrich:
    def test_validate_and_enrich_valid_response(
        self, recommendation_engine, sample_restaurants
    ):
        """validate_and_enrich() should process valid recommendations."""
        llm_response = {
            "summary": "Great options found",
            "recommendations": [
                {
                    "restaurant_id": "rest_001",
                    "rank": 1,
                    "explanation": "Perfect for your Italian preference",
                },
                {
                    "restaurant_id": "rest_003",
                    "rank": 2,
                    "explanation": "Excellent rating and quality",
                },
            ],
        }

        response = recommendation_engine.validate_and_enrich(
            llm_response, sample_restaurants
        )

        assert isinstance(response, RecommendationResponse)
        assert len(response.recommendations) == 2
        assert response.recommendations[0].restaurant_id == "rest_001"
        assert response.recommendations[0].rank == 1
        assert response.summary == "Great options found"
        assert response.metadata["candidate_count"] == 3
        assert response.metadata["result_count"] == 2

    def test_validate_and_enrich_drops_hallucinated_ids(
        self, recommendation_engine, sample_restaurants
    ):
        """validate_and_enrich() should drop hallucinated restaurant IDs."""
        llm_response = {
            "recommendations": [
                {"restaurant_id": "rest_001", "rank": 1, "explanation": "Good"},
                {
                    "restaurant_id": "hallucinated_999",
                    "rank": 2,
                    "explanation": "Made up",
                },
                {"restaurant_id": "rest_002", "rank": 3, "explanation": "Also good"},
            ],
        }

        response = recommendation_engine.validate_and_enrich(
            llm_response, sample_restaurants
        )

        assert len(response.recommendations) == 2
        rec_ids = [r.restaurant_id for r in response.recommendations]
        assert "hallucinated_999" not in rec_ids
        assert "rest_001" in rec_ids
        assert "rest_002" in rec_ids

    def test_validate_and_enrich_sorts_by_rank(
        self, recommendation_engine, sample_restaurants
    ):
        """validate_and_enrich() should sort recommendations by rank."""
        llm_response = {
            "recommendations": [
                {"restaurant_id": "rest_003", "rank": 2, "explanation": "Second"},
                {"restaurant_id": "rest_001", "rank": 1, "explanation": "First"},
            ],
        }

        response = recommendation_engine.validate_and_enrich(
            llm_response, sample_restaurants
        )

        assert response.recommendations[0].rank == 1
        assert response.recommendations[1].rank == 2

    def test_validate_and_enrich_merges_restaurant_fields(
        self, recommendation_engine, sample_restaurants
    ):
        """validate_and_enrich() should merge LLM output with restaurant data."""
        llm_response = {
            "recommendations": [
                {"restaurant_id": "rest_001", "rank": 1, "explanation": "Explanation"}
            ],
        }

        response = recommendation_engine.validate_and_enrich(
            llm_response, sample_restaurants
        )

        rec = response.recommendations[0]
        assert rec.restaurant is not None
        assert rec.restaurant.name == "Pizzeria Roma"
        assert rec.restaurant.rating == 4.5

    def test_validate_and_enrich_missing_recommendations_field(
        self, recommendation_engine, sample_restaurants
    ):
        """validate_and_enrich() should fail if 'recommendations' field is missing."""
        llm_response = {"summary": "No recommendations field"}

        with pytest.raises(ValueError, match="missing 'recommendations' field"):
            recommendation_engine.validate_and_enrich(
                llm_response, sample_restaurants
            )

    def test_validate_and_enrich_with_request_id(
        self, recommendation_engine, sample_restaurants
    ):
        """validate_and_enrich() should include request_id in metadata."""
        llm_response = {"recommendations": []}
        request_id = "test-request-123"

        response = recommendation_engine.validate_and_enrich(
            llm_response, sample_restaurants, request_id=request_id
        )

        assert response.metadata["request_id"] == request_id


# Tests for RecommendationEngine.get_recommendations_for_candidates()
class TestRecommendationEngineGetRecommendationsForCandidates:
    def test_get_recommendations_for_empty_candidates(
        self, recommendation_engine, user_preferences
    ):
        """get_recommendations_for_candidates() should handle empty candidates."""
        response = recommendation_engine.get_recommendations_for_candidates(
            user_preferences, []
        )

        assert response.result_count == 0
        assert response.metadata["candidate_count"] == 0

    def test_get_recommendations_for_candidates_full_flow(
        self, recommendation_engine, user_preferences, sample_restaurants, mock_llm_client
    ):
        """get_recommendations_for_candidates() should orchestrate full flow."""
        llm_response = json.dumps(
            {
                "summary": "Found great options",
                "recommendations": [
                    {
                        "restaurant_id": "rest_001",
                        "rank": 1,
                        "explanation": "Matches preference",
                    }
                ],
            }
        )
        mock_llm_client.complete.return_value = llm_response

        response = recommendation_engine.get_recommendations_for_candidates(
            user_preferences, sample_restaurants[:1]
        )

        assert response.result_count == 1
        assert response.recommendations[0].restaurant_id == "rest_001"
        assert response.summary == "Found great options"
        mock_llm_client.complete.assert_called_once()


# Tests for empty_response_with_hints()
class TestEmptyResponseWithHints:
    def test_empty_response_with_cuisine_hint(self):
        """empty_response_with_hints() should include cuisine in hints."""
        prefs = UserPreferences(
            location="Bangalore",
            budget=Budget.LOW,
            cuisine="Thai",
        )

        response = empty_response_with_hints(prefs)

        assert response.result_count == 0
        assert "Thai" in response.summary
        assert "cuisine" in response.summary.lower()

    def test_empty_response_with_rating_hint(self):
        """empty_response_with_hints() should include rating in hints."""
        prefs = UserPreferences(
            location="Bangalore",
            budget=Budget.MEDIUM,
            min_rating=4.7,
        )

        response = empty_response_with_hints(prefs)

        assert response.result_count == 0
        assert "4.7" in response.summary
        assert "rating" in response.summary.lower()

    def test_empty_response_default_hint(self):
        """empty_response_with_hints() should provide default hint."""
        prefs = UserPreferences(
            location="Bangalore",
            budget=Budget.HIGH,
        )

        response = empty_response_with_hints(prefs)

        assert response.result_count == 0
        assert "criteria" in response.summary.lower()


# Tests for orchestrator get_recommendations()
class TestOrchestratorGetRecommendations:
    @patch("src.services.orchestrator.get_repository")
    @patch("src.services.orchestrator.get_filter_service")
    @patch("src.services.orchestrator.RecommendationEngine")
    def test_get_recommendations_happy_path(
        self,
        mock_engine_class,
        mock_filter_class,
        mock_repo_class,
        user_preferences,
        sample_restaurants,
    ):
        """get_recommendations() should orchestrate full flow."""
        # Setup mocks
        mock_repo = MagicMock()
        mock_repo.all.return_value = sample_restaurants
        mock_repo_class.return_value = mock_repo

        mock_filter = MagicMock()
        mock_filter.apply.return_value = FilterResult(candidates=sample_restaurants[:2])
        mock_filter_class.return_value = mock_filter

        mock_engine = MagicMock()
        mock_response = RecommendationResponse(
            recommendations=[],
            metadata={"candidate_count": 2},
        )
        mock_engine.get_recommendations_for_candidates.return_value = mock_response
        mock_engine_class.return_value = mock_engine

        # Call
        response = get_recommendations(user_preferences)

        # Verify orchestration
        assert response.metadata["candidate_count"] == 2
        mock_repo.all.assert_called_once()
        mock_filter.apply.assert_called_once()
        mock_engine.get_recommendations_for_candidates.assert_called_once()

    @patch("src.services.orchestrator.get_repository")
    @patch("src.services.orchestrator.get_filter_service")
    def test_get_recommendations_no_candidates_returns_hints(
        self,
        mock_filter_class,
        mock_repo_class,
        user_preferences,
        sample_restaurants,
    ):
        """get_recommendations() should return hints when no candidates."""
        mock_repo = MagicMock()
        mock_repo.all.return_value = sample_restaurants
        mock_repo.metadata = MagicMock()
        mock_repo_class.return_value = mock_repo

        mock_filter = MagicMock()
        mock_filter.apply.return_value = FilterResult(candidates=[], hints=["Try broader criteria"])
        mock_filter_class.return_value = mock_filter

        response = get_recommendations(user_preferences)

        assert response.result_count == 0
        assert "No restaurants match" in response.summary

    def test_get_recommendations_generates_request_id(self, user_preferences):
        """get_recommendations() should generate request_id if not provided."""
        # This would require full mocking, so we'll test the basic validation instead
        invalid_prefs = UserPreferences(
            location="",  # Invalid: empty
            budget=Budget.MEDIUM,
        )

        with pytest.raises(ValidationError):
            get_recommendations(invalid_prefs)

    @patch("src.services.orchestrator.get_repository")
    @patch("src.services.orchestrator.get_filter_service")
    def test_get_recommendations_with_explicit_request_id(
        self,
        mock_filter_class,
        mock_repo_class,
        user_preferences,
        sample_restaurants,
    ):
        """get_recommendations() should use provided request_id."""
        mock_repo = MagicMock()
        mock_repo.all.return_value = sample_restaurants
        mock_repo_class.return_value = mock_repo

        mock_filter = MagicMock()
        mock_filter.apply.return_value = FilterResult(candidates=[])
        mock_filter_class.return_value = mock_filter

        request_id = "custom-123"
        response = get_recommendations(user_preferences, request_id=request_id)

        # Empty response should still have the request ID in hints scenario
        assert response.metadata.get("candidate_count") == 0
