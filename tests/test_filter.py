"""Unit tests for preference validation and candidate filtering."""

from __future__ import annotations

import time

import pytest

from src.models.preferences import Budget, UserPreferences
from src.models.restaurant import BudgetThresholds, IngestionMetadata, Restaurant
from src.services.filter import CandidateFilterService, apply_filter
from src.services.validation import ValidationError, validate_preferences

# --- Fixtures ---

THRESHOLDS = BudgetThresholds(p33=300.0, p66=600.0, sample_size=100)

METADATA = IngestionMetadata(
    schema_version="1.0.0",
    source="test",
    row_count=6,
    raw_row_count=6,
    dropped_incomplete=0,
    last_sync_at="2026-01-01T00:00:00+00:00",
    cache_path="/tmp/test.parquet",
    budget_thresholds_global=THRESHOLDS,
    budget_thresholds_per_city={"bangalore": THRESHOLDS},
)


def _restaurant(
    id: str,
    name: str,
    city: str = "Bangalore",
    location: str = "Koramangala",
    cuisines: str = "Italian, Pizza",
    rating: float = 4.2,
    cost: int = 500,
    rest_type: str = "Casual Dining",
) -> Restaurant:
    city_norm = city.casefold()
    loc_norm = location.casefold()
    cuisines_norm = cuisines.casefold()
    return Restaurant(
        id=id,
        name=name,
        location=location,
        city=city,
        cuisines=cuisines,
        rating=rating,
        approximate_cost=cost,
        address=f"123 Main, {location}, {city}",
        cost_for_two=str(cost),
        location_normalized=loc_norm,
        city_normalized=city_norm,
        cuisines_normalized=cuisines_norm,
        listed_area=location,
        rest_type=rest_type,
        votes=100,
    )


@pytest.fixture
def sample_restaurants() -> list[Restaurant]:
    return [
        _restaurant("1", "Italian Place", cuisines="Italian, Pizza", rating=4.5, cost=400),
        _restaurant("2", "Chinese Wok", cuisines="Chinese, Thai", rating=4.0, cost=500),
        _restaurant("3", "Budget Bites", cuisines="Fast Food", rating=3.8, cost=250),
        _restaurant("4", "Fine Dine", cuisines="French", rating=4.8, cost=900),
        _restaurant("5", "Family Kitchen", cuisines="North Indian", rating=4.1, cost=550, rest_type="Family Dining"),
        _restaurant("6", "Other City", city="Mumbai", location="Andheri", cuisines="Italian", rating=4.3, cost=450),
    ]


@pytest.fixture
def filter_service() -> CandidateFilterService:
    return CandidateFilterService(METADATA, max_candidates=50)


# --- Validation ---


def test_validate_rejects_empty_location():
    prefs = UserPreferences(location="   ", budget=Budget.MEDIUM)
    with pytest.raises(ValidationError) as exc:
        validate_preferences(prefs)
    assert "location" in exc.value.errors


def test_validate_rejects_invalid_rating():
    prefs = UserPreferences(location="Bangalore", budget=Budget.LOW, min_rating=6.0)
    with pytest.raises(ValidationError) as exc:
        validate_preferences(prefs)
    assert "min_rating" in exc.value.errors


def test_validate_accepts_valid_prefs():
    prefs = UserPreferences(location="Bangalore", budget=Budget.HIGH, min_rating=4.0)
    validate_preferences(prefs)


# --- Location ---


def test_filter_by_location_city(filter_service: CandidateFilterService, sample_restaurants: list[Restaurant]):
    prefs = UserPreferences(location="Bangalore", budget=Budget.MEDIUM, min_rating=3.5)
    result = filter_service.apply(sample_restaurants, prefs)
    # Medium budget: costs 400, 500, 550 in Bangalore (not 250 low, 900 high)
    assert len(result.candidates) == 3
    assert all(r.city_normalized == "bangalore" for r in result.candidates)


def test_filter_unknown_location_empty(filter_service: CandidateFilterService, sample_restaurants: list[Restaurant]):
    prefs = UserPreferences(location="Tokyo", budget=Budget.MEDIUM)
    result = filter_service.apply(sample_restaurants, prefs)
    assert result.is_empty
    assert result.hints


def test_filter_location_alias_bengaluru(filter_service: CandidateFilterService, sample_restaurants: list[Restaurant]):
    prefs = UserPreferences(location="Bengaluru", budget=Budget.MEDIUM, min_rating=3.0)
    result = filter_service.apply(sample_restaurants, prefs)
    assert len(result.candidates) == 3


# --- Cuisine ---


def test_filter_by_cuisine(filter_service: CandidateFilterService, sample_restaurants: list[Restaurant]):
    prefs = UserPreferences(location="Bangalore", budget=Budget.MEDIUM, cuisine="Italian", min_rating=3.5)
    result = filter_service.apply(sample_restaurants, prefs)
    assert {r.id for r in result.candidates} == {"1"}


