# D48 — targeted D47 hardening

**OFFICIAL TARGETS: NOT YET VERIFIED.** Nothing here is an official score. Nothing was submitted.

## The two reported weaknesses

| # | Weakness (reported by the team lead) | Confirmed? | Fix | Proof |
|---|---|---|---|---|
| 1 | `main.py` checked `trace_problems` after it could already publish `output.csv` | Yes — the copy ran before the check, so `--best-effort` could publish an inconsistent run | The gate is evaluated before any publication, `--best-effort` included; exit 2; an existing `output.csv` is left untouched; `blocked_by_trace_gate` recorded | `test_entrypoint.TraceGateBlocksPublication` injects an inconsistency: **fails on the D47 `main.py`** (output overwritten), passes now |
| 2 | OCR cross-check compared a fact with whole-page text, so an id and an email from different rows could pass | Yes — on the real connector console (`evidence_14`) the D47 check **accepted** `data_flow_1121` paired with the next row's `lucia-torres@gmail.com` | Record-local corroboration: each printed occurrence of an id gets its own record context (detail header + cards / side panel under its title / table row without side-panel text). A fact holds only if one context shows all its identifiers and no context of that id shows another known person or an unknown person's email (ambiguous → review). OCR facts are built from the same contexts | D48 rejects the swapped pairing on the real screenshot; 7 new tests: two-person table, valid detail page, side panel, ambiguous context, glued row number, glued email, real screenshot |

Two detection bugs found while building fix 2 (they briefly produced two new COMPLETE claims, case_39 and case_50,
which were **not** accepted): OCR glued a row number to an id (`1data_flow_9846`), making a table cell look like a
panel title; and OCR joined `user_20 · analytics_7438 · email` with hyphens, so the email pattern swallowed the ids.
Both fixed generically (id-like tokens without word boundaries; known-identifier suffix of glued emails), after which
the output returned to byte-identical.

## Output impact

| | Accepted release | D47 candidate | D48 candidate |
|---|---|---|---|
| Commit | `4f61906` (tag `release-accepted`) | `09bcc92` | `d47-experiments` HEAD (see below) |
| output sha256 | `059df995…3246` | `e03e7a16…271b` | **`e03e7a16442b4547b9a99fc57f9c43d83bd8fa7cbe4ea04339e725c0782e271b`** (byte-identical to D47) |
| Rows differing from the release | — | case_34, case_53, case_421 | same three, unchanged |
| Status C / I / NA, steps | 160 / 348 / 10, 2,947 | 159 / 349 / 10, 2,955 | same as D47 |
| Strict validator | 3 R12, 8 R31 | same | same |
| Public samples (dev / reserved / all) | 1.0·0.950·0.591 / 0.80·0.830·0.40 / 0.9375·0.915·0.531 | identical | identical |

Neither correction changes case_34, case_53 or case_421: their facts are corroborated record-locally (header contexts
on evidence_04 and evidence_28 hold the subject's email; case_421 rests on a lineage event and a log line, not an image).

**Unsupported-association audit (518 cases):** every step that cites a screenshot (7 steps: case_33, 34, 35, 39, 50, 52,
53) has an identifier of that case's subject inside the cited resource's own record context. 0 exceptions.

## Verification

| Check | Result |
|---|---|
| `unittest discover -s code/tests` | 164 tests OK, 12 expected failures (pinned known defects) |
| `test_evaluator.py` / `custom_scenarios.py` | 33 OK / 5 of 5 |
| Clean room: unzip `code-d48.zip` + dataset, empty environment, OCR engine import blocked | output byte-identical (`e03e7a16…`), 11/11 OCR cache hits, 0 trace problems, 0 model calls, 164 tests OK |
| `code-d48.zip` | sha256 `9214dbcadcc4b875e467de20dfea53a8cd689dcc98b1cf6d88e4ca57cf13a0c2`, 68 entries, contains both evaluation reports, no dataset / keys / personal email |

## Release readiness

- Deadline: not verifiable from the container; a third-party listing implies 25 Oct 12:30 UTC. Engineering stopped
  well before it. Resubmission rules: unknown — check the form.
- Recommendation: if a resubmission is allowed, submit `code-d48.zip` + `output-d48.csv` (= D47 output) + the
  delivered `log.txt`. D48 strictly hardens D47 (safer publication, stricter grounding) with no prediction change.
  Otherwise keep the accepted release, which remains on tag `release-accepted`.
