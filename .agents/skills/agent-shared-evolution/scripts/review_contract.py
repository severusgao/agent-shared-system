"""Shared identities for reviewed evidence and version-bound proposals."""
from __future__ import annotations

import hashlib
import json
import re

UPDATE_KINDS = {"add", "supplement", "correct", "replace", "retract"}
KNOWLEDGE_STATES = {"confirmed", "observed", "inferred", "decision"}


def proposal_digest(candidate: dict) -> str:
    """Bind approval to the complete candidate, including its baseline and revision."""
    payload = {k: v for k, v in candidate.items() if k not in {"proposal_digest", "status"}}
    content = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def validate_revision(candidate: dict) -> None:
    revision = candidate.get("proposal_revision")
    digest = candidate.get("proposal_digest")
    if revision is not None and (type(revision) is not int or revision < 1):
        raise ValueError("proposal_revision must be a positive integer")
    if digest is not None:
        if revision is None or not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
            raise ValueError("proposal_digest requires an explicit revision and SHA-256")
        if digest != proposal_digest(candidate):
            raise ValueError("proposal content changed; refresh revision/digest and approval")


def validate_memory_update(candidate: dict) -> None:
    """Optional for legacy records; inspect only fields needed by the actual update."""
    update = candidate.get("memory_update")
    if update is None:
        return
    if candidate.get("owner") != "memories" or not isinstance(update, dict):
        raise ValueError("memory_update belongs to a memory candidate")
    if update.get("operation") not in UPDATE_KINDS:
        raise ValueError("invalid memory update operation")
    if update.get("knowledge_status") not in KNOWLEDGE_STATES:
        raise ValueError("distinguish confirmed, observed, inferred and decision")
    for key in ("target_refs", "basis_refs"):
        if not isinstance(update.get(key), list) or not update[key]:
            raise ValueError("memory update requires " + key)
    for key in ("target_refs", "basis_refs", "affected_refs", "conditions",
                "independent_event_refs", "counterevidence_refs"):
        if key in update and (not isinstance(update[key], list)
                              or any(not isinstance(v, str) or not v.strip() for v in update[key])):
            raise ValueError("invalid memory update references: " + key)


def evidence_identity(row: dict) -> tuple:
    """Copies of the same original event are one event, regardless of review batch."""
    if row.get("origin_ref"):
        return ("origin", row["origin_ref"])
    return ("event", *(row.get(k) for k in
                       ("environment_id", "agent", "profile", "session_id", "event_id")))
