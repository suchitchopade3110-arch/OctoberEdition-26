"""Auditor with multimodal evidence (EXP-007 PDFs + EXP-007G image facts; D14, D16, D17, D18).

The identity, temporal and policy engines are the unchanged Auditor's. This class only adds observations:
  * PDFs: text extracted offline with pypdf (documents.py);
  * images: structured facts read from the content-addressed evidence cache (evidence_cache.py) and grounded by
    images.py. No model is called here. A cache miss adds nothing, so those resources stay UNKNOWN.
Every added observation keeps its evidence id, manifest capture time and an `extraction` provenance tag.
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from . import evidence_cache, ocr
from .auditor import Auditor
from .documents import CATALOG, EMAIL, USER, document_observations, pdf_text
from .images import flow_state_from_text, ground_record, link_rows, usable_state

DEFAULT_OCR_DIR = Path(__file__).resolve().parents[1] / "evidence_cache" / "ocr"


class MultimodalAuditor(Auditor):
    def __init__(self, data_dir: Path, cache_dir: Path | None, use_ocr: bool = True, ocr_dir: Path | None = None):
        self.cache_dir = cache_dir
        # Local OCR second reader. Off when image evidence is disabled (cache_dir=None) or use_ocr=False. Its line
        # cache is shipped in code/evidence_cache/ocr/ and is independent of which fact cache is used.
        self.use_ocr = bool(use_ocr and cache_dir is not None)
        self.ocr_dir = (ocr_dir or DEFAULT_OCR_DIR) if self.use_ocr else None
        super().__init__(data_dir)
        self.extraction: list[dict] = []
        self.image_report: list[dict] = []
        self._extract_pdfs()
        self._ingest_images()

    # ---------------------------------------------------------------- shared helpers
    def _catalog(self) -> tuple[dict[str, str], dict[str, str]]:
        label_to_rid, rid_target = {}, {}
        for a in self.links:
            m = CATALOG.search(a["details"])
            if not m:
                continue
            rid, label = m.group(1), m.group(2)
            rid_target[rid] = a["target_system"]
            # A person identifier (user id, email) is not a reference to a resource.
            if label != rid and not USER.fullmatch(label.lower()) and not EMAIL.fullmatch(label):
                label_to_rid[label] = rid
        return label_to_rid, rid_target

    def _users_for(self, keys: set[str]) -> set[str]:
        k2u = defaultdict(set)
        for u, ks in self.keys.items():
            for k in ks:
                k2u[k].add(u)
        return set().union(*(k2u.get(k, set()) for k in keys)) if keys else set()

    # ---------------------------------------------------------------- PDFs
    def _extract_pdfs(self) -> None:
        label_to_rid, rid_target = self._catalog()
        for e in self.evidence:
            if not e["file_path"].lower().endswith(".pdf"):
                continue
            text = pdf_text(self.data_dir / e["file_path"])
            found, obs = document_observations(text, e["origin"], label_to_rid, rid_target, self.known_systems, self._users_for)
            record = {"file_id": e["file_id"], "file": Path(e["file_path"]).name, "captured_at": e["captured_at"],
                      "chars": len(text), **found, "observations": []}
            for rid, rec, hint, keys, via in obs:
                before = len(self.idx.obs)
                self.idx.add(e["file_id"], e["captured_at"], rec, system=hint, extra_keys=keys)
                for o in self.idx.obs[before:]:
                    o.extraction = "pdf-text"
                    self.obs_by_res[o.resource_id].append(o)
                    record["observations"].append({"resource_id": o.resource_id, "system": o.system, "state": o.state,
                                                   "category": o.category, "linked_via": via})
            self.extraction.append(record)

    # ---------------------------------------------------------------- images
    def _ingest_images(self) -> None:
        label_to_rid, rid_target = self._catalog()
        known_rids = set(self.obs_by_res) | set(rid_target)
        for e in self.evidence:
            if not e["file_path"].lower().endswith((".png", ".jpg", ".jpeg")):
                continue
            sha = evidence_cache.sha256_file(self.data_dir / e["file_path"])
            c, notes = evidence_cache.lookup(self.cache_dir, sha) if self.cache_dir else (None, ["no cache configured"])
            rep = {"file_id": e["file_id"], "sha256": sha, "cache": notes, "used": [], "rejected": [], "review": []}
            self.image_report.append(rep)
            lines = None
            if self.use_ocr:
                rep["ocr"] = []
                lines = ocr.read_lines(self.data_dir / e["file_path"], sha, self.ocr_dir, rep["ocr"])
            if c is not None:
                rep.update(model=c["model"], prompt_version=c["prompt_version"])
                if c["file_id"] != e["file_id"]:
                    rep["cache"].append(f"entry was made for {c['file_id']}; same bytes, reused for {e['file_id']}")
                f, source = c["facts"], f"image:{c['model']}:{c['prompt_version']}"
            elif lines:
                f, source = ocr.facts_from_ocr(lines, known_rids, label_to_rid), f"image:ocr:{ocr.SCHEMA}"
                rep.update(model=ocr.ENGINE, prompt_version=ocr.SCHEMA)
            else:
                rep["status"] = "unresolved: no extraction available (resources stay UNKNOWN)"
                continue
            if f.get("embedded_instructions_seen"):
                rep["review"].append("image contains embedded instructions; quarantined")
                continue
            mode, rows = link_rows(f["records"], self._users_for)
            rep["linking"] = mode
            for row_no, (r, users, why_link) in enumerate(rows, 1):
                rid, how = ground_record(r, known_rids, label_to_rid)
                if not rid:
                    rep["rejected"].append(f"row {row_no}: {how}")
                    continue
                if (mode == "per_row" and not users) or why_link.startswith("unresolved"):
                    rep["review"].append(f"row {row_no} {rid}: {why_link}")
                    continue
                if c is not None and lines is not None:
                    disagree = ocr.cross_check(r, rid, lines, self._users_for)
                    if disagree:  # the two independent readers must agree on what is printed
                        rep["review"].append(f"row {row_no} {rid}: {disagree}")
                        continue
                fields, why = flow_state_from_text(r) if rid.startswith("data_flow_") else usable_state(r, rid)
                if not fields:
                    rep["review"].append(f"row {row_no} {rid}: {why}")
                    continue
                sys_printed = r.get("system_id") or None
                hint = e["origin"] if e["origin"] in self.known_systems else (
                    sys_printed if sys_printed in self.known_systems else rid_target.get(rid))
                # Keys: only this row's own identifiers (+ its resource id); never a neighbour's.
                keys = {x.lower() for x in r.get("subject_identifiers", [])} | {rid}
                before = len(self.idx.obs)
                self.idx.add(e["file_id"], e["captured_at"], {"resource_id": rid, **fields}, system=hint, extra_keys=keys)
                for o in self.idx.obs[before:]:
                    o.extraction = f"{source}:row{row_no}"
                    self.obs_by_res[o.resource_id].append(o)
                    rep["used"].append({"row": row_no, "resource_id": rid, "system": o.system, "state": o.state,
                                        "linked_via": how, "person_link": why_link, "users": sorted(users),
                                        "state_reason": why or r["state_basis"]})
