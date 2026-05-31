# Edge Case Catalog: Restaurant Recommendation System

This document defines **edge cases**, **expected behavior**, and **implementation guidance** for every layer of the system. Use it during development (Phases 1–7), code review, and manual QA.

**Related docs:** [`architecture.md`](architecture.md) · [`implementation-plan.md`](implementation-plan.md) · [`context.md`](../context.md)

---

## How to Use This Document

| Column | Meaning |
|--------|---------|
| **ID** | Stable reference (e.g. `EC-F-012`) for tests and issues |
| **Priority** | P0 = must handle for milestone; P1 = should handle; P2 = nice-to-have |
| **Layer** | Where the edge case is detected or handled |
| **Behavior** | What the system must do |
| **Test hint** | Suggested way to verify |

Prefix key: `EC-D` data · `EC-I` ingestion · `EC-V` validation · `EC-F` filter · `EC-P` prompt · `EC-L` LLM · `EC-O` orchestration · `EC-U` UI · `EC-C` config · `EC-S` security

---

## 1. Data Ingestion (`EC-I`, `EC-D`)

### 1.1 External data & cache

| ID | Scenario | Priority | Behavior | Test hint |
|----|----------|----------|----------|-----------|
| EC-I-001 | Hugging Face download fails (network, 503) | P0 | Retry 2–3× with exponential backoff; if all fail, show setup error with link to dataset and “check network” | Mock `ConnectionError` |
| EC-I-002 | HF dataset unreachable (DNS, firewall) | P0 | Same as EC-I-001; do not start app with empty repository silently | Disconnect network on first run |
| EC-I-003 | Cache file exists but is corrupted (invalid Parquet) | P0 | Delete or quarantine corrupt file; re-run ingestion from HF | Truncate Parquet file |
| EC-I-004 | Cache exists but schema version changed | P1 | Compare `schema_version` in metadata; if mismatch, re-ingest and overwrite cache | Bump version constant |
| EC-I-005 | Partial write during cache save (crash mid-write) | P1 | Write to temp file then atomic rename; on load failure, treat as cache miss | Kill process during save |
| EC-I-006 | Disk full while writing cache | P1 | Fail ingestion with clear message; do not leave half-written cache as valid | Mock `OSError` ENOSPC |
| EC-I-007 | Second startup: valid cache hit | P0 | Load Parquet only; skip HF download; log `cache_hit=true` | Run init twice |
| EC-I-008 | User deletes cache manually | P0 | Transparent re-download on next init | Delete `restaurants.parquet` |
| EC-I-009 | HF dataset updated (more/fewer rows) | P2 | Optional `FORCE_REFRESH=true` env to bypass cache | Document in README |

### 1.2 Schema & field mapping

| ID | Scenario | Priority | Behavior | Test hint |
|----|----------|----------|----------|-----------|
| EC-D-001 | Unexpected or renamed HF columns | P0 | Schema discovery on first load; mapping table in `ingestion.py`; log unmapped columns | Spike notebook |
| EC-D-002 | Missing optional column (e.g. `address`) | P0 | Set field to `null`/empty; continue ingestion | Fixture without address |
| EC-D-003 | Missing required column (`name`, location, rating) | P0 | Drop row; increment `dropped_incomplete` counter; log sample count | Fixture with null name |
| EC-D-004 | Duplicate restaurant names in same city | P1 | Generate unique `id` (hash of name+city+row index); never collide IDs | Duplicate fixture rows |
| EC-D-005 | Rating stored as string (`"4.5/5"`, `"NEW"`) | P0 | Parse numeric prefix; map non-numeric to `null` and drop or default per policy | Rows with `"NEW"`, `"-"` |
| EC-D-006 | Rating out of range (< 0 or > 5) | P0 | Clamp to [0, 5] or drop row; document choice in logs | `rating=9.2` |
| EC-D-007 | Cost as string (`"₹1,200 for two"`) | P0 | Extract digits; normalize to `approximate_cost` int | Various cost formats |
| EC-D-008 | Cost missing or zero | P1 | Exclude from budget percentile calc; budget filter may skip or use global fallback | `cost=null` |
| EC-D-009 | Multiple cuisines in one field (`"Italian, Pizza, Fast Food"`) | P0 | Store normalized string; filter uses token/substring match | Multi-cuisine row |
| EC-D-010 | Empty cuisine string | P1 | Keep row; cuisine filter only applies when user specifies cuisine | Blank cuisine |
| EC-D-011 | Location only in address, not city field | P1 | Populate `city` via heuristic (last token, known city list) or copy `location` | Messy address rows |
| EC-D-012 | Non-ASCII / emoji in name or address | P1 | Preserve UTF-8; trim only; no encoding errors on display | Unicode names |
| EC-D-013 | Extremely long address (> 500 chars) | P1 | Truncate for LLM prompt; full address in UI if available | Long address fixture |

