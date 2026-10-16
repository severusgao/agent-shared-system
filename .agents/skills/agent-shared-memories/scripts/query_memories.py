#!/usr/bin/env python3
"""Read-only navigation over formal memory and reviewed AgentEvolution records."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import unicodedata

# Querying must not create interpreter caches in the shared tree.
sys.dont_write_bytecode = True
from lint_memories import REQUIRED_FILES
from resolve_memories_root import resolve

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "agent-shared-evolution" / "scripts"))
from review_contract import evidence_identity, validate_revision


def normalized(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold()


def timestamp(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("time filters require an explicit timezone")
    return result.astimezone(timezone.utc)


def read_text(path: Path, boundary: Path, warnings: list[str]) -> str | None:
    if not path.resolve().is_relative_to(boundary.resolve()):
        warnings.append(f"Skipped path outside selected root: {path}")
        return None
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        warnings.append(f"Cannot read {path}: {exc}")
        return None


def read_json(path: Path, boundary: Path, warnings: list[str]) -> dict | None:
    text = read_text(path, boundary, warnings)
    if text is None:
        return None
    try:
        value = json.loads(text)
        if not isinstance(value, dict):
            raise ValueError("expected a JSON object")
        return value
    except (ValueError, TypeError) as exc:
        warnings.append(f"Invalid JSON {path}: {exc}")
        return None


def json_rows(path: Path, boundary: Path, warnings: list[str]) -> list[tuple[int, dict]]:
    text = read_text(path, boundary, warnings)
    rows = []
    for line, value in enumerate((text or "").splitlines(), 1):
        if not value.strip():
            continue
        try:
            row = json.loads(value)
            if not isinstance(row, dict) or row.get("schema_version") != 1:
                raise ValueError("expected a schema 1 record")
            rows.append((line, row))
        except (ValueError, TypeError) as exc:
            warnings.append(f"Unsupported record {path}:{line}: {exc}")
    return rows


def markdown_sections(text: str) -> list[tuple[str, int, int, str]]:
    """Return complete heading sections, never split individual condition clauses."""
    lines = text.splitlines()
    start = 0
    if lines and lines[0] == "---":
        end = next((i for i in range(1, len(lines)) if lines[i] == "---"), None)
        if end is None:
            raise ValueError("unclosed frontmatter")
        start = end + 1
    sections, heading, begin, in_code = [], "Introduction", start, False
    for i in range(start, len(lines)):
        if re.match(r"^\s*(```|~~~)", lines[i]):
            in_code = not in_code
        match = re.match(r"^#{1,2}\s+(.+?)\s*#*\s*$", lines[i]) if not in_code else None
        if match:
            if i > begin and any(v.strip() for v in lines[begin:i]):
                sections.append((heading, begin + 1, i, "\n".join(lines[begin:i])))
            heading, begin = match.group(1), i
    if begin < len(lines) and any(v.strip() for v in lines[begin:]):
        sections.append((heading, begin + 1, len(lines), "\n".join(lines[begin:])))
    return sections


def formal_records(root: Path, warnings: list[str]) -> list[dict]:
    records = []
    for name in REQUIRED_FILES:
        path = root / name
        text = read_text(path, root, warnings)
        if text is None:
            continue
        updated = re.search(r"^updated:\s*(\d{4}-\d{2}-\d{2})\s*$", text, re.M)
        sources = re.search(r"^sources:\s*\n((?:[ \t]+-.*\n)*)", text, re.M)
        source_refs = [v.strip().removeprefix("- ") for v in sources[1].splitlines()] if sources else []
        kind = "provenance" if name == "SOURCES.md" else "change_log" if name == "CHANGELOG.md" else "current"
        try:
            for heading, first, last, content in markdown_sections(text):
                records.append({"id": f"memory:{name}#{heading}", "kind": kind, "scope": "current",
                                "title": f"{name} / {heading}", "text": content,
                                "source": {"path": str(path), "line_start": first, "line_end": last},
                                "source_refs": source_refs, "file_updated": updated[1] if updated else None,
                                "status": "current_text" if kind == "current" else "context",
                                "approval": "See the entry's provenance; not inferred from file metadata.",
                                "applicability": "Read the full section and linked conditions before acting.",
                                "warnings": [] if source_refs or name in {"INDEX.md", "SOURCES.md", "CHANGELOG.md"}
                                else ["No file-level source reference; verify provenance when it matters."]})
        except ValueError as exc:
            warnings.append(f"Invalid memory {path}: {exc}")
    return records


def candidate_state(candidate: dict, review_id: str, decisions: list[dict],
                    history_root: Path, shared_root: Path | None) -> dict:
    """A recorded status is not necessarily approval of this exact candidate version."""
    related = [d for d in decisions if d.get("review_id") == review_id
               and d.get("candidate_id") == candidate.get("id")]
    notices = []
    valid_version = False
    try:
        validate_revision(candidate)
        valid_version = bool(candidate.get("proposal_digest"))
    except ValueError as exc:
        notices.append(str(exc))
    if not valid_version:
        notices.append("Legacy or incomplete proposal version: approval binding is unknown.")
    matching, unmatched = [], []
    for d in related:
        if (valid_version and d.get("proposal_digest") == candidate["proposal_digest"]
                and d.get("proposal_revision") == candidate["proposal_revision"]):
            matching.append(d)
        else:
            unmatched.append(d)
    if unmatched and valid_version:
        notices.append("Other or unspecified revisions exist; their approval is not inherited.")
    changes = {"proposed", "approved", "applied", "verified", "rejected", "retracted", "superseded"}
    recorded_status = next((d["decision"] for d in reversed(related) if d.get("decision") in changes), "proposed")
    bound_status, approval, applied, verified, withdrawn = "proposed", None, None, None, False
    accepted_verifications = []
    # Withdrawal is a barrier for this version. Delayed multi-Agent events cannot revive it.
    for event in matching:
        action = event.get("decision")
        if action in {"rejected", "retracted", "superseded"}:
            bound_status, approval, applied, verified, withdrawn = action, None, None, None, True
            accepted_verifications.clear()
        elif withdrawn and action in {"approved", "applied", "verified"}:
            notices.append("Ignored a post-withdrawal event; a new proposal version and approval are required.")
        elif action == "approved":
            if event.get("approval_ref"):
                bound_status, approval, applied, verified = "approved", event, None, None
                accepted_verifications.clear()
            else:
                notices.append("Approval event lacks a version-bound user reference.")
        elif action in {"applied", "verified"}:
            if approval is None:
                notices.append("Ignored application/verification without a preceding exact-version approval.")
                continue
            if any(event.get(k) and approval.get(k) and event[k] != approval[k]
                   for k in ("approval_ref", "application_ref", "batch_id")):
                notices.append("Ignored event linked to a different approval/application batch.")
                continue
            if action == "applied":
                bound_status, applied, verified = "applied", event, None
                accepted_verifications.clear()
            elif applied and event.get("verification_ref"):
                if any(event.get(k) and applied.get(k) and event[k] != applied[k]
                       for k in ("approval_ref", "application_ref", "batch_id")):
                    notices.append("Ignored verification linked to a different application.")
                    continue
                bound_status, verified = "verified", event
                accepted_verifications.append(event)
            else:
                notices.append("Ignored verification without application and a verification reference.")
    state = {"recorded_status": recorded_status, "status": bound_status if valid_version else "version_unknown",
             "proposal_revision": candidate.get("proposal_revision"),
             "proposal_digest": candidate.get("proposal_digest"),
             "approval_binding": "exact_version" if approval else "unknown" if not valid_version else "not_approved",
             "authorization_status": "withdrawn" if bound_status in {"retracted", "rejected", "superseded"} else "approved" if approval else "unknown" if not valid_version else "not_approved",
             "usable_as_current_rule": False,
             "approval_ref": approval.get("approval_ref") if approval else None,
             "historical_refs": [{k: d[k] for k in ("decision", "revision", "proposal_revision", "approval_ref", "application_ref", "verification_ref", "timestamp_utc") if k in d} for d in related],
             "applied": bool(applied), "verification_ref": verified.get("verification_ref") if verified else None,
             "verified_environments": list(dict.fromkeys(d.get("environment", "unspecified") for d in accepted_verifications)),
             "accepted_verification_refs": [{"environment": d.get("environment", "unspecified"), "verification_ref": d["verification_ref"]} for d in accepted_verifications],
             "warnings": notices, "current_target_match": "unknown"}
    application_ref = (applied or {}).get("application_ref")
    if application_ref and shared_root:
        app = read_json(history_root / application_ref, history_root, notices)
        if app and (app.get("proposal_digests", {}).get(candidate.get("id")) == candidate.get("proposal_digest")):
            hashes = app.get("authored_hashes", {})
            expected = {name: hashes.get(name) for name in candidate.get("targets", [])}
            actual = {}
            for name in expected:
                target = shared_root / name
                if not target.resolve().is_relative_to(shared_root.resolve()):
                    notices.append("Target escapes the shared root: " + name)
                    continue
                actual[name] = hashlib.sha256(target.read_bytes()).hexdigest() if target.is_file() else None
            if not expected or any(v is None for v in expected.values()) or set(actual) != set(expected):
                notices.append("Application target hashes are incomplete.")
            else:
                state["current_target_match"] = actual == expected
                if actual != expected:
                    notices.append("Targets changed since this application; historical checks do not verify current text.")
        elif app:
            notices.append("Application receipt does not bind this proposal digest.")
    elif applied:
        notices.append("Application receipt is missing; current target comparison is unavailable.")
    return state


def history_records(root: Path, shared_root: Path | None, warnings: list[str]) -> list[dict]:
    if not root.is_dir():
        warnings.append("Reviewed-history root is unavailable: " + str(root))
        return []
    decisions = [row for _, row in json_rows(root / "decisions.jsonl", root, warnings)]
    records, events = [], {}
    for path in sorted(root.glob("*/evidence.jsonl")):
        for line, row in json_rows(path, root, warnings):
            required = ("environment_id", "agent", "profile", "session_id", "event_id", "timestamp_utc", "role", "summary", "outcome", "origin_ref")
            if any(not isinstance(row.get(k), str) or not row[k].strip() for k in required):
                warnings.append(f"Incomplete evidence {path}:{line}")
                continue
            identity = evidence_identity(row)
            source = {"path": str(path), "line_start": line, "line_end": line}
            if identity in events:
                record = events[identity]
                record["copies"].append(source)
                record["event_ids"] = list(dict.fromkeys([*record["event_ids"], row["event_id"]]))
                if (any(record["evidence"].get(k) != row.get(k) for k in required if k != "event_id")
                        or record.get("verification_ref") != row.get("verification_ref")):
                    record["warnings"].append("Copies of the same original event differ; review all variants. They are not independent evidence.")
                    record["variants"].append({"source": source, "evidence": {k: row[k] for k in required}, "verification_ref": row.get("verification_ref")})
                    record["text"] += "\nConflicting copy:\n" + row["summary"]
                continue
            record = {"id": f"evidence:{row['origin_ref']}", "kind": "evidence", "scope": "history",
                      "title": f"{row['agent']} / {row['event_id']}", "text": row["summary"],
                      "source": source, "copies": [source], "event_ids": [row["event_id"]],
                      "variants": [{"source": source, "evidence": {k: row[k] for k in required}, "verification_ref": row.get("verification_ref")}],
                      "evidence": {k: row[k] for k in required}, "timestamp_utc": row["timestamp_utc"],
                      "verification_ref": row.get("verification_ref"), "independent_event_count": 1,
                      "status": row["outcome"], "warnings": []}
            if row["role"] not in {"user", "assistant", "observation"}:
                record["warnings"].append("Unknown actor type; do not infer user confirmation.")
            if row["outcome"].startswith("verified_") and not row.get("verification_ref"):
                record["warnings"].append("Claimed verification has no verification reference.")
            records.append(record); events[identity] = record
    by_event_id = {}
    for record in events.values():
        for event_id in record["event_ids"]:
            by_event_id.setdefault(event_id, []).append(record)
    for path in sorted(root.glob("*/review-package.json")):
        package = read_json(path, root, warnings)
        if not package:
            continue
        if package.get("schema_version") not in {1, 2} or not isinstance(package.get("candidates"), list):
            warnings.append("Unsupported review-package schema: " + str(path)); continue
        review_id = package.get("review_id")
        for c in package["candidates"]:
            if not isinstance(c, dict) or not c.get("id") or not isinstance(c.get("evidence_ids", []), list):
                warnings.append("Incomplete candidate: " + str(path)); continue
            state = candidate_state(c, review_id, decisions, root, shared_root)
            refs, event_keys, missing = [], set(), []
            for event_id in c.get("evidence_ids", []):
                found = by_event_id.get(event_id, [])
                if not found:
                    missing.append(event_id)
                if len(found) > 1:
                    state["warnings"].append("Evidence ID is ambiguous across sources: " + str(event_id))
                for event in found:
                    event_keys.add(event["id"])
                    refs.extend(event["copies"])
            if missing:
                state["warnings"].append("Evidence references not found in reviewed summaries: " + ", ".join(map(str, missing)))
            if package["schema_version"] == 2 and not isinstance(c.get("platform_assessment"), dict):
                state["warnings"].append("Schema 2 platform assessment is missing.")
            related = [d for d in decisions if d.get("review_id") == review_id and d.get("candidate_id") == c["id"]]
            records.append({"id": f"candidate:{review_id}:{c['id']}", "kind": "candidate", "scope": "history",
                            "title": f"{review_id} / {c['id']} / {c.get('proposal_key', '')}",
                            "text": "\n".join(str(c.get(k, "")) for k in ("problem", "exact_change", "existing_coverage", "impact", "validation"))
                                    + ("\n" + json.dumps(c["memory_update"], ensure_ascii=False) if c.get("memory_update") else ""),
                            "source": {"path": str(path), "candidate_id": c["id"]},
                            "schema_version": package["schema_version"], "candidate": c,
                            "timestamp_utc": next((d.get("timestamp_utc") for d in reversed(related) if d.get("timestamp_utc")), package.get("prepared_utc")),
                            "evidence_sources": refs, "located_event_count": len(event_keys),
                            "independence": "Original-event deduplication only; distinct events may still share one underlying incident.",
                            "platform_assessment": c.get("platform_assessment"), **state})
    return records


def query(root: Path, terms: list[str], *, scope: str = "all", history_root: Path | None = None,
          limit: int = 5, offset: int = 0, preview_chars: int = 500, full: bool = False,
          since: str | None = None, until: str | None = None) -> dict:
    root = root.expanduser().resolve()
    if not (root / "INDEX.md").is_file():
        raise ValueError("memories root must contain INDEX.md")
    terms = list(dict.fromkeys(t.strip() for t in terms if t.strip()))
    if not terms:
        raise ValueError("at least one nonempty search term is required")
    if scope not in {"all", "current", "history"}:
        raise ValueError("scope must be all, current or history")
    if limit < 1 or offset < 0 or preview_chars < 1:
        raise ValueError("limit/preview must be positive and offset nonnegative")
    first, last = timestamp(since) if since else None, timestamp(until) if until else None
    if first and last and first >= last:
        raise ValueError("since must be earlier than until")
    warnings = []
    shared_root = root.parent if root.name == "memories" and root.parent.name == ".agents" else None
    if history_root is None and shared_root:
        history_root = shared_root / "evolution"
    records = formal_records(root, warnings) if scope in {"all", "current"} else []
    if scope in {"all", "history"}:
        if history_root is None:
            warnings.append("Cannot derive the reviewed-history root; supply --history-root.")
        else:
            records.extend(history_records(history_root.expanduser().resolve(), shared_root, warnings))
    scored = []
    for record in records:
        text = normalized(record["title"] + "\n" + record["text"] + "\n" + json.dumps(record.get("evidence", {}), ensure_ascii=False) + "\n" + json.dumps(record.get("variants", []), ensure_ascii=False))
        hits = [term for term in terms if normalized(term) in text]
        if not hits:
            continue
        if (first or last) and record["scope"] == "history":
            try:
                when = timestamp(record.get("timestamp_utc") or "")
                if first and when < first or last and when >= last:
                    continue
            except ValueError:
                record["warnings"].append("Event time is unknown; included rather than silently lost to time filtering.")
        score = len(hits) * 10 + sum(3 for term in hits if normalized(term) in normalized(record["title"]))
        scored.append((score, record, hits))
    scored.sort(key=lambda value: (value[1]["kind"] != "current" if scope != "history" else False,
                                    -value[0], value[1]["scope"] != "current", value[1]["id"]))
    results = []
    for score, record, hits in scored[offset:offset + limit]:
        value = dict(record)
        text = value.pop("text")
        value.update(score=score, matched_terms=hits, preview=text if full else text[:preview_chars],
                     truncated=False if full else len(text) > preview_chars, total_chars=len(text))
        if not full:
            value.pop("candidate", None)  # Full payload is available through --full or the source file.
        results.append(value)
    return {"schema_version": 1, "read_only": True, "memories_root": str(root),
            "history_root": str(history_root) if history_root else None, "scope": scope, "terms": terms,
            "time_filter": {"since": since, "until": until, "applies_to": "history event time only; file updated is not fact time"},
            "scanned_records": len(records), "total_matches": len(scored), "offset": offset,
            "next_offset": offset + len(results) if offset + len(results) < len(scored) else None,
            "complete": not warnings, "warnings": warnings, "results": results,
            "usage": "Navigation only. Expand truncated results and read current conditions/provenance before action. Historical evidence/proposals do not authorize writes."}


def markdown(result: dict) -> str:
    lines = [f"Matches: {result['total_matches']}; shown: {len(result['results'])}; offset: {result['offset']}", result["usage"]]
    for warning in result["warnings"]:
        lines.append("Warning: " + warning)
    for row in result["results"]:
        source = row["source"]
        where = str(source["path"]) + (f":{source['line_start']}" if source.get("line_start") else "")
        lines += ["", f"## {row['title']}", f"Kind: {row['kind']}; status: {row['status']}", f"Source: {where}"]
        for key in ("source_refs", "applicability", "recorded_status", "proposal_revision", "proposal_digest", "approval_binding", "authorization_status", "usable_as_current_rule", "approval_ref", "verification_ref", "verified_environments", "accepted_verification_refs", "current_target_match", "platform_assessment", "historical_refs", "evidence", "variants", "copies", "located_event_count", "independence"):
            if key in row:
                lines.append(key + ": " + json.dumps(row[key], ensure_ascii=False))
        lines.extend("Warning: " + value for value in row["warnings"])
        lines.append(row["preview"])
        if row["truncated"]:
            lines.append(f"Truncated ({row['total_chars']} chars). Read the complete section or use --full.")
    if result["next_offset"] is not None:
        lines += ["", f"More matches: use --offset {result['next_offset']} with the same terms."]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path)
    parser.add_argument("--history-root", type=Path)
    parser.add_argument("--term", action="append", required=True, help="Repeat for keywords, synonyms or object names; literal OR matching.")
    parser.add_argument("--scope", choices=("all", "current", "history"), default="all")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--preview-chars", type=int, default=500)
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--since"); parser.add_argument("--until")
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    args = parser.parse_args()
    try:
        resolution = resolve() if args.root is None else None
        if resolution and not resolution.get("ok"):
            raise ValueError("cannot resolve shared memories; no content was guessed")
        root = args.root or Path(resolution["memories_root"])
        result = query(root, args.term, scope=args.scope, history_root=args.history_root,
                       limit=args.limit, offset=args.offset, preview_chars=args.preview_chars,
                       full=args.full, since=args.since, until=args.until)
        print(json.dumps(result, ensure_ascii=False, indent=2) if args.format == "json" else markdown(result), end="\n" if args.format == "json" else "")
        return 0
    except (OSError, ValueError, TypeError) as exc:
        print(json.dumps({"read_only": True, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
