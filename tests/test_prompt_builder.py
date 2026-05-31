"""Tests for prompt building and LLM response parsing."""

from __future__ import annotations

import json
import pytest

from src.models.preferences import Budget, UserPreferences
from src.models.restaurant import Restaurant
from src.services.prompt_builder import (
    LLMRecommendation,
    LLMResponse,
    PromptBuilder,
)


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
            address="123 Main Street, Bangalore, Karnataka 560001",
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
            address="456 Park Road, Bangalore, Karnataka 560002",
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
            address="789 Tech Park, Bangalore, Karnataka 560003",
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
        additional_preferences=["cozy", "wifi"],
    )


@pytest.fixture
def prompt_builder() -> PromptBuilder:
    """Create a PromptBuilder instance."""
    return PromptBuilder(top_n=5)


# Tests for system message
class TestSystemMessage:
    def test_system_message_contains_key_phrases(self, prompt_builder: PromptBuilder):
        """System message should include key constraints."""
        msg = prompt_builder.build_system_message()
        assert "JSON" in msg
        assert "restaurant" in msg.lower()
        assert "valid JSON" in msg
        assert "invent" in msg.lower()

    def test_system_message_includes_response_format(self, prompt_builder: PromptBuilder):
        """System message should document the response JSON format."""
        msg = prompt_builder.build_system_message()
        assert "restaurant_id" in msg
        assert "rank" in msg
        assert "explanation" in msg
        assert "summary" in msg


# Tests for preference serialization
class TestPreferencesSerialization:
    def test_preference_block_contains_all_fields(
        self, prompt_builder: PromptBuilder, user_preferences: UserPreferences
    ):
        """Preference block should include all user preferences."""
        block = prompt_builder._serialize_preference_block(user_preferences)
        assert "Location: Bangalore" in block
        assert "Budget: medium" in block
        assert "Minimum rating: 4.0" in block
        assert "Italian" in block
        assert "cozy" in block
        assert "wifi" in block

    def test_preference_block_without_cuisine(
        self, prompt_builder: PromptBuilder
    ):
        """Preference block should handle missing cuisine gracefully."""
        prefs = UserPreferences(
            location="Mumbai",
            budget=Budget.LOW,
            min_rating=3.5,
        )
        block = prompt_builder._serialize_preference_block(prefs)
        assert "Location: Mumbai" in block
        assert "Budget: low" in block
        assert "Preferred cuisine" not in block


# Tests for address truncation
class TestAddressTruncation:
    def test_short_address_not_truncated(self, prompt_builder: PromptBuilder):
        """Short addresses should not be truncated."""
        short = "123 Main St, City"
        result = prompt_builder._truncate_address(short)
        assert result == short

    def test_long_address_truncated(self, prompt_builder: PromptBuilder):
        """Long addresses should be truncated with ellipsis."""
        long = "x" * 100
        result = prompt_builder._truncate_address(long)
        assert len(result) <= PromptBuilder.ADDRESS_TRUNCATE_LEN + 3  # +3 for "..."
        assert result.endswith("...")

    def test_truncation_respects_max_len(self, prompt_builder: PromptBuilder):
        """Truncation should respect custom max_len parameter."""
        address = "123456789" * 10
        result = prompt_builder._truncate_address(address, max_len=20)
        assert len(result) <= 23  # max_len + "..."


