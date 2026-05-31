"""Unit tests for ingestion parsing and budget thresholds."""

from __future__ import annotations

import pandas as pd

from src.data.ingestion import (
    _extract_city_from_address,
    _transform_raw_dataframe,
    compute_budget_thresholds,
    parse_cost,
    parse_rating,
)


def test_parse_rating_valid():
    assert parse_rating("4.1/5") == 4.1
    assert parse_rating("3.0/5") == 3.0


def test_parse_rating_invalid():
    assert parse_rating("-") is None
    assert parse_rating("NEW") is None
    assert parse_rating("") is None
    assert parse_rating(None) is None


def test_parse_cost():
    assert parse_cost("800") == 800
    assert parse_cost("₹1,200 for two") == 1200
    assert parse_cost("") is None


def test_extract_city_aliases():
    assert _extract_city_from_address("Foo, Bengaluru") == "bangalore"
    assert _extract_city_from_address("Road, Banashankari, Bangalore") == "bangalore"


def test_transform_drops_incomplete_rows():
    raw = pd.DataFrame(
        [
            {
                "name": "A",
                "location": "Koramangala",
                "address": "1st St, Bangalore",
                "rate": "4.0/5",
                "cuisines": "Italian",
                "approx_cost(for two people)": "500",
                "listed_in(city)": "BTM",
                "votes": 10,
                "rest_type": "Cafe",
                "online_order": "Yes",
                "book_table": "No",
            },
            {
                "name": "",
                "location": "X",
                "address": "Addr",
                "rate": "4.0/5",
                "cuisines": "",
                "approx_cost(for two people)": "500",
                "listed_in(city)": "BTM",
                "votes": None,
                "rest_type": "",
                "online_order": "",
                "book_table": "",
            },
            {
                "name": "B",
                "location": "",
                "address": "Addr, Bangalore",
                "rate": "3.5/5",
                "cuisines": "Chinese",
                "approx_cost(for two people)": "600",
                "listed_in(city)": "BTM",
                "votes": 5,
                "rest_type": "",
                "online_order": "",
                "book_table": "",
            },
        ]
    )
    df, dropped = _transform_raw_dataframe(raw)
    assert len(df) == 1
    assert dropped == 2
    assert df.iloc[0]["name"] == "A"
    assert df.iloc[0]["city_normalized"] == "bangalore"


def test_budget_thresholds():
    df = pd.DataFrame({"approximate_cost": [100, 200, 300, 400, 500, 600], "city_normalized": ["bangalore"] * 6})
    global_t, per_city = compute_budget_thresholds(df)
    assert global_t.sample_size == 6
    assert global_t.p33 <= global_t.p66
    assert "bangalore" in per_city
