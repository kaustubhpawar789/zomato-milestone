"""Unit tests for Phase 2 domain models."""

from __future__ import annotations

import pytest

from src.models.preferences import Budget, UserPreferences
from src.models.recommendation import Recommendation, RecommendationResponse
from src.models.restaurant import Restaurant


def test_budget_from_str():
    assert Budget.from_str("low") == Budget.LOW
    assert Budget.from_str("MEDIUM") == Budget.MEDIUM
    with pytest.raises(ValueError):
        Budget.from_str("cheap")


def test_user_preferences_normalized():
    prefs = UserPreferences(
        location="  Bangalore ",
        budget=Budget.MEDIUM,
        cuisine=" Italian ",
        additional_preferences=[" Family-Friendly ", ""],
    )
    assert prefs.location_normalized == "bangalore"
    assert prefs.cuisine_normalized == "italian"
    assert prefs.additional_preferences_normalized == ["family-friendly"]
    assert prefs.min_rating == 3.5


def test_recommendation_response():
    restaurant = Restaurant(
        id="abc",
        name="Test",
        location="Koramangala",
        city="Bangalore",
        cuisines="Italian",
        rating=4.0,
        approximate_cost=500,
        address="Addr",
        cost_for_two="500",
        location_normalized="koramangala",
        city_normalized="bangalore",
        cuisines_normalized="italian",
        listed_area="BTM",
    )
    rec = Recommendation(
        restaurant_id="abc",
        rank=1,
        explanation="Great fit.",
        restaurant=restaurant,
    )
    response = RecommendationResponse(
        recommendations=[rec],
        summary="Top pick.",
        metadata={"candidate_count": 10},
    )
    assert response.result_count == 1
    assert response.to_dict()["summary"] == "Top pick."
    assert response.to_dict()["recommendations"][0]["restaurant"]["name"] == "Test"