# Tests for candidates serialization
class TestCandidatesSerialization:
    def test_candidates_json_is_valid(
        self, prompt_builder: PromptBuilder, sample_restaurants: list[Restaurant]
    ):
        """Serialized candidates should be valid JSON."""
        json_str = prompt_builder._serialize_candidates(sample_restaurants)
        data = json.loads(json_str)
        assert isinstance(data, list)
        assert len(data) == 3

    def test_candidates_contain_required_fields(
        self, prompt_builder: PromptBuilder, sample_restaurants: list[Restaurant]
    ):
        """Each candidate should have required fields."""
        json_str = prompt_builder._serialize_candidates(sample_restaurants)
        data = json.loads(json_str)
        for candidate in data:
            assert "restaurant_id" in candidate
            assert "name" in candidate
            assert "cuisine" in candidate
            assert "rating" in candidate
            assert "cost_for_two" in candidate
            assert "location" in candidate
            assert "address" in candidate

    def test_candidates_have_correct_ids(
        self, prompt_builder: PromptBuilder, sample_restaurants: list[Restaurant]
    ):
        """Candidates should preserve restaurant IDs."""
        json_str = prompt_builder._serialize_candidates(sample_restaurants)
        data = json.loads(json_str)
        ids = [c["restaurant_id"] for c in data]
        assert "rest_001" in ids
        assert "rest_002" in ids
        assert "rest_003" in ids


# Tests for full prompt building
class TestPromptBuilding:
    def test_prompt_includes_preferences(
        self,
        prompt_builder: PromptBuilder,
        user_preferences: UserPreferences,
        sample_restaurants: list[Restaurant],
    ):
        """Prompt should include user preferences."""
        prompt = prompt_builder.build_prompt(user_preferences, sample_restaurants)
        assert "User Preferences:" in prompt
        assert "Bangalore" in prompt
        assert "Italian" in prompt

    def test_prompt_includes_candidates(
        self,
        prompt_builder: PromptBuilder,
        user_preferences: UserPreferences,
        sample_restaurants: list[Restaurant],
    ):
        """Prompt should include candidate restaurants."""
        prompt = prompt_builder.build_prompt(user_preferences, sample_restaurants)
        assert "Available Restaurants:" in prompt
        assert "rest_001" in prompt
        assert "Pizzeria Roma" in prompt
        assert "rest_002" in prompt
        assert "Spice House" in prompt

    def test_prompt_includes_top_n_instruction(
        self,
        prompt_builder: PromptBuilder,
        user_preferences: UserPreferences,
        sample_restaurants: list[Restaurant],
    ):
        """Prompt should specify the number of top recommendations."""
        prompt = prompt_builder.build_prompt(user_preferences, sample_restaurants)
        assert "top 5" in prompt

    def test_prompt_raises_on_empty_candidates(
        self, prompt_builder: PromptBuilder, user_preferences: UserPreferences
    ):
        """Prompt building should fail with empty candidates."""
        with pytest.raises(ValueError, match="No candidates"):
            prompt_builder.build_prompt(user_preferences, [])


