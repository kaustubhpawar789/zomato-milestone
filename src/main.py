"""Application entrypoint — CLI demo for the recommendation pipeline."""

from __future__ import annotations

import json
import logging
import sys

from src.data.repository import get_repository
from src.models.preferences import Budget, UserPreferences
from src.services.filter import CandidateFilterService
from src.services.orchestrator import get_recommendations
from src.services.validation import ValidationError


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    force = "--force" in sys.argv
    repo = get_repository()
    metadata = repo.load(force_refresh=force)
    print(f"Ready: {repo.count()} restaurants (cache_hit={metadata.cache_hit})")
    print(f"  Cities (sample): {repo.unique_cities()[:5]}")

    if "--demo-filter" in sys.argv:
        prefs = UserPreferences(
            location="Bangalore",
            budget=Budget.MEDIUM,
            cuisine="North Indian",
            min_rating=4.0,
        )
        result = CandidateFilterService(metadata).apply(repo.all(), prefs)
        print(f"  Filter demo: {len(result.candidates)} candidates (truncated={result.truncated})")
        if result.relaxed_constraints:
            print(f"  Relaxed: {result.relaxed_constraints}")

    if "--demo-recommend" in sys.argv:
        prefs = UserPreferences(
            location="Bangalore",
            budget=Budget.MEDIUM,
            cuisine="North Indian",
            min_rating=4.0,
        )
        print("\n--- Recommendation Demo ---")
        try:
            response = get_recommendations(prefs)
            print(f"  Results: {response.result_count}")
            if response.summary:
                print(f"  Summary: {response.summary}")
            for rec in response.recommendations:
                r = rec.restaurant
                print(
                    f"  #{rec.rank} {r.name} "
                    f"| {r.cuisines} | ★{r.rating} | ₹{r.approximate_cost or '?'}"
                )
                print(f"      → {rec.explanation}")
            meta = response.metadata
            if "llm_latency_ms" in meta:
                print(f"  LLM latency: {meta['llm_latency_ms']}ms")
            if "orchestration_latency_ms" in meta:
                print(f"  Total latency: {meta['orchestration_latency_ms']}ms")
        except ValidationError as exc:
            print(f"  Validation error: {exc}")
        except RuntimeError as exc:
            print(f"  Error: {exc}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