def test_filter_relaxes_cuisine_when_zero(filter_service: CandidateFilterService, sample_restaurants: list[Restaurant]):
    prefs = UserPreferences(
        location="Bangalore",
        budget=Budget.MEDIUM,
        cuisine="Ethiopian",
        min_rating=3.5,
    )
    result = filter_service.apply(sample_restaurants, prefs)
    assert "cuisine" in result.relaxed_constraints
    assert len(result.candidates) > 0


# --- Rating ---


def test_filter_by_min_rating(filter_service: CandidateFilterService, sample_restaurants: list[Restaurant]):
    prefs = UserPreferences(location="Bangalore", budget=Budget.MEDIUM, min_rating=4.5)
    result = filter_service.apply(sample_restaurants, prefs)
    assert all(r.rating >= 4.5 for r in result.candidates)
    assert len(result.candidates) == 1


# --- Budget ---


def test_filter_by_budget_low(filter_service: CandidateFilterService, sample_restaurants: list[Restaurant]):
    prefs = UserPreferences(location="Bangalore", budget=Budget.LOW, min_rating=3.0)
    result = filter_service.apply(sample_restaurants, prefs)
    for r in result.candidates:
        assert r.approximate_cost is None or r.approximate_cost <= THRESHOLDS.p33


def test_filter_by_budget_high(filter_service: CandidateFilterService, sample_restaurants: list[Restaurant]):
    prefs = UserPreferences(location="Bangalore", budget=Budget.HIGH, min_rating=3.0)
    result = filter_service.apply(sample_restaurants, prefs)
    for r in result.candidates:
        assert r.approximate_cost is None or r.approximate_cost > THRESHOLDS.p66


# --- Additional preferences ---


def test_filter_additional_preferences_or_match(
    filter_service: CandidateFilterService, sample_restaurants: list[Restaurant]
):
    prefs = UserPreferences(
        location="Bangalore",
        budget=Budget.MEDIUM,
        min_rating=3.5,
        additional_preferences=["family"],
    )
    result = filter_service.apply(sample_restaurants, prefs)
    assert any("5" == r.id for r in result.candidates)


def test_filter_skips_keyword_when_zero_matches(
    filter_service: CandidateFilterService, sample_restaurants: list[Restaurant]
):
    prefs = UserPreferences(
        location="Bangalore",
        budget=Budget.MEDIUM,
        min_rating=3.5,
        additional_preferences=["michelin star"],
    )
    result = filter_service.apply(sample_restaurants, prefs)
    assert len(result.candidates) == 3


# --- Truncation ---


def test_filter_truncates_to_max_candidates():
    many = [
        _restaurant(str(i), f"R{i}", rating=3.0 + (i % 20) * 0.1, cost=400 + (i % 3) * 100)
        for i in range(80)
    ]
    service = CandidateFilterService(METADATA, max_candidates=50)
    prefs = UserPreferences(location="Bangalore", budget=Budget.MEDIUM, min_rating=3.0)
    result = service.apply(many, prefs)
    assert len(result.candidates) == 50
    assert result.truncated is True
    assert result.pre_truncate_count == 80


def test_filter_exactly_max_candidates_no_truncate():
    rows = [
        _restaurant(str(i), f"R{i}", rating=4.0, cost=500)
        for i in range(50)
    ]
    service = CandidateFilterService(METADATA, max_candidates=50)
    prefs = UserPreferences(location="Bangalore", budget=Budget.MEDIUM, min_rating=3.0)
    result = service.apply(rows, prefs)
    assert len(result.candidates) == 50
    assert result.truncated is False


# --- apply_filter helper ---


def test_apply_filter_helper(sample_restaurants: list[Restaurant]):
    prefs = UserPreferences(location="Bangalore", budget=Budget.MEDIUM)
    result = apply_filter(sample_restaurants, prefs, METADATA)
    assert len(result.candidates) <= 50


# --- Integration: performance on cached dataset ---


@pytest.mark.integration
def test_filter_performance_under_100ms():
    from pathlib import Path

    if not Path("src/data/cache/restaurants.parquet").exists():
        pytest.skip("Cache missing")

    from src.data.repository import RestaurantRepository

    repo = RestaurantRepository()
    repo.load()
    service = CandidateFilterService(repo.metadata)
    prefs = UserPreferences(location="Bangalore", budget=Budget.MEDIUM, cuisine="North Indian", min_rating=4.0)

    start = time.perf_counter()
    result = service.apply(repo.all(), prefs)
    elapsed_ms = (time.perf_counter() - start) * 1000

    assert len(result.candidates) <= 50
    assert elapsed_ms < 100, f"Filter took {elapsed_ms:.1f}ms (target <100ms)"