### 1.3 Post-ingestion statistics

| ID | Scenario | Priority | Behavior | Test hint |
|----|----------|----------|----------|-----------|
| EC-D-020 | City has too few rows for per-city budget percentiles | P0 | Fall back to **global** percentiles for that city’s budget filter | City with < 30 restaurants |
| EC-D-021 | All costs identical in a city (zero variance) | P1 | Treat all as `medium` budget or use global thresholds | Synthetic flat cost |
| EC-D-022 | >50% rows dropped after cleaning | P1 | Log warning; still run if remaining count > 0 | Aggressive drop rules |
| EC-D-023 | Zero rows remain after cleaning | P0 | Fail startup; “dataset unusable” — do not run empty app | Drop-all fixture |

---

## 2. User Input Validation (`EC-V`)

### 2.1 Required fields

| ID | Scenario | Priority | Behavior | Test hint |
|----|----------|----------|----------|-----------|
| EC-V-001 | Empty `location` (whitespace only) | P0 | Reject before filter; message: “Location is required.” | `"   "` |
| EC-V-002 | Missing `budget` | P0 | Reject; message: “Select a budget: low, medium, or high.” | `budget=null` |
| EC-V-003 | Invalid `budget` value (`"cheap"`, `1`) | P0 | Reject; list allowed enum values | Invalid enum |
| EC-V-004 | `min_rating` < 0 or > 5 | P0 | Reject; message: “Rating must be between 0 and 5.” | `-1`, `6` |
| EC-V-005 | `min_rating` non-numeric (`"four"`) | P0 | Reject with type error | String input |
| EC-V-006 | `min_rating` omitted | P0 | Apply default (e.g. `3.5`) — do not treat as 0 | Omit field |

### 2.2 Optional & free-text fields

| ID | Scenario | Priority | Behavior | Test hint |
|----|----------|----------|----------|-----------|
| EC-V-010 | Empty `cuisine` | P0 | Skip cuisine filter step | `cuisine=""` |
| EC-V-011 | Cuisine with different casing (`"italian"` vs `"Italian"`) | P0 | Case-insensitive match after normalization | Mixed case |
| EC-V-012 | Cuisine typo (`"Itallian"`) | P1 | No match → may trigger filter relaxation or empty set; do not crash | Typo search |
| EC-V-013 | Very long `cuisine` (> 200 chars) | P1 | Truncate or reject with max-length message | 500-char string |
| EC-V-014 | `additional_preferences` empty list | P0 | Skip keyword filter | `[]` |
| EC-V-015 | `additional_preferences` with empty strings | P1 | Strip and ignore empty tags | `["", "  "]` |
| EC-V-016 | Adversarial / prompt-injection in preferences (`"Ignore instructions..."`) | P0 | Treat as opaque user text; system prompt enforces JSON-only + candidate whitelist; bound length (e.g. 500 chars total) | Injection strings |
| EC-V-017 | Special characters in location (`<script>`, SQL-like) | P0 | Sanitize for display (escape HTML in UI); no eval; string match only | XSS-style input |
| EC-V-018 | Unicode location (`"बैंगलोर"`) | P1 | Match if dataset contains equivalent; else no results + hints | Non-Latin input |

### 2.3 Location ambiguity

