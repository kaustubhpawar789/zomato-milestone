"""Recommendation engine: LLM orchestration with guardrails.

Phase 5 deliverable — end-to-end recommendation flow:
  invoke(prompt) → parse JSON → whitelist IDs → merge & sort → RecommendationResponse
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Optional

from src.llm import LLMClient, get_llm_client
from src.models.preferences import UserPreferences
from src.models.recommendation import Recommendation, RecommendationResponse
from src.models.restaurant import Restaurant
from src.services.prompt_builder import PromptBuilder

logger = logging.getLogger(__name__)

# Regex to extract JSON from a markdown code fence (```json ... ```)
_JSON_FENCE_RE = re.compile(
    r"```(?:json)?\s*\n?(.*?)\n?\s*```", re.DOTALL
)


def _extract_json_text(raw: str) -> str:
    """Strip markdown code fences if the LLM wrapped its JSON in them."""
    match = _JSON_FENCE_RE.search(raw)
    if match:
        return match.group(1).strip()
    return raw.strip()


class RecommendationEngine:
    """
    Orchestrates the end-to-end recommendation flow with guardrails.

    Responsibilities:
    - Call LLM with prompt
    - Parse JSON response (with single retry)
    - Validate against candidate set (hallucination prevention)
    - Merge LLM explanations with restaurant fields
    - Handle errors gracefully
    """

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        prompt_builder: Optional[PromptBuilder] = None,
        timeout: float = 30.0,
    ):
        """
        Initialize recommendation engine.

        Args:
            llm_client: LLMClient instance (default: auto-initialize from config)
            prompt_builder: PromptBuilder instance (default: new instance with default top_n=5)
            timeout: LLM call timeout in seconds (default: 30.0)
        """
        self.llm_client = llm_client or get_llm_client()
        self.prompt_builder = prompt_builder or PromptBuilder(top_n=5)
        self.timeout = timeout

    # ------------------------------------------------------------------
    # LLM invocation with retry & timeout
    # ------------------------------------------------------------------

    def invoke(
        self, prompt: str, system: str = "", max_retries: int = 1
    ) -> dict:
        """
        Call LLM and parse JSON response with single retry on malformed JSON.

        Uses a thread-pool executor to enforce ``self.timeout`` on the LLM
        call itself (guards against hanging connections).

        Args:
            prompt: User prompt with candidates
            system: System message
            max_retries: Number of retries on JSON parse failure (default: 1)

        Returns:
            Parsed JSON response (as dict) and elapsed time as a tuple ``(dict, float)``
            — **however**, for backward-compat the public return is just ``dict``.
            Use ``invoke_with_latency()`` to get timing.

        Raises:
            RuntimeError: If LLM call fails or JSON parsing fails after retries
        """
        result, _ = self._invoke_with_latency(prompt, system, max_retries)
        return result

    def _invoke_with_latency(
        self, prompt: str, system: str = "", max_retries: int = 1
    ) -> tuple[dict, float]:
        """Internal invoke that also returns wall-clock latency in ms."""
        attempt = 0
        last_error = None
        cumulative_start = time.time()

        while attempt <= max_retries:
            attempt += 1
            try:
                logger.debug(f"Calling LLM (attempt {attempt}/{max_retries + 1})")
                start_time = time.time()

                # Enforce timeout via thread-pool executor
                response_text = self._call_llm_with_timeout(prompt, system)

                elapsed_ms = (time.time() - start_time) * 1000
                logger.debug(f"LLM call completed in {elapsed_ms:.1f}ms")

                # Try to parse JSON (strip markdown fences first)
                try:
                    clean_text = _extract_json_text(response_text)
                    response_json = json.loads(clean_text)
                    logger.debug("JSON parsing succeeded")
                    total_ms = (time.time() - cumulative_start) * 1000
                    return response_json, total_ms

                except json.JSONDecodeError as exc:
                    last_error = exc
                    if attempt <= max_retries:
                        logger.warning(
                            f"JSON parse failed on attempt {attempt}, retrying with constraint"
                        )
                        # Retry with stricter instruction
                        prompt = (
                            prompt
                            + "\n\n**IMPORTANT: Return ONLY valid JSON. No other text.**"
                        )
                    else:
                        logger.error(f"JSON parse failed after {max_retries + 1} attempts")
                        raise RuntimeError(
                            f"LLM response is not valid JSON: {exc}"
                        ) from exc

            except FuturesTimeoutError:
                logger.error(
                    f"LLM call timed out after {self.timeout}s on attempt {attempt}"
                )
                raise RuntimeError(
                    f"Recommendation request timed out after {self.timeout} seconds. "
                    "Please try again later."
                )

            except RuntimeError:
                # Re-raise RuntimeErrors (timeout, JSON) directly
                raise

            except Exception as exc:
                logger.exception(f"LLM call failed on attempt {attempt}: {exc}")
                if attempt > max_retries:
                    raise RuntimeError(
                        f"Unable to get recommendations at this time. "
                        f"Please try again later. (Detail: {exc})"
                    ) from exc
                last_error = exc

        # Should not reach here, but safety fallback
        raise RuntimeError(f"LLM invocation failed after {max_retries + 1} attempts")

    def _call_llm_with_timeout(self, prompt: str, system: str) -> str:
        """Call llm_client.complete with configurable timeout enforcement."""
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(self.llm_client.complete, prompt, system=system)
            return future.result(timeout=self.timeout)

    # ------------------------------------------------------------------
    # Response validation & enrichment
    # ------------------------------------------------------------------

    def validate_and_enrich(
        self,
        llm_response: dict,
        candidates: list[Restaurant],
        request_id: Optional[str] = None,
        llm_latency_ms: Optional[float] = None,
    ) -> RecommendationResponse:
        """
        Validate LLM response and merge with restaurant fields.

        Args:
            llm_response: Parsed JSON from LLM
            candidates: Original candidate restaurants (for validation)
            request_id: Optional request ID for tracking
            llm_latency_ms: Optional LLM call latency in milliseconds

        Returns:
            RecommendationResponse with enriched recommendations

        Raises:
            ValueError: If response format is invalid
        """
        try:
            # Build candidate ID set for whitelist validation
            candidate_ids = {r.id for r in candidates}
            candidate_map = {r.id: r for r in candidates}

            # Extract recommendations from response
            if "recommendations" not in llm_response:
                raise ValueError("LLM response missing 'recommendations' field")

            recommendations_data = llm_response.get("recommendations", [])
            if not isinstance(recommendations_data, list):
                raise ValueError("'recommendations' must be a list")

            # Validate and enrich each recommendation
            validated_recs = []
            dropped_ids = []
            for rec_data in recommendations_data:
                restaurant_id = rec_data.get("restaurant_id")

                # Whitelist validation: only accept valid IDs
                if restaurant_id not in candidate_ids:
                    logger.warning(
                        f"Dropping hallucinated/invalid restaurant_id: {restaurant_id}"
                    )
                    dropped_ids.append(str(restaurant_id))
                    continue

                # Ensure required fields
                rank = rec_data.get("rank")
                explanation = rec_data.get("explanation", "")

                if rank is None:
                    logger.warning(f"Missing rank for {restaurant_id}, skipping")
                    continue

                # Get restaurant object
                restaurant = candidate_map[restaurant_id]

                # Create recommendation with merged fields
                rec = Recommendation(
                    restaurant_id=restaurant_id,
                    rank=int(rank),
                    explanation=str(explanation),
                    restaurant=restaurant,
                )
                validated_recs.append(rec)

            # Re-sort by rank (model order may be inconsistent)
            validated_recs.sort(key=lambda r: r.rank)

            # Extract summary if present
            summary = llm_response.get("summary")
            if summary:
                summary = str(summary)

            # Build metadata
            metadata = {
                "candidate_count": len(candidates),
                "result_count": len(validated_recs),
            }
            if request_id:
                metadata["request_id"] = request_id
            if llm_latency_ms is not None:
                metadata["llm_latency_ms"] = round(llm_latency_ms, 1)
            if dropped_ids:
                metadata["dropped_hallucinated_ids"] = dropped_ids

            logger.info(
                f"Enriched {len(validated_recs)} recommendations "
                f"from {len(candidates)} candidates"
                + (f" (dropped {len(dropped_ids)} hallucinated)" if dropped_ids else "")
            )

            return RecommendationResponse(
                recommendations=validated_recs,
                summary=summary,
                metadata=metadata,
            )

        except Exception as exc:
            logger.exception("Error enriching LLM response")
            raise ValueError(f"Invalid LLM response format: {exc}") from exc

    # ------------------------------------------------------------------
    # Full flow: build prompt → invoke → validate & enrich
    # ------------------------------------------------------------------

    def get_recommendations_for_candidates(
        self,
        preferences: UserPreferences,
        candidates: list[Restaurant],
        request_id: Optional[str] = None,
    ) -> RecommendationResponse:
        """
        End-to-end method: build prompt, invoke LLM, validate and enrich.

        Args:
            preferences: User preferences object
            candidates: Filtered candidate restaurants
            request_id: Optional request ID

        Returns:
            Complete RecommendationResponse

        Raises:
            RuntimeError: On LLM failure (with user-friendly message)
            ValueError: On response validation failure
        """
        if not candidates:
            logger.warning("Empty candidate list, returning empty response")
            return RecommendationResponse(
                recommendations=[],
                metadata={
                    "candidate_count": 0,
                    "result_count": 0,
                    "request_id": request_id,
                },
            )

        try:
            # Build prompt
            prompt = self.prompt_builder.build_prompt(preferences, candidates)
            system = self.prompt_builder.build_system_message()

            logger.debug(f"Built prompt ({len(prompt)} chars)")

            # Invoke LLM (with latency tracking)
            llm_response_json, llm_latency_ms = self._invoke_with_latency(
                prompt, system=system
            )

            # Validate and enrich
            response = self.validate_and_enrich(
                llm_response_json,
                candidates,
                request_id=request_id,
                llm_latency_ms=llm_latency_ms,
            )

            return response

        except Exception as exc:
            logger.exception("Error in recommendation flow")
            raise
