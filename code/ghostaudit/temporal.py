"""State of a resource at audit_at (accepted EXP-004 rules, D10).

Three times are kept apart: observation time (log line or record time, else file capture),
availability time (file captured_at) and the case cutoff (audit_at).
State = latest reliable observation time among evidence available at audit_at; line order is never
chronology. D10-A: equal-time conflicts are marked ambiguous with full provenance; preference only for
comparable scope/authority; replica copies never merged (C08: a remaining copy means the record exists).
D10-B: rows dated after their own file's capture are quarantined (kept, flagged, never selected).
"""
from __future__ import annotations

NON_COMPLIANCE = {"PRESENT_ID": 0, "PRESENT": 1, "FLOW_ACTIVE": 0, "RESTORE_OPEN": 0,
                  "PRESENT_CLEAN": 2, "FLOW_DISABLED": 3, "RESTORE_BLOCKED": 3, "ABSENT": 4}
PRESENT_STATES = {"PRESENT_ID", "PRESENT", "PRESENT_CLEAN"}


def obs_time(o) -> tuple[str, str]:
    """(observation time, source of that time). A time later than the file's capture is 'post-dated'."""
    t, src = getattr(o, "observed_at", None), "line"
    if not t:
        t, src = getattr(o, "record_time", None), "record"
    if not t:
        return o.captured_at, "capture"
    if t > o.captured_at:
        return t, "post-dated"
    return t, src


def scope_of(o) -> str:
    """Copy/scope an observation describes: the SQL table when known, else its logical system."""
    return getattr(o, "scope", None) or o.system


def choose(obs: list, audit_at: str) -> tuple[object | None, dict]:
    """Pick the observation that defines state at audit_at. Returns (None, info) when nothing is usable."""
    in_time = [o for o in obs if o.captured_at <= audit_at and obs_time(o)[0] <= audit_at]
    post = [o for o in obs if o.captured_at <= audit_at and obs_time(o)[1] == "post-dated"]
    usable = [o for o in in_time if obs_time(o)[1] != "post-dated"]
    info: dict = {"usable": len(usable), "excluded_after_cutoff": len([o for o in obs if o.captured_at > audit_at])}
    if post:
        info["post_dated_ignored"] = [{"file_id": o.file_id, "at": obs_time(o)[0], "state": o.state} for o in post]
    if not usable:
        return None, info
    timeline = sorted(usable, key=lambda o: (obs_time(o)[0], o.file_id, getattr(o, "line", 0) or 0))
    seen_absent = False
    for o in timeline:
        if o.state == "ABSENT":
            seen_absent = True
        elif seen_absent and o.state in PRESENT_STATES:
            info["reappeared"] = {"file_id": o.file_id, "at": obs_time(o)[0]}
            break
    t_max = obs_time(timeline[-1])[0]
    top = [o for o in timeline if obs_time(o)[0] == t_max]
    states = {o.state for o in top}
    if len(states) == 1:
        return max(top, key=lambda o: (o.file_id, getattr(o, "line", 0) or 0)), info
    info["ambiguous"] = True
    info["tied_observations"] = [{"file_id": o.file_id, "line": getattr(o, "line", None), "scope": scope_of(o),
                                  "system": o.system, "state": o.state, "at": t_max} for o in top]
    files = {o.file_id for o in top}
    scopes = {scope_of(o) for o in top}
    if len(files) == 1 and len(scopes) > 1:
        present = [o for o in top if o.state != "ABSENT"]
        info["tie"] = "same snapshot, different copies: a remaining copy means the record exists (C08)"
        chosen = min(present or top, key=lambda o: (NON_COMPLIANCE.get(o.state, 9), o.file_id))
        info["preference_applied"] = True
    elif len(scopes) == 1 and len({o.system for o in top}) == 1:
        info["tie"] = "comparable sources: least-compliant state preferred (not proof)"
        chosen = min(top, key=lambda o: (NON_COMPLIANCE.get(o.state, 9), o.file_id))
        info["preference_applied"] = True
    else:
        info["tie"] = "incomparable scope or authority: no preference applied"
        chosen = max(top, key=lambda o: (o.file_id, getattr(o, "line", 0) or 0))
        info["preference_applied"] = False
    info["tie_states"] = sorted(states)
    return chosen, info
