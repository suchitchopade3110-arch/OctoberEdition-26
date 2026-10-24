# Usage report — Ghost Data Still Exists

Covers (A) the final full-dataset run that produces `output.csv` and (B) every model request made during
development. The figures come from the run notes and from the attempt ledger, which records each API request.
No figures are estimated unless marked.

## A. Final production run (518 cases)

| Item | Value |
|---|---|
| Command | `python code/main.py` |
| Model providers / models called | **none** |
| Model calls | **0** |
| Input / output tokens | 0 / 0 |
| Total and average tokens per request | 0 / 0 |
| Cost (total, per request) | $0.00 / $0.00 |
| Runtime / peak memory (measured 2026-10-25) | ≈2.6 s / ≈20 MB |

The final run reads screenshot facts from `code/evidence_cache/` instead of calling a model. That cache was made
during development (section B). So the **$0 above is the run cost, not the total cost of building the evidence**.
Without the cache (`--no-evidence-cache`) or on a cache miss, a screenshot adds no observation. Its resources stay
UNKNOWN; they are never treated as deleted.

## B. Development-time extraction (Google Gemini API)

Provider: Google Gemini Developer API (`google-genai` SDK 2.16.0). Requests went through the PRIMARY key slot only,
with SDK retries off. No key failover was ever triggered. **15 API requests in total: 14 image extraction attempts
(8 successful, 6 timed out) plus 1 metadata request (`models.get`).** These are the 15 lines of the attempt ledger.

| Model | Requests | Successful extractions | Failed (timeout) | Input tokens | Output tokens | Latency, total |
|---|---|---|---|---|---|---|
| gemini-3.8-flash | 9 | 3 | 6 (HTTP 504 DEADLINE_EXCEEDED) | 4,230 | 1,777 | 1,008.6 s |
| gemini-3.5-flash-lite | 6 (5 extractions + 1 `models.get`) | 5 | 0 | 6,936 | 2,309 | 45.7 s |
| **Total** | **15** (14 extractions + 1 metadata) | **8** | **6** | **11,166** | **4,086** | **1,054.3 s** |

Per-request detail (`runs/gemini_cache/attempt_ledger.jsonl`):

| # | Evidence | Model | Outcome | Latency s | In | Out |
|---|---|---|---|---|---|---|
| 1–3 | evidence_09 | 3.8-flash | 504 at the 45 s deadline (retried on the same key) | 45.9 / 44.8 / 44.6 | – | – |
| 4 | evidence_09 | 3.8-flash | 504 at the 180 s deadline | 181.1 | – | – |
| 5 | evidence_09 | 3.8-flash | success | 131.7 | 1,428 | 373 |
| 6 | evidence_14 | 3.8-flash | success | 60.5 | 1,402 | 732 |
| 7 | evidence_19 | 3.8-flash | 504 at 180 s | 180.2 | – | – |
| 8 | evidence_23 | 3.8-flash | success (compact request) | 138.7 | 1,400 | 672 |
| 9 | evidence_60 | 3.8-flash | 504 at 180 s | 181.2 | – | – |
| 10 | – | 3.5-flash-lite | `models.get` (metadata) | 0.9 | – | – |
| 11 | evidence_32 | 3.5-flash-lite | success | 5.9 | 1,374 | 846 |
| 12 | evidence_60 | 3.5-flash-lite | success | 4.3 | 1,400 | 206 |
| 13 | evidence_19 | 3.5-flash-lite | success | 18.6 | 1,374 | 186 |
| 14 | evidence_28 | 3.5-flash-lite | success (rejected by grounding, EXP-009) | 9.8 | 1,388 | 205 |
| 15 | evidence_42 | 3.5-flash-lite | success (rejected by grounding, EXP-009) | 6.1 | 1,400 | 866 |

Average over the 8 successful extractions: 1,396 input + 511 output = **1,907 tokens per image**.
Six of these extractions are in the shipped cache. The other two (rows 14–15) were rejected and are not shipped.

### Cost

Official paid-tier prices (Gemini Developer API pricing page, checked 2026-10-25; output includes thinking tokens):

| Model | Input / 1M | Output / 1M | Input cost | Output cost | Total |
|---|---|---|---|---|---|
| gemini-3.8-flash (introductory rate to 2026-12-31) | $0.75 | $3.75 | $0.00317 | $0.00666 | $0.00984 |
| gemini-3.5-flash-lite | $0.30 | $2.50 | $0.00208 | $0.00577 | $0.00785 |
| **Total (paid-tier rates)** | | | | | **$0.0177** |

Per extracted image (8): ≈ $0.0022. Per request of the 518-case run: $0 (no calls).

### Missing or uncertain usage information

- **Timed-out requests (6).** The API returned no usage, so no tokens are reported for them. Whether Google billed any
  tokens for them is **unknown**.
- **Thinking tokens.** `thoughts_token_count` was not returned (null) for any successful request. The output counts
  above are what the API reported.
- **Billing tier.** Both models also have a free tier. The cost above assumes paid-tier rates. Whether this project
  was billed is not visible from the API and has not been checked in the Google Cloud console.
- **Metadata request.** `models.get` returned no usage. Its billing status is unknown.
- **Latency.** The figures are wall-clock times measured by the client.
