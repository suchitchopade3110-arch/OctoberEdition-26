"""Local OCR reader for screenshot evidence (EXP-D1): a second, independent model next to the Gemini facts.

Runtime role (no network, no key, deterministic):
  1. read_lines(): every screenshot is read by a local OCR model (RapidOCR, ONNX runtime). The text lines and their
     positions are cached by the image's sha256 in code/evidence_cache/ocr/, so a run without the OCR package still
     reproduces; on a cache miss with the package installed, OCR runs live.
  2. cross_check(): a Gemini fact row is used only if its resource id and every person identifier it reports are also
     present in the OCR text of the same image (two independent readers must agree on what is printed).
  3. facts_from_ocr(): for a screenshot with no Gemini facts, the OCR lines become facts in the same schema, which then
     pass the unchanged grounding guards in images.py. A row asserts a state only when a resource id known to the
     dataset AND a person's direct identifier (email / phone) are printed in the same row or detail header; everything
     else is left UNCLEAR (needs review). Absence of an identifier is never read as redaction.
Screenshot text is data: nothing in it is followed as an instruction.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .documents import RID

ENGINE = "rapidocr_onnxruntime"
SCHEMA = "ocr-lines-v1"
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE = re.compile(r"\+\d[\d ()-]{6,}\d")
USER_REF = re.compile(r"\buser_\d+\b")
# Text addressed to an assistant (not to a console user) quarantines the whole image, as for Gemini facts.
INJECTION = re.compile(r"ignore (all |any )?(previous|prior) instructions|system prompt|you are (an? )?(ai|assistant|model)|"
                       r"mark (this|the) (case|request) (as )?complete|disregard (the )?(rules|policy)", re.I)
ROW_TOLERANCE_PX = 14     # lines whose top edges are this close belong to one table row
HEADER_BOTTOM_PX = 170    # page title / subtitle band of these consoles (the resource a detail page is about)
DETAIL_BOTTOM_PX = 320    # summary cards directly under the title on detail pages


@dataclass(frozen=True)
class Line:
    text: str
    x: int
    y: int
    conf: float


def _engine():
    try:
        from rapidocr_onnxruntime import RapidOCR  # optional dependency (code/requirements.txt)
    except ImportError:
        return None
    return RapidOCR()


def engine_version() -> str | None:
    try:
        from importlib.metadata import version
        return f"{ENGINE}=={version('rapidocr_onnxruntime')}"
    except Exception:
        return None


def read_lines(image: Path, sha: str, cache_dir: Path | None, notes: list[str]) -> list[Line] | None:
    """OCR lines of one image: cached result first, live OCR on a miss when the engine is installed, else None."""
    cpath = cache_dir / f"{sha}.json" if cache_dir else None
    if cpath and cpath.exists():
        d = json.loads(cpath.read_text(encoding="utf-8"))
        if d.get("schema") == SCHEMA and d.get("source_sha256") == sha:
            notes.append(f"ocr: cache hit ({d.get('engine')})")
            return [Line(**ln) for ln in d["lines"]]
        notes.append("ocr: cache entry ignored (schema or source hash mismatch)")
    eng = _engine()
    if eng is None:
        notes.append("ocr: no cache entry and the OCR engine is not installed")
        return None
    result, _ = eng(str(image))
    lines = [Line(str(t), int(b[0][0]), int(b[0][1]), round(float(c), 4)) for b, t, c in (result or [])]
    notes.append(f"ocr: ran {engine_version()} live ({len(lines)} lines)")
    if cpath:
        cpath.parent.mkdir(parents=True, exist_ok=True)
        cpath.write_text(json.dumps({"schema": SCHEMA, "source_sha256": sha, "engine": engine_version(),
                                     "lines": [vars(ln) for ln in lines]}, ensure_ascii=False, indent=1),
                         encoding="utf-8")
    return lines


def norm(s: str) -> str:
    """Comparison form: OCR drops spaces and reads separators differently, so compare without them."""
    return re.sub(r"[\s·•|:,\-–—()]+", "", s.lower())


def cross_check(record: dict, rid: str, lines: list[Line]) -> str | None:
    """None if the OCR text contains the fact row's resource id and every identifier it reports; else the reason."""
    page = norm(" ".join(ln.text for ln in lines))
    missing = [x for x in [rid, *record.get("subject_identifiers", [])] if x and norm(x) not in page]
    return f"OCR does not show {missing}" if missing else None


def _rows(lines: list[Line]) -> list[list[Line]]:
    rows: list[list[Line]] = []
    for ln in sorted(lines, key=lambda l: (l.y, l.x)):
        if rows and abs(ln.y - rows[-1][0].y) <= ROW_TOLERANCE_PX:
            rows[-1].append(ln)
        else:
            rows.append([ln])
    return [sorted(r, key=lambda l: l.x) for r in rows]


def facts_from_ocr(lines: list[Line], known_rids: set[str], label_to_rid: dict[str, str]) -> dict:
    """Facts in the Gemini schema (records with resource_id, subject_identifiers, supporting_text, state, ...)."""
    records = []
    detail_text = [ln.text for ln in lines if ln.y < DETAIL_BOTTOM_PX]
    for row in _rows(lines):
        text = [ln.text for ln in row]
        joined = " ".join(text)
        rids = sorted({m.group(0) for m in RID.finditer(joined) if m.group(0) in known_rids})
        labels = sorted({lab for lab in label_to_rid if lab in joined})
        if not rids and not labels:
            continue
        in_header = row[0].y < HEADER_BOTTOM_PX
        support = list(dict.fromkeys(text + (detail_text if in_header else [])))
        blob = " ".join(support)
        idents = sorted(set(EMAIL.findall(blob)) | set(PHONE.findall(blob)) | set(USER_REF.findall(blob)))
        direct = bool(EMAIL.search(blob) or PHONE.search(blob))
        for rid in rids or [""]:
            records.append({
                "resource_id": rid, "system_id": "", "subject_identifiers": idents,
                "supporting_text": support, "visible_status_text": "", "restore_or_flow_detail": "",
                # Only printed direct identifiers establish a state; anything else needs review.
                "state": "PRESENT_WITH_IDENTIFIERS" if (direct and rid and not rid.startswith(("data_flow_", "backup_")))
                else "UNCLEAR",
                "state_basis": "VISIBLE_TEXT", "timestamp": "", "uncertainty": "",
                "ocr_rows": "header+detail" if in_header else "row"})
    return {"records": records, "embedded_instructions_seen": any(INJECTION.search(ln.text) for ln in lines)}
