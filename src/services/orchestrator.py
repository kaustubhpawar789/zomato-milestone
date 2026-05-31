"""Orchestration layer: end-to-end recommendation flow.

Phase 5 deliverable — single entry-point for the recommendation pipeline:
    validate → filter → prompt → invoke → validate_and_enrich → RecommendationResponse
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Optional

from src.data.repository import get_repository
from src.models.preferences import UserPreferences
from src.models.recommendation import RecommendationResponse
from src.services.filter import FilterResult, get_filter_service
from src.services.validation import ValidationError, validate_preferences
from src.services.recommendation_engine import RecommendationEngine

logger = logging.getLogger(__name__)


def empty_response_with_hints(prefs: UserPreferences) -> RecommendationResponse:
    """
    Create an empty response with helpful hints for empty search results.

    Args:
        prefs: User preferences that yielded no results

    Returns:
        Empty RecommendationResponse with metadata hints
    """
    hints = []
    if prefs.cuisine:
        hints.append(f"Try removing the cuisine filter '{prefs.cuisine}'")
    if prefs.min_rating > 3.5:
        hints.append(f"Try lowering your minimum rating from {prefs.min_rating}")
    if not hints:
        hints.append("Try broadening your search criteria")

    metadata = {
        "candidate_count": 0,
        "result_count": 0,
        "hints": hints,
    }

    return RecommendationResponse(
        recommendations=[],
        summary="No restaurants match your search criteria. " + " or ".join(hints) + ".",
        metadata=metadata,
    )


def get_recommendations(
    prefs: UserPreferences,
    request_id: Optional[str] = None,
) -> RecommendationResponse:
    """
    End-to-end orchestration: validate → filter → prompt → invoke → enrich.

    This is the main entry point for getting recommendations.

    Args:
        prefs: User preferences
        request_id: Optional request ID for tracking (generated if not provided)

    Returns:
        RecommendationResponse with ranked recommendations

    Raises:
        ValidationError: On preference validation failure (field-level errors)
        RuntimeError: On LLM failure (user-friendly message)
    """
    # Generate request ID if not provided
    if not request_id:
        request_id = str(uuid.uuid4())

    logger.info(f"[{request_id}] get_recommendations started")
    orchestration_start = time.time()

    try:
        # Step 1: Validate preferences
        logger.debug(f"[{request_id}] Validating preferences")
        try:
            validate_preferences(prefs)
        except (ValueError, ValidationError) as exc:
            logger.warning(f"[{request_id}] Preference validation failed: {exc}")
            raise

        # Step 2: Get all restaurants from repository
        logger.debug(f"[{request_id}] Loading restaurants from repository")
        repository = get_repository()
        all_restaurants = repository.all()
        logger.debug(f"[{request_id}] Loaded {len(all_restaurants)} restaurants")

        # Step 3: Filter candidates
        logger.debug(f"[{request_id}] Applying filter service")
        filter_service = get_filter_service(repository.metadata)
        filter_result: FilterResult = filter_service.apply(all_restaurants, prefs)
        candidates = filter_result.candidates
        logger.info(
            f"[{request_id}] Filtered to {len(candidates)} candidates"
            f" (truncated={filter_result.truncated},"
            f" relaxed={filter_result.relaxed_constraints})"
        )

        # Step 4: Handle empty result case
        if not candidates:
            logger.info(f"[{request_id}] No candidates after filtering, returning hints")
            response = empty_response_with_hints(prefs)
            response.metadata["request_id"] = request_id
            if filter_result.hints:
                response.metadata["filter_hints"] = filter_result.hints
            return response

        # Step 5: Invoke recommendation engine
        logger.debug(f"[{request_id}] Invoking recommendation engine")
        engine = RecommendationEngine()
        response = engine.get_recommendations_for_candidates(
            prefs, candidates, request_id=request_id
        )

        # Step 6: Attach orchestration metadata
        orchestration_ms = (time.time() - orchestration_start) * 1000
        response.metadata["orchestration_latency_ms"] = round(orchestration_ms, 1)
        if filter_result.relaxed_constraints:
            response.metadata["relaxed_constraints"] = filter_result.relaxed_constraints
        if filter_result.truncated:
            response.metadata["candidates_truncated"] = True
            response.metadata["pre_truncate_count"] = filter_result.pre_truncate_count

        logger.info(
            f"[{request_id}] Recommendation flow completed: "
            f"{response.result_count} results from {len(candidates)} candidates "
            f"in {orchestration_ms:.0f}ms"
        )

        return response

    except ValidationError:
        # Validation errors are expected and should be returned as error responses
        raise
    except RuntimeError as exc:
        # LLM errors are runtime failures (already user-friendly from engine)
        logger.error(f"[{request_id}] LLM error: {exc}")
        raise
    except Exception as exc:
        # Unexpected errors — wrap with user-friendly message
        logger.exception(f"[{request_id}] Unexpected error in recommendation flow")
        raise RuntimeError(
            "Something went wrong while generating recommendations. "
            "Please try again later."
        ) from exc