| ID | Scenario | Priority | Behavior | Test hint |
|----|----------|----------|----------|-----------|
| EC-V-020 | Location not in dataset (`"Tokyo"`) | P0 | Zero candidates → empty state with “try a supported city” + optional city list | Unknown city |
| EC-V-021 | Abbreviation (`"BLR"` vs `"Bangalore"`) | P1 | Alias map or fuzzy match if implemented; else document supported names | Abbreviation |
| EC-V-022 | Location matches multiple cities (`"New"`) | P1 | Contains-match may over-match; cap candidates at 50; prefer exact city match when available | Partial string |
| EC-V-023 | Extra spaces / punctuation (`"  Delhi ,  "`) | P0 | Trim and normalize before filter | Messy input |

---

## 3. Candidate Filtering (`EC-F`)

### 3.1 Zero, few, and many results

| ID | Scenario | Priority | Behavior | Test hint |
|----|----------|----------|----------|-----------|
| EC-F-001 | Zero candidates after full pipeline | P0 | Return empty response + hints (lower rating, change cuisine, broaden location) | Impossible combo |
| EC-F-002 | Zero candidates → relax cuisine once | P0 | Retry without cuisine filter; set `metadata.relaxed_constraints=["cuisine"]`; show UI notice | Strict cuisine + city |
| EC-F-003 | Still zero after relaxation | P0 | Empty state; do **not** call LLM | All filters strict |
| EC-F-004 | Exactly 1 candidate | P0 | Send 1 candidate to LLM; return 1 recommendation (rank 1) | Unique match |
| EC-F-005 | 2–5 candidates, `TOP_N=5` | P0 | LLM ranks all available; UI shows fewer than 5 cards | Small set |
| EC-F-006 | > `MAX_CANDIDATES_FOR_LLM` (50) | P0 | Sort by rating desc (optional cost fit); take top 50; log `truncated=true` | Popular city only |
| EC-F-007 | Exactly 50 candidates | P0 | No truncation flag; proceed normally | Boundary count |
| EC-F-008 | Single candidate but user asked top 5 | P0 | Return 1 result; no padding with fake entries | `TOP_N=5`, 1 match |

### 3.2 Per-filter edge cases

| ID | Scenario | Priority | Behavior | Test hint |
|----|----------|----------|----------|-----------|
| EC-F-010 | `min_rating=5.0` eliminates almost all rows | P0 | Valid; may yield zero → relaxation/empty flow | Rating 5.0 |
| EC-F-011 | `min_rating=0` | P0 | No rating filter effect (or include all with valid rating) | Zero floor |
| EC-F-012 | Budget `low` but city has no low-tier restaurants | P0 | Zero or few matches; empty/relax path | Skewed cost distribution |
| EC-F-013 | User budget `high` + cuisine rare in city | P0 | Few candidates; LLM still ranks available set | Niche cuisine |
| EC-F-014 | Cuisine filter: plural vs singular (`"Burger"` vs `"Burgers"`) | P1 | Token/substring match on normalized cuisines | Plural forms |
| EC-F-015 | `additional_preferences` match nothing in data | P1 | Keyword filter removes all → treat as zero candidates or skip keyword step if it zeroes set (document policy: **prefer skip keyword before zeroing**) | `"michelin star"` |
| EC-F-016 | Multiple additional tags (AND vs OR) | P0 | Document and implement consistently (recommended: **OR** — match any tag) | `["family-friendly", "outdoor"]` |
| EC-F-017 | Conflicting filters (high rating + low budget + rare cuisine) | P0 | Zero candidates → relaxation message | Strict combo |

### 3.3 Data quality during filter

| ID | Scenario | Priority | Behavior | Test hint |
|----|----------|----------|----------|-----------|
| EC-F-020 | Restaurant has `rating=null` in store | P0 | Exclude from rating filter or treat as below threshold; do not compare `None >= 4` | Null rating row |
| EC-F-021 | Restaurant missing `approximate_cost` | P1 | Include in non-budget filters; exclude from budget tier or include with `unknown` bucket | Null cost |
| EC-F-022 | Case mismatch on city (`"bangalore"` vs `"Bangalore"`) | P0 | Case-insensitive location match | Mixed case data |

---

## 4. Prompt Builder (`EC-P`)