# Tests for response parsing
class TestResponseParsing:
    def test_parse_valid_response(self, prompt_builder: PromptBuilder):
        """Valid LLM response should parse correctly."""
        llm_output = json.dumps(
            {
                "summary": "Great Italian options in Bangalore",
                "recommendations": [
                    {
                        "restaurant_id": "rest_001",
                        "rank": 1,
                        "explanation": "Perfect Italian restaurant",
                    },
                    {
                        "restaurant_id": "rest_002",
                        "rank": 2,
                        "explanation": "Indian alternative",
                    },
                ],
            }
        )
        response = LLMResponse.from_json_str(llm_output)
        assert response.summary == "Great Italian options in Bangalore"
        assert len(response.recommendations) == 2
        assert response.recommendations[0].restaurant_id == "rest_001"
        assert response.recommendations[0].rank == 1

    def test_parse_response_with_whitelist_validation(
        self, prompt_builder: PromptBuilder, sample_restaurants: list[Restaurant]
    ):
        """Invalid restaurant IDs should be dropped during parsing."""
        llm_output = json.dumps(
            {
                "recommendations": [
                    {"restaurant_id": "rest_001", "rank": 1, "explanation": "Good"},
                    {
                        "restaurant_id": "hallucinated_999",
                        "rank": 2,
                        "explanation": "Made up",
                    },
                    {"restaurant_id": "rest_003", "rank": 3, "explanation": "Great"},
                ],
            }
        )
        candidate_ids = ["rest_001", "rest_002", "rest_003"]
        response = prompt_builder.parse_response(llm_output, candidate_ids)
        assert len(response.recommendations) == 2
        rec_ids = [r.restaurant_id for r in response.recommendations]
        assert "hallucinated_999" not in rec_ids
        assert "rest_001" in rec_ids
        assert "rest_003" in rec_ids

    def test_parse_response_invalid_json(self, prompt_builder: PromptBuilder):
        """Invalid JSON should raise ValueError."""
        llm_output = "This is not JSON"
        with pytest.raises(ValueError, match="not valid JSON"):
            prompt_builder.parse_response(llm_output, ["rest_001"])

    def test_parse_response_malformed_recommendation(self, prompt_builder: PromptBuilder):
        """Malformed recommendation objects should raise ValueError."""
        llm_output = json.dumps({
            "recommendations": [
                {"restaurant_id": "rest_001"}  # Missing 'rank' and 'explanation'
            ]
        })
        with pytest.raises(ValueError, match="missing expected schema"):
            prompt_builder.parse_response(llm_output, ["rest_001"])

    def test_parse_response_empty_recommendations(self, prompt_builder: PromptBuilder):
        """Response with no recommendations should parse without error."""
        llm_output = json.dumps(
            {
                "summary": "No matches found",
                "recommendations": [],
            }
        )
        response = prompt_builder.parse_response(llm_output, ["rest_001"])
        assert len(response.recommendations) == 0
        assert response.summary == "No matches found"


# Tests for LLMRecommendation and LLMResponse models
class TestResponseModels:
    def test_llm_recommendation_from_dict(self):
        """LLMRecommendation should parse from dict."""
        data = {
            "restaurant_id": "rest_001",
            "rank": 1,
            "explanation": "Great restaurant",
        }
        rec = LLMRecommendation.from_dict(data)
        assert rec.restaurant_id == "rest_001"
        assert rec.rank == 1
        assert rec.explanation == "Great restaurant"

    def test_llm_response_from_dict(self):
        """LLMResponse should parse from dict with recommendations."""
        data = {
            "summary": "Top picks",
            "recommendations": [
                {
                    "restaurant_id": "rest_001",
                    "rank": 1,
                    "explanation": "Best Italian",
                }
            ],
        }
        response = LLMResponse.from_dict(data)
        assert response.summary == "Top picks"
        assert len(response.recommendations) == 1
        assert response.recommendations[0].restaurant_id == "rest_001"

    def test_llm_response_optional_summary(self):
        """LLMResponse should handle missing summary."""
        data = {"recommendations": []}
        response = LLMResponse.from_dict(data)
        assert response.summary is None
        assert len(response.recommendations) == 0


# Integration-style tests
class TestPromptWorkflow:
    def test_build_and_parse_workflow(
        self,
        prompt_builder: PromptBuilder,
        user_preferences: UserPreferences,
        sample_restaurants: list[Restaurant],
    ):
        """Complete workflow: build prompt, simulate LLM, parse response."""
        # Build prompt
        prompt = prompt_builder.build_prompt(user_preferences, sample_restaurants)
        assert len(prompt) > 0
        assert "rest_001" in prompt

        # Simulate LLM output
        llm_output = json.dumps(
            {
                "summary": "Found some great options",
                "recommendations": [
                    {
                        "restaurant_id": "rest_001",
                        "rank": 1,
                        "explanation": "Italian cuisine matches preference",
                    },
                    {
                        "restaurant_id": "rest_003",
                        "rank": 2,
                        "explanation": "High rating and quality",
                    },
                ],
            }
        )

        # Parse and validate
        response = prompt_builder.build_and_parse_workflow(
            user_preferences, sample_restaurants, llm_output
        )
        assert response.summary == "Found some great options"
        assert len(response.recommendations) == 2
        assert response.recommendations[0].restaurant_id == "rest_001"
