"""Request intent (contract Q01-Q04): accepted baseline keyword rule (EXP-001).

EXP-005 (clause-level classifier) was REJECTED for production integration by the team lead; this module
deliberately keeps the accepted rule, including its known limits (trap T06: e.g. "remaining copy of"
is read as an access request; see docs/TRAP_FINDINGS.md and code/tests/fixtures/audit_repro_cases.json).
"""
from __future__ import annotations

import re

NON_DELETION = re.compile(r"not (asking|a request) (for|to) (deletion|erase|delete)|do not (close|delete)|don't delete|"
                          r"marketing lists only|stop the promotional|keep the account|leave (my|the) (profile|account)|"
                          r"copy of|download my|change the email|replace it|misspelled|resetting the login|what personal information", re.I)
DELETION = re.compile(r"delet|eras|remov|close|clos|exclus|elimin|suppress|削除|삭제|apag|borr|forget", re.I)


def authorizes_deletion(text: str) -> bool:
    if NON_DELETION.search(text):
        return False
    return bool(DELETION.search(text))