| ID | Scenario | Priority | Behavior | Test hint |
|----|----------|----------|----------|-----------|
| EC-P-001 | Zero candidates passed to builder | P0 | Orchestrator must not call builder; assert/guard in dev | Call with `[]` |
| EC-P-002 | Candidate with missing optional fields | P0 | Omit null fields from JSON or send `"unknown"`; never crash serialization | Sparse restaurant |
| EC-P-003 | Prompt exceeds model context window | P1 | Reduce candidate count further or truncate explanations in instructions; log token estimate | 50 large rows |
| EC-P-004 | Duplicate `restaurant_id` in candidate list | P0 | Deduplicate before prompt; log warning | Duplicate IDs |
| EC-P-005 | User preferences include quotes/newlines | P0 | JSON-encode preferences block; no manual string concat | `"café \"fine\""` |
| EC-P-006 | `TOP_N` > candidate count | P0 | Instruct LLM: “rank all N candidates” where N = len(candidates) | `TOP_N=5`, 3 candidates |

---

## 5. LLM & Recommendation Engine (`EC-L`)

### 5.1 API & connectivity

| ID | Scenario | Priority | Behavior | Test hint |
|----|----------|----------|----------|-----------|
| EC-L-001 | Missing `LLM_API_KEY` | P0 | Fail at startup or on first request with “configure .env” | Empty key |
| EC-L-002 | Invalid / revoked API key | P0 | User message: auth failed; log error code; no stack trace in UI | Bad key |
| EC-L-003 | LLM request timeout | P0 | Configurable timeout; message: “Could not generate recommendations. Please try again.” | Mock timeout |
| EC-L-004 | Rate limit (429) | P0 | Single retry with backoff; then friendly error | Mock 429 |
| EC-L-005 | Provider outage (5xx) | P0 | Retry once; then error state | Mock 503 |
| EC-L-006 | Ollama/local LLM not running | P1 | Clear message when provider is `ollama` and connection refused | Stop Ollama |

### 5.2 Response parsing & validation

