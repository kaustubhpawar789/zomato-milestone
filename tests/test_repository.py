"""Unit tests for RestaurantRepository."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.data.repository import RestaurantRepository, get_repository, reset_repository


@pytest.fixture(autouse=True)
def _reset_singleton():
    reset_repository()
    yield
    reset_repository()


@pytest.fixture
def repo() -> RestaurantRepository:
    cache = Path("src/data/cache/restaurants.parquet")
    if not cache.exists():
        pytest.skip("Parquet cache missing; run ingestion first.")
    return RestaurantRepository()


def test_load_and_count(repo: RestaurantRepository):
    metadata = repo.load()
    assert repo.count() > 0
    assert metadata.row_count == repo.count()
    assert repo.is_loaded


def test_all_returns_copy(repo: RestaurantRepository):
    repo.load()
    first = repo.all()
    second = repo.all()
    assert first is not second
    assert len(first) == len(second)


def test_get_by_id(repo: RestaurantRepository):
    repo.load()
    sample = repo.all()[0]
    found = repo.get_by_id(sample.id)
    assert found is not None
    assert found.name == sample.name
    assert repo.get_by_id("nonexistent-id-xyz") is None


def test_unique_cities_sorted(repo: RestaurantRepository):
    repo.load()
    cities = repo.unique_cities()
    assert len(cities) > 0
    assert cities == sorted(cities, key=str.casefold)
    assert all(c.strip() for c in cities)
    assert "Bangalore" in cities


def test_get_budget_thresholds(repo: RestaurantRepository):
    repo.load()
    global_t = repo.metadata.budget_thresholds_global
    assert repo.get_budget_thresholds("").p33 == global_t.p33
    if repo.unique_cities():
        city_norm = repo.all()[0].city_normalized
        thresholds = repo.get_budget_thresholds(city_norm)
        assert thresholds.p33 <= thresholds.p66


def test_singleton_get_repository():
    r1 = get_repository()
    r2 = get_repository()
    assert r1 is r2


def test_metadata_requires_load():
    repo = RestaurantRepository()
    with pytest.raises(RuntimeError):
        _ = repo.metadata
