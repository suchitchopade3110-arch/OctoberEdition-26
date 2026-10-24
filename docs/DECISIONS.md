# Decisions

Team lead decides; this file records what was decided, what was rejected, and the evidence.
Entries D1–D6 were approved by the team lead on 2026-10-24 (approval text in `log.txt`, same date). Quotes are the lead's words.
Rule IDs refer to `docs/contract.md`.

---

## Contract clarifications from the team lead (2026-10-24, after Step 2)
- **A4:** samples show INCOMPLETE cases verify already-compliant accounts and retained security records → contract R33 (V). Verifying *every* other already-compliant resource stays unresolved → R34 (U).
- **Ordering:** keep the exact official operation order (R16). Numeric case ordering is a validated interpretation, not a universal rule → R04 (V); validator only errors when rows follow neither numeric nor plain-text order.

## D1: Deterministic core, bounded AI at the edges
- **Chose:** Architecture A. Parsing, identity linking, time filtering, policy and step planning are plain Python. AI is used only "when deterministic extraction cannot reliably resolve request intent, ambiguous data categories, or multimodal evidence", and every AI result is cached.
- **Rejected:** Architecture B (an AI investigator loop per case). Estimated 4–8M tokens per full run against well under 0.2M for A; results would vary between runs; and the model would be deciding things the spec defines exactly (ordering, status rules).
- **Evidence:** 499/518 test cases have exactly one text evidence file mentioning the subject before `audit_at`; evidence is structured (SQL, JSON, key=value logs, a pipe table). The 32 official answers follow fixed rule → step mappings (validator: 0 warnings on R30/R31).
- **Lives in:** to be built (`code/`); guarded by `code/evaluation/validate_output.py`.
- **Still unsure:** how far the hidden set departs from the visible formats.

## D2: Cite the evidence that establishes each resource's state
- **Chose:** per-resource citation (C02). Evidence must be valid at `audit_at` (C03, inclusive per T02). Absence needs authoritative evidence: an explicit negative readback, or a snapshot whose scope covers that system and was captured after the last write (C06). An omitted record in a partial snapshot is not enough.
- **Safeguard from the lead:** "Do not assume exactly one evidence file per case."
- **Rejected:** "one file per case" shortcut (case_04 cites two files).
- **Evidence:** cases 01/02 (absence from a primary+failover snapshot), case_31 (empty `customer_profiles` collection), case_03 (`rows=0 http_status=404` readback), case_04 (two files).
- **Still unsure:** what the grader expects when absence can't be proven (C07).

## D3: Deterministic categories, constrained AI fallback
- **Chose:** category comes from evidence content (explicit label, collection/table, record fields). The AI fallback may only pick one of the 15 `deletion_rules.csv` categories and must quote the supporting evidence. The policy engine, not the model, maps category → action (contract §6).
- **Evidence:** case_12 — an `analytics_platform` record that is a marketing contact (`email_opt_in=true`) is deleted, not anonymized (P18). So category can't be read from `system_id` alone.

## D4: 22 development cases, 10 reserved evaluation cases
- **Chose:** split in `code/evaluation/splits.py`. Reserved: 04, 09, 10, 15, 19, 24, 26, 30, 31, 32.
- **Modification from the lead:** include a complex 14-step multi-system case → case_30 added (replaces case_22, which returns to dev).
- **Wording:** this is a *reserved evaluation set*, not a blind holdout — all samples were inspected during kickoff. "Do not optimize against the reserved set during development." Enforced: `eval.py` refuses `--split reserved` without `--allow-reserved`.
- **Also required:** at least three independent evaluation scenarios we build ourselves (planned in `docs/EXPERIMENTS.md`).

## D5: Contract built from the earlier draft, re-verified
- **Chose:** started from the earlier `docs/contract.md` draft, verified each rule against `problem_statement.md`, `AGENTS.md` and `README.md`, and tagged every rule E (explicit), V (validated by samples) or U (unresolved).
- **Changes vs the draft:** drift reporting decided (C08, from case_05); absence thresholds added (C06, from D2); policy pairs checked against all 32 answers by the validator; open items listed in contract §10.

## D6: `.gitignore` before the first commit
- **Chose:** ignore `.env*` (except `.env.example`), venvs, `__pycache__`/compiled files, `spike/`, `cache/`, `runs/`, `code.zip`, `agent-trace*`.
- **Kept tracked:** `log.txt` — the required transcript. Append-only; earlier entries are never changed.

## D7: Model provider — PROVISIONALLY APPROVED (2026-10-24)
- **Lead's condition:** `claude-haiku-5-5` "for later bounded AI experiments, subject to checking API availability and measuring actual quality and token costs. Do not make paid API calls yet."
- **Status:** no API calls made. EXP-001 needs none.
- **Finding:** no API credential for our solution exists in this environment. The only provider-related variables belong to the Claude Code harness itself (`ANTHROPIC_BASE_URL`, `CLAUDE_CODE_*`), which the solution must not reuse. `anthropic` and `openai` Python SDKs are installed.
- **Recommendation:** Anthropic, `claude-haiku-5-5` ($0.10 input / $0.50 output per 1M tokens, Anthropic list price as of 2026-10-06; lowest-cost current model). Image/PDF input support for this model is to be confirmed with the Models API (`capabilities`) before integration — not yet checked. Escalate a single item to `claude-sonnet-5-5` ($2 / $10) only if Haiku's measured accuracy on our labelled items is not good enough.
- **Rough size (estimate, not measured):** ~375 intent texts + 15 image/PDF extractions ≈ 0.2–0.3M input tokens, cached after the first run → about $0.05 or less per uncached full run.
- **Needs from the lead:** approve the model, and put an `ANTHROPIC_API_KEY` in an uncommitted `.env` (or log in with `ant auth login`). Until then the pipeline runs on its deterministic fallback only.
- **Will record when measured:** exact model, call counts, input/output tokens, cost → `code/evaluation/usage_report.md`.
