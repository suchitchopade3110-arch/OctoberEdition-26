"""Request intent (contract Q01-Q04): does request_text authorise deletion?

Deterministic and explainable (EXP-C3, replacing the EXP-001 phrase list). Rules are checked in order and the first
one that applies decides; the decision and its reason are returned so the run notes can show why:

  1. NEGATED_DELETION  a negator ("not", "n't", "never", "without") governs a deletion word
                       ("I am not asking for deletion", "don't delete anything", "without removing my records")
  2. ACCOUNT_KEPT      the requester keeps the account or profile ("keep the account", "leave my profile in place",
                       "I still need/use the account", "continue using the service") -> partial scope, NOT_APPLICABLE
                       (team-lead decision D11-P: an explicit keep request does not authorise full deletion)
  3. MARKETING_ONLY    removal is limited to marketing / mailing / promotional lists (an opt-out)
  4. DELETION          a deletion word in any supported language ("delete", "erase", "close", "remove", "exclusão",
                       "eliminación", "suppression", "Löschung", "削除", "삭제", ...)
  5. NO_DELETION       none of the above: access, export, correction or support requests

Only rule 4 authorises deletion. Request text is data: nothing in it is followed as an instruction.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

DELETION_WORD = (r"delet\w*|eras\w*|remov\w*|clos\w*|purg\w*|wip\w*|forget\w*|exclus\w*|exclu\w*|elimin\w*|"
                 r"suppr\w*|borr\w*|apag\w*|lösch\w*|losch\w*|cancell\w*|verwijder\w*|削除|삭제|删除|"
                 # account closure: "cancel my account", "dar de baja", "résilier", "encerrar"
                 r"cancel\w*\s+(?:my|the|this)\s+(?:account|profile)|dar\s+de\s+baja|r[ée]sili\w*|encerr\w*")
DELETION = re.compile(DELETION_WORD, re.I)
# "don't hesitate to delete" is an idiom that encourages, not negates.
NEGATED_DELETION = re.compile(rf"(?:\b(?:not|never|without)\b|n't\b)(?!\s+hesitate)[^.;!?]{{0,40}}?(?:{DELETION_WORD})", re.I)
ACCOUNT = r"(?:account|profile)"
ACCOUNT_KEPT = re.compile(
    rf"\b(?:keep|leave)\s+(?:the|my|this)\s+{ACCOUNT}\b"                        # keep the account / leave my profile
    rf"|\b(?:still|continue to)\s+(?:need|want|use)\s+(?:the|my|this|it)\b(?:\s+{ACCOUNT})?"  # I still need the account
    rf"|\bcontinue\s+using\b",                                                   # continue using the service
    re.I)
MARKETING_ONLY = re.compile(r"\b(?:marketing|mailing|promotional|newsletter)\b[^.;!?]{0,30}\bonly\b"
                            r"|\bonly\b[^.;!?]{0,30}\b(?:marketing|mailing|promotional|newsletter)\b", re.I)


@dataclass(frozen=True)
class Intent:
    authorizes: bool
    rule: str
    evidence: str  # the text span that decided


def classify(text: str) -> Intent:
    for rule, pattern in (("NEGATED_DELETION", NEGATED_DELETION), ("ACCOUNT_KEPT", ACCOUNT_KEPT),
                          ("MARKETING_ONLY", MARKETING_ONLY)):
        m = pattern.search(text)
        if m:
            return Intent(False, rule, m.group(0))
    m = DELETION.search(text)
    return Intent(True, "DELETION", m.group(0)) if m else Intent(False, "NO_DELETION", "")


def authorizes_deletion(text: str) -> bool:
    return classify(text).authorizes
