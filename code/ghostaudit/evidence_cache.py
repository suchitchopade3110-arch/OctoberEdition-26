"""Content-addressed cache of structured facts extracted from evidence images.

Layout: <cache_dir>/<source sha256>/<model>__<prompt_version>.json, plus index.json listing every entry with the
sha256 of the entry file itself. An entry is found by the SHA-256 of the evidence file's current bytes, so a
renamed file still hits and a changed file misses. Each entry records the evidence id, path, origin and capture
time it was made from, the model and prompt/schema version, usage, and the extracted facts.

On a miss the image simply contributes no observation (its resources stay UNKNOWN); a miss is never read as
absence. Live extraction (gemini.py) is opt-in and writes new entries here.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ENTRY_FIELDS = ("file_id", "file_path", "origin", "captured_at", "sha256", "model", "model_version", "prompt_version",
                "usage", "latency_s", "schema_errors", "facts", "raw_text")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def entry_path(cache_dir: Path, sha: str, model: str, prompt_version: str) -> Path:
    return cache_dir / sha / f"{model}__{prompt_version}.json"


def write_entry(cache_dir: Path, entry: dict) -> Path:
    """Store a validated extraction. Only ENTRY_FIELDS are kept (no attempt logs, never any credential)."""
    clean = {k: entry.get(k) for k in ENTRY_FIELDS}
    p = entry_path(cache_dir, clean["sha256"], clean["model"], clean["prompt_version"])
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(clean, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    rebuild_index(cache_dir)
    return p


def rebuild_index(cache_dir: Path) -> None:
    rows = []
    for p in sorted(cache_dir.glob("*/*.json")):
        e = json.loads(p.read_text(encoding="utf-8"))
        rows.append({"entry": p.relative_to(cache_dir).as_posix(), "entry_sha256": sha256_file(p),
                     "source_sha256": e["sha256"], "file_id": e["file_id"], "model": e["model"],
                     "prompt_version": e["prompt_version"]})
    (cache_dir / "index.json").write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")


def lookup(cache_dir: Path, sha: str) -> tuple[dict | None, list[str]]:
    """Return (chosen entry, notes) for an evidence file's sha256. Entries with schema errors or no facts are
    skipped. If several valid entries exist, the choice is deterministic: highest (prompt_version, model)."""
    d = cache_dir / sha
    notes: list[str] = []
    if not d.is_dir():
        return None, ["cache miss"]
    valid = []
    for p in sorted(d.glob("*.json")):
        e = json.loads(p.read_text(encoding="utf-8"))
        if e.get("sha256") != sha:
            notes.append(f"{p.name}: entry hash does not match its folder; ignored")
        elif e.get("schema_errors") or not e.get("facts"):
            notes.append(f"{p.name}: no valid facts; ignored")
        else:
            valid.append(e)
    if not valid:
        return None, notes + ["no valid entry"]
    valid.sort(key=lambda e: (e["prompt_version"], e["model"]))
    if len(valid) > 1:
        notes.append(f"{len(valid)} valid entries; using {valid[-1]['model']} / {valid[-1]['prompt_version']}")
    return valid[-1], notes


def verify_index(cache_dir: Path) -> list[str]:
    """Integrity check: every indexed entry exists and is byte-identical to what was indexed."""
    problems = []
    idx = cache_dir / "index.json"
    if not idx.exists():
        return ["index.json missing"]
    for row in json.loads(idx.read_text(encoding="utf-8")):
        p = cache_dir / row["entry"]
        if not p.exists():
            problems.append(f"missing {row['entry']}")
        elif sha256_file(p) != row["entry_sha256"]:
            problems.append(f"modified {row['entry']}")
    return problems