| ID | Scenario | Priority | Behavior | Test hint |
|----|----------|----------|----------|-----------|
| EC-L-010 | Response is not JSON (markdown fenced block) | P0 | Strip ```json fences; parse; if fail → one retry | Mock markdown wrapper |
| EC-L-011 | Malformed JSON | P0 | One retry with “valid JSON only”; then error | Truncated JSON |
| EC-L-012 | Valid JSON but wrong schema (missing `recommendations`) | P0 | Retry once; then error | `{}` |
| EC-L-013 | Empty `recommendations` array | P0 | Return empty results + “try different preferences”; log warning | `[]` |
| EC-L-014 | Hallucinated `restaurant_id` not in candidates | P0 | Drop invalid entries; log `hallucinated_id` | Mock fake ID |
| EC-L-015 | Duplicate ranks (two `rank: 1`) | P0 | Re-sort by rank; tie-break by rating desc from datastore | Duplicate ranks |
| EC-L-016 | Missing `rank` on some items | P0 | Assign order by array position or rating | Partial ranks |
| EC-L-017 | Missing `explanation` | P0 | Fallback text: “Recommended based on your preferences.” | Null explanation |
| EC-L-018 | More than `TOP_N` recommendations returned | P1 | Take first `TOP_N` after sort | 10 items, TOP_N=5 |
| EC-L-019 | Fewer than `TOP_N` but valid IDs | P0 | Return what LLM gave; no padding | 2 of 5 |
| EC-L-020 | LLM recommends below `min_rating` in explanation only | P1 | Display uses **datastore** rating; filter already enforced; ignore prose contradicting data | Mock text |
| EC-L-021 | LLM invents restaurant name with valid ID | P0 | UI shows **canonical** name from repository, not LLM text | Wrong name in JSON |
| EC-L-022 | `summary` field missing | P0 | Omit summary section in UI | No summary key |
| EC-L-023 | `summary` present but empty string | P1 | Hide summary section | `""` |
| EC-L-024 | Explanation extremely long (> 1k chars) | P1 | Truncate for UI with ellipsis | Long text |

### 5.3 Model behavior quirks

| ID | Scenario | Priority | Behavior | Test hint |
|----|----------|----------|----------|-----------|
| EC-L-030 | Model returns same restaurant twice | P0 | Deduplicate by `restaurant_id`; keep best rank | Duplicate IDs |
| EC-L-031 | Model returns candidates in random order | P0 | Re-sort by `rank` after validation | Unordered list |
| EC-L-032 | Model refuses (“I can’t help”) | P0 | Treat as parse failure → retry → error | Refusal string |
| EC-L-033 | Non-English explanation | P1 | Accept; optional future: prompt “respond in English” | Hindi explanation |

---

## 6. Orchestration (`EC-O`)

| ID | Scenario | Priority | Behavior | Test hint |
|----|----------|----------|----------|-----------|
| EC-O-001 | `get_recommendations` called before repository init | P0 | Raise clear `RuntimeError` or return “system starting” | Early call |
| EC-O-002 | Repository empty (ingestion failed) | P0 | Block recommendations; show global error banner | Empty repo |
| EC-O-003 | Double submit (user clicks twice) | P1 | UI debounce / disable button during LLM call | Double-click |
| EC-O-004 | Concurrent requests (Streamlit rerun) | P1 | Each request isolated; no shared mutable candidate list | Parallel tabs |
| EC-O-005 | Identical preferences submitted twice | P2 | Optional short TTL cache of response | Same form twice |
| EC-O-006 | Partial LLM success (3 valid IDs, 2 invalid) | P0 | Return 3 enriched results; log dropped count | Mixed valid/invalid |
| EC-O-007 | All LLM IDs invalid after validation | P0 | Empty/error: “Could not validate recommendations.” | All fake IDs |

---

## 7. Presentation Layer (`EC-U`)

| ID | Scenario | Priority | Behavior | Test hint |
|----|----------|----------|----------|-----------|
| EC-U-001 | Form submitted with validation errors | P0 | Inline field errors; no LLM call | Invalid form |
| EC-U-002 | Loading state during 2–15 s LLM call | P0 | Spinner; disable submit | Slow mock LLM |
| EC-U-003 | Display missing cost on restaurant | P0 | Show “Cost not available” | `cost=null` |
| EC-U-004 | Display missing rating | P0 | Show “Rating N/A” or hide star | Null rating |
| EC-U-005 | Very long restaurant name in card | P1 | CSS truncate / wrap | 100+ char name |
| EC-U-006 | Filter relaxation applied | P0 | Banner: “Expanded search: cuisine filter relaxed.” | EC-F-002 path |
| EC-U-007 | Zero results empty state | P0 | Actionable copy per architecture §7.3 | EC-F-003 |
| EC-U-008 | LLM error state | P0 | Non-technical message + retry button | EC-L-003 |
| EC-U-009 | City dropdown vs free text mismatch | P1 | If dropdown: only listed cities; if text: allow any with validation message | Both input modes |
| EC-U-010 | Streamlit session reset mid-request | P1 | Graceful error or restart; no partial corrupt state | Refresh browser |

---

## 8. Configuration & Environment (`EC-C`)

| ID | Scenario | Priority | Behavior | Test hint |
|----|----------|----------|----------|-----------|
| EC-C-001 | `.env` file missing | P0 | Use defaults where safe; fail on missing API key for LLM | No `.env` |
| EC-C-002 | Invalid `TOP_N` (0, negative, non-int) | P0 | Default to 5; log warning | `TOP_N=0` |
| EC-C-003 | `MAX_CANDIDATES_FOR_LLM` < 1 | P0 | Clamp to minimum 1 or default 50 | `MAX=0` |
| EC-C-004 | Unknown `LLM_PROVIDER` | P0 | Fail at client init with supported list | `LLM_PROVIDER=foo` |
| EC-C-005 | `DATA_CACHE_PATH` points to non-writable dir | P0 | Clear error on ingestion | Read-only path |
| EC-C-006 | Relative vs absolute cache path | P1 | Resolve from project root consistently | Different cwd |

---

## 9. Security & Abuse (`EC-S`)

| ID | Scenario | Priority | Behavior | Test hint |
|----|----------|----------|----------|-----------|
| EC-S-001 | API key committed to git | P0 | `.gitignore` `.env`; document rotation | Grep repo |
| EC-S-002 | Oversized request body / preferences | P1 | Max length on text fields | 10k char location |
| EC-S-003 | Log files contain API keys | P0 | Never log full key; redact prompts in prod if sensitive | Inspect logs |
| EC-S-004 | Sending full 51k rows to LLM | P0 | Hard cap in filter + assert in prompt builder | Bypass attempt |

---

## 10. Decision Matrix: Filter Fallback Order

When multiple constraints conflict, apply relaxation in this order (only **one** automatic relaxation for milestone):

```text
1. Relax cuisine (if was specified)
2. If still zero → do NOT relax rating or budget automatically
3. Return empty state with hints
```

| User intent | Auto-relax? | User message |
|-------------|-------------|--------------|
| Strict cuisine eliminated all rows | Yes (cuisine) | “No exact cuisine match; showing other options in {location}.” |
| Strict rating + budget | No | “Try lowering minimum rating or changing budget.” |
| Unknown city | No | “Location not found. Try: {sample cities}.” |

---

## 11. Priority Summary for Milestone

### P0 checklist (must implement)

- [ ] EC-I-001, EC-I-007, EC-I-003
- [ ] EC-D-001, EC-D-003, EC-D-005, EC-D-007, EC-D-020, EC-D-023
- [ ] EC-V-001 through EC-V-006, EC-V-010, EC-V-016, EC-V-017
- [ ] EC-F-001 through EC-F-008, EC-F-002, EC-F-020, EC-F-022
- [ ] EC-P-001, EC-P-004, EC-P-006
- [ ] EC-L-001 through EC-L-005, EC-L-010 through EC-L-019, EC-L-021, EC-L-030, EC-L-031
- [ ] EC-O-001, EC-O-006, EC-O-007
- [ ] EC-U-001 through EC-U-008
- [ ] EC-S-001, EC-S-004

### P1 (should implement if time permits)

- Remaining EC-I, EC-D, EC-V, EC-F, EC-L, EC-U, EC-C rows marked P1

### P2 (document only / post-milestone)

- EC-I-009, EC-O-005, EC-L-033

---

## 12. Automated Test Mapping

| Test file | Edge case IDs to cover |
|-----------|------------------------|
| `tests/test_filter.py` | EC-F-001–008, EC-F-010–017, EC-F-020–022, EC-V-010–011 |
| `tests/test_prompt_builder.py` | EC-P-002–006, EC-S-004 |
| `tests/test_validation.py` | EC-L-010–021, EC-L-030–031, EC-O-006–007 |
| `tests/test_ingestion.py` (optional) | EC-D-003–009, EC-I-007 |
| Manual QA matrix (Phase 7) | EC-V-020, EC-F-003, EC-L-003, EC-U-006–008 |

### Sample manual QA scenarios

| # | Input | Expected outcome |
|---|--------|------------------|
| 1 | Bangalore, medium, Italian, rating 4.0 | ≤5 cards with explanations |
| 2 | Tokyo, medium, any | Empty state / city not found |
| 3 | Bangalore, low, rare cuisine, rating 4.9 | Zero or relaxed cuisine banner |
| 4 | Valid form, LLM offline | Error message, no crash |
| 5 | `min_rating=5`, popular city | Few or zero results; hints shown |
| 6 | Only 1 matching restaurant | Single card, rank 1 |

---

## 13. Logging & Metadata Conventions

For edge-case debugging, attach to `RecommendationResponse.metadata` where applicable:

```json
{
  "candidate_count": 12,
  "truncated": false,
  "relaxed_constraints": ["cuisine"],
  "dropped_llm_ids": 1,
  "cache_hit": true,
  "request_id": "uuid"
}
```

| Event | Log level | Fields |
|-------|-----------|--------|
| Hallucinated ID dropped | WARNING | `restaurant_id`, `request_id` |
| Filter returned 0 | INFO | `prefs_hash`, `location` |
| LLM retry | WARNING | `attempt`, `error` |
| Cache corrupt, re-ingesting | WARNING | `path` |

---

## 14. References

- [architecture.md](architecture.md) — §3.3 fallbacks, §6.4 guardrails, §7.3 empty states, §12 errors
- [implementation-plan.md](implementation-plan.md) — Phase 3 fallbacks, Phase 5 validation, Phase 7 manual matrix
- [context.md](../context.md) — success criteria
