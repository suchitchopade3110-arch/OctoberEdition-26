"""PDF evidence extraction (offline, pypdf): text facts and resource links from business documents.

A resource is referenced by a document only if its id is printed, or a printed label is mapped to it by a
LINK_RESOURCE_IDENTITY catalog row. A document naming more than one subject is never used for linking.
"""
from __future__ import annotations

import re
from pathlib import Path

from . import evidence as ev

RID = re.compile(r"\b(account|search|analytics|support|export|data_flow|backup|audit_record|tombstone|cache|marketing|legal_hold|legal|object)_\d+\b")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")  # domain never ends with a dot (sentence-final emails)
USER = re.compile(r"\buser_\d+\b")
PHONE = re.compile(r"\+\d[\d ]{7,}\d")
CATALOG = re.compile(r"linked (\S+) \(([^)]+)\) to", re.I)
FILE_HINT = re.compile(r"\bfile [\w.-]+\.(pdf|png|jpg|zip|csv)\b|\buploader\b|\battachment\b", re.I)


def document_observations(text: str, origin: str, label_to_rid: dict[str, str], rid_target: dict[str, str],
                          known_systems: set[str], users_for) -> tuple[dict, list[tuple[str, dict, str | None, set[str], str]]]:
    """Pure extraction step (unit-tested): returns (coverage record, [(rid, record, system hint, keys, linked_via)])."""
    low = text.lower()
    keys = {k.lower() for k in EMAIL.findall(text)} | set(USER.findall(low)) | {ev.norm(p) for p in PHONE.findall(text)}
    users = users_for(keys)
    refs = {m.group(0) for m in RID.finditer(text)}
    via_label = {label_to_rid[l] for l in label_to_rid if l in text}
    record = {"resource_ids_printed": sorted(refs), "resource_ids_via_catalog_label": sorted(via_label), "subjects": sorted(users)}
    if len(users) > 1:
        record["skipped"] = "document names more than one subject; not used for linking"
        return record, []
    if not (refs | via_label):
        record["skipped"] = "no resource id or catalog-mapped label in the document"
        return record, []
    out = []
    for rid in sorted(refs | via_label):
        rec = {"resource_id": rid}
        emails = EMAIL.findall(text)
        if emails:
            rec["email"] = emails[0].lower()
        if FILE_HINT.search(text):
            rec["file"] = "document attachment"
        hint = origin if origin in known_systems else rid_target.get(rid)
        out.append((rid, rec, hint, keys | {rid}, "printed id" if rid in refs else "catalog label"))
    return record, out


def pdf_text(path: Path) -> str:
    import pypdf
    return "\n".join((p.extract_text() or "") for p in pypdf.PdfReader(path).pages)
