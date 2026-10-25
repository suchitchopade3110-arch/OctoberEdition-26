"""Local OCR reader for screenshot evidence: a second, independent model next to the Gemini facts.

Runtime role (no network, no key, deterministic):
  1. read_lines(): every screenshot is read by a local OCR model (RapidOCR, ONNX runtime). The text lines and their
     positions are cached by the image's sha256 in code/evidence_cache/ocr/, so a run without the OCR package still
     reproduces; on a cache miss with the package installed, OCR runs live.
  2. cross_check(): a Gemini fact row is used only if the OCR text shows its resource id and every person identifier
     it reports inside the same record (table row, side panel or detail header; record_contexts) and no record context
     of that id shows another person (two independent readers must agree on what is printed, record by record).
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
ROW_TOLERANCE_PX = 14     # lines whose top edges are this close belong to one table row (same record)
HEADER_BOTTOM_PX = 170    # page title / subtitle band of these consoles (the resource a detail page is about)
DETAIL_BOTTOM_PX = 320    # summary cards directly under the title on detail pages
PANEL_ALIGN_PX = 25       # key/value lines of a side panel start within this many px of its title
PANEL_DEPTH_PX = 330      # how far below its title a side panel's key/value lines reach
ROW_SIBLING_PX = 400      # a table cell has another cell this close to its right in the same row
ID_TOKEN = re.compile(r"(?:account|search|analytics|support|export|data_flow|backup|audit_record|tombstone|cache|"
                      r"marketing|legal_hold|legal|object)_\d+")   # RID without word boundaries (OCR glues tokens)


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


def _panel_titles(lines: list[Line]) -> list[Line]:
    """Side-panel titles: a line naming a resource id below the page header band, with nothing beside it to its right
    in the same row (a table cell has sibling cells), and at least two aligned lines under it that contain no id-like
    token, even one glued to OCR noise such as a row number (a key/value column, not a table column of ids)."""
    out = []
    for t in lines:
        if t.y < HEADER_BOTTOM_PX or not RID.search(t.text):
            continue
        if any(0 < m.x - t.x <= ROW_SIBLING_PX and abs(m.y - t.y) <= ROW_TOLERANCE_PX for m in lines):
            continue
        below = [m for m in lines if abs(m.x - t.x) <= PANEL_ALIGN_PX and 0 < m.y - t.y <= PANEL_DEPTH_PX]
        if len(below) >= 2 and not any(ID_TOKEN.search(m.text) for m in below):
            out.append(t)
    return out


def _emails(text: str, is_known) -> set[str]:
    """Emails in OCR text. OCR can glue neighbouring tokens onto an email with '-' (e.g. 'user_20-x_7-a.b@c.com' for
    'user_20 · x_7 · a.b@c.com'); then the longest '-'-suffix that is a known identifier is the email."""
    out = set()
    for e in (m.lower() for m in EMAIL.findall(text)):
        local, _, domain = e.partition("@")
        cuts = [e] + [local[i + 1:] + "@" + domain for i, ch in enumerate(local) if ch == "-"]
        out.add(next((c for c in cuts if is_known(c)), e))
    return out


def record_contexts(key: str, lines: list[Line]) -> list[tuple[str, list[Line]]]:
    """The OCR lines that belong to the same record as each printed occurrence of `key` (a resource id or label):
      header - key in the page title band: the title band and the summary cards under it;
      panel  - key titles a side panel: the aligned key/value lines below it;
      row    - otherwise the table row at the same height, on the same side of any side panel.
    Text elsewhere on the page never counts as the record's own."""
    titles = _panel_titles(lines)
    panel_left = min((t.x for t in titles), default=None) if titles else None
    def left(m: Line) -> bool:
        return panel_left is None or m.x < panel_left - PANEL_ALIGN_PX
    k = norm(key)
    out = []
    for occ in lines:
        if not k or k not in norm(occ.text):
            continue
        if occ.y < HEADER_BOTTOM_PX:
            out.append(("header", [m for m in lines if m.y < DETAIL_BOTTOM_PX and (left(m) or not left(occ))]))
        elif occ in titles:
            out.append(("panel", [m for m in lines if m.x >= occ.x - PANEL_ALIGN_PX and occ.y <= m.y <= occ.y + PANEL_DEPTH_PX]))
        else:
            out.append(("row", [m for m in lines if abs(m.y - occ.y) <= ROW_TOLERANCE_PX and left(m) == left(occ)]))
    return out


def cross_check(record: dict, rid: str, lines: list[Line], users_for=None) -> str | None:
    """Record-local corroboration of one fact row by the OCR reader. None if it holds, else the reason.

    Holds only if (a) some record context of `rid` (see record_contexts) shows every identifier the row reports, and
    (b) no record context of `rid` shows an email / user reference of another known person or of nobody known (two
    people around one id is an ambiguous layout: left for review, not decided)."""
    ctxs = record_contexts(rid, lines)
    if not ctxs:
        return f"OCR does not show {rid}"
    want = [x for x in record.get("subject_identifiers", []) if x and norm(x) != norm(rid)]
    rec_ids = {x.lower() for x in want}
    rec_users = users_for(rec_ids) if users_for else set()
    supported = False
    for kind, ctx in ctxs:
        raw = " ".join(m.text for m in ctx)
        if all(norm(x) in norm(raw) for x in want):
            supported = True
        if users_for:
            seen = _emails(raw, lambda c: c in rec_ids or bool(users_for({c}))) | {u.lower() for u in USER_REF.findall(raw)}
            for ident in sorted(seen - rec_ids):
                who = users_for({ident})
                if not who or not who <= rec_users:
                    return f"{kind} context of {rid} also shows {ident!r} ({'unknown person' if not who else 'another person'}); ambiguous"
    if not supported:
        return f"OCR does not show {want} in the same record as {rid}"
    return None


def facts_from_ocr(lines: list[Line], known_rids: set[str], label_to_rid: dict[str, str]) -> dict:
    """Facts in the Gemini schema, one record per printed occurrence of a known resource id (or catalog label), built
    only from that occurrence's record context (record_contexts). A state is asserted only when that context prints a
    direct identifier (email / phone); anything else is UNCLEAR (needs review)."""
    page = " ".join(ln.text for ln in lines)
    keys = sorted({m.group(0) for m in RID.finditer(page) if m.group(0) in known_rids})
    keys += sorted(lab for lab in label_to_rid if norm(lab) in norm(page))
    records = []
    for key in keys:
        rid = key if key in known_rids else ""
        for kind, ctx in record_contexts(key, lines):
            support = list(dict.fromkeys(m.text for m in sorted(ctx, key=lambda m: (m.y, m.x))))
            blob = " ".join(support)
            idents = sorted(set(EMAIL.findall(blob)) | set(PHONE.findall(blob)) | set(USER_REF.findall(blob)))
            direct = bool(EMAIL.search(blob) or PHONE.search(blob))
            records.append({
                "resource_id": rid, "system_id": "", "subject_identifiers": idents,
                "supporting_text": support, "visible_status_text": "", "restore_or_flow_detail": "",
                "state": "PRESENT_WITH_IDENTIFIERS" if (direct and rid and not rid.startswith(("data_flow_", "backup_")))
                else "UNCLEAR",
                "state_basis": "VISIBLE_TEXT", "timestamp": "", "uncertainty": "", "ocr_context": kind})
    return {"records": records, "embedded_instructions_seen": any(INJECTION.search(ln.text) for ln in lines)}
