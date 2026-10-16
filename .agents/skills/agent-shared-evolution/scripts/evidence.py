"""Local-only, standard-library history collection and review-package validation."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import tempfile

SHARED_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(SHARED_ROOT / "scripts"))
from shared_environment import detect_environment  # noqa: E402
from review_contract import validate_memory_update, validate_revision

OUTCOMES = {"unknown", "open", "aborted", "completed_unverified", "verified_success", "verified_failure"}
LOCAL_ROOT = Path.home() / ".agent-shared-evolution"


def utc(value: str | int | float | datetime) -> datetime:
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, (int, float)):
        result = datetime.fromtimestamp(value, timezone.utc)
    else:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("timestamp requires timezone")
    return result.astimezone(timezone.utc)


def iso(value: datetime) -> str:
    return utc(value).isoformat().replace("+00:00", "Z")


def redact(text: str) -> str:
    text = re.sub(r"<(think|analysis)>.*?</\1>", "[INTERNAL CONTENT OMITTED]", text, flags=re.S | re.I)
    text = re.sub(r"-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----", "[REDACTED PRIVATE KEY]", text, flags=re.S)
    text = re.sub(r"(?im)\b(authorization|cookie|set-cookie)\s*[:=][^\r\n]+", r"\1: [REDACTED]", text)
    text = re.sub(r"(?i)\b(sk-[\w-]{12,}|gh[pousr]_[\w]{12,}|github_pat_[\w]{12,})\b", "[REDACTED KEY]", text)
    text = re.sub(r"(?i)([\"']?(?:api[_-]?key|access[_-]?token|refresh[_-]?token|token|password|secret|client[_-]?secret)[\"']?\s*[:=]\s*)([\"'][^\"'\r\n]*[\"']|[^\s,;\r\n}\]]+)", r"\1[REDACTED]", text)
    text = re.sub(r"(?i)(https?://)[^/@\s]+:[^/@\s]+@", r"\1[REDACTED]@", text)
    text = re.sub(r"(/Users/|/home/)[^/\s]+", r"\1[USER]", text)
    return re.sub(r"(?i)[A-Z]:[\\/]Users[\\/][^\\/\s]+", r"[USERPROFILE]", text)


def digest(*parts: object) -> str:
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()[:24]


def safe_local(path: Path) -> Path:
    path = path.expanduser().resolve()
    if path.is_relative_to(SHARED_ROOT.parent.resolve()):
        raise ValueError("raw evidence and local state must stay outside shared system")
    if not any(path.is_relative_to(base.resolve()) for base in (LOCAL_ROOT, Path(tempfile.gettempdir()))):
        raise ValueError("output must be in ~/.agent-shared-evolution or the system temporary directory")
    return path


def write_local(path: Path, data: dict) -> Path:
    path = safe_local(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".writing")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)
    return path


def source(agent: str, profile: str, path: Path) -> dict:
    path = path.expanduser().resolve()
    env = detect_environment().environment_id
    return {"source_id": digest(env, agent, profile, str(path)), "environment_id": env,
            "agent": agent, "profile": profile, "path": str(path), "available": path.exists()}


def discover(home: Path | None = None, explicit: list[str] | None = None) -> list[dict]:
    if explicit:
        found = []
        for item in explicit:
            agent, profile, raw = item.split(":", 2)
            if agent not in {"codex", "claude", "hermes"}:
                raise ValueError("unsupported native adapter: " + agent)
            found.append(source(agent, profile, Path(raw)))
        return found
    home = home or Path.home()
    codex = Path(os.environ.get("CODEX_HOME", str(home / ".codex")))
    claude = Path(os.environ.get("CLAUDE_CONFIG_DIR", str(home / ".claude")))
    hermes = Path(os.environ.get("HERMES_HOME", str(home / ".hermes")))
    found = [source("codex", "default", codex), source("claude", "default", claude / "projects"),
             source("hermes", "default", hermes / "state.db")]
    if (hermes / "profiles").is_dir():
        for db in sorted((hermes / "profiles").glob("*/state.db")):
            found.append(source("hermes", db.parent.name, db))
    return list({s["source_id"]: s for s in found}.values())


def text_content(value: object, accepted: set[str]) -> str:
    if isinstance(value, str):
        return value
    if not isinstance(value, list):
        return ""
    return "\n".join(str(part.get("text", "")) for part in value
                     if isinstance(part, dict) and part.get("type") in accepted)


def injected_context(text: str) -> bool:
    stripped = text.strip()
    opening, closing = "<external_codex_apps_open_page>", "</external_codex_apps_open_page>"
    if (stripped.startswith(opening) and stripped.endswith(closing)
            and stripped.find(closing) == len(stripped) - len(closing)):
        return True
    if stripped == "[Request interrupted by user for tool use]":
        return True
    return text.lstrip().startswith(("# AGENTS.md instructions", "<INSTRUCTIONS>",
            "<environment_context>", "<recommended_plugins>", "<skill>",
            "<skills_instructions>", "<app-context>", "<user_instructions>"))


def event(s: dict, session: str, turn: str, timestamp: datetime, role: str, text: str,
          origin: str, outcome: str = "unknown", **extra: object) -> dict:
    clean = redact(text)
    return {"schema_version": 1, "event_id": digest(s["environment_id"], s["agent"], s["profile"], role, iso(timestamp), text),
            "environment_id": s["environment_id"], "source_id": s["source_id"],
            "agent": s["agent"], "profile": s["profile"], "session_id": session,
            "turn_id": turn, "timestamp_utc": iso(timestamp), "role": role,
            "excerpt": clean[:2400], "truncated": len(clean) > 2400,
            "outcome": outcome, "origin_ref": origin, **extra}


def json_rows(path: Path, stats: Counter):
    with path.open(encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                if not isinstance(row, dict):
                    raise ValueError("row not object")
            except (ValueError, TypeError):
                stats["malformed_rows"] += 1
                continue
            stats["rows"] += 1
            yield number, row


def native_files(s: dict) -> list[Path]:
    path = Path(s["path"])
    if path.is_file():
        return [path]
    if s["agent"] == "codex" and any((path / name).exists() for name in ("sessions", "archived_sessions")):
        roots = [path / "sessions", path / "archived_sessions"]
    else:
        roots = [path]
    return sorted({p for root in roots if root.exists() for p in root.rglob("*.jsonl")})


def codex_records(s: dict, start: datetime, end: datetime, stats: Counter) -> list[dict]:
    records, endings = [], {}
    for path in native_files(s):
        stats["files"] += 1
        session, turn, child = path.stem, "unknown", False
        recognized = False
        for number, row in json_rows(path, stats):
            kind, payload = row.get("type"), row.get("payload", {})
            if kind in {"session_meta", "event_msg", "response_item", "turn_context", "compacted", "world_state"}:
                recognized = True
            if not isinstance(payload, dict):
                continue
            if kind == "session_meta":
                session = str(payload.get("id") or payload.get("session_id") or session)
                src = payload.get("source")
                previously_child = child
                child = child or bool(payload.get("agent_path") or payload.get("subagent_history_start_ordinal") is not None or
                             isinstance(src, dict) and (src.get("subagent") or src.get("SubAgent")))
                if child and not previously_child:
                    stats["excluded_subagent_files"] += 1
                continue
            if child:
                continue
            if kind == "turn_context" or kind == "event_msg" and payload.get("type") == "task_started":
                turn = str(payload.get("turn_id") or turn)
                continue
            if kind == "event_msg" and payload.get("type") in {"task_complete", "turn_aborted"}:
                current_turn = str(payload.get("turn_id") or turn)
                try:
                    t = utc(row["timestamp"])
                except (ValueError, KeyError, TypeError, OverflowError):
                    stats["missing_timestamps"] += 1
                    continue
                endings[(session, current_turn)] = (t, "aborted" if payload["type"] == "turn_aborted" else "completed_unverified")
                continue
            if kind != "response_item" or payload.get("type") != "message":
                continue
            role = payload.get("role")
            if role not in {"user", "assistant"} or role == "assistant" and (payload.get("phase") not in {None, "final", "final_answer"} or payload.get("channel") in {"analysis", "commentary", "summary"}):
                continue
            text = text_content(payload.get("content"), {"input_text", "output_text", "text"})
            if not text or role == "user" and injected_context(text):
                if text:
                    stats["excluded_context_messages"] += 1
                continue
            try:
                t = utc(row["timestamp"])
            except (ValueError, KeyError, TypeError, OverflowError):
                stats["missing_timestamps"] += 1
                continue
            record = event(s, session, turn, t, role, text, f"{path}:{number}", "open")
            if payload.get("id"):
                record["event_id"] = digest(s["environment_id"], s["agent"], s["profile"], payload["id"])
            records.append(record)
        if not recognized:
            stats["unrecognized_files"] += 1
    for record in records:
        ending = endings.get((record["session_id"], record["turn_id"]))
        if ending and ending[0] < end:
            record["outcome"] = ending[1]
    # Native message IDs survive re-stamped inherited history. Keep the earliest actual event
    # before filtering the window, so an old copied message cannot become a new occurrence.
    unique = {}
    for record in sorted(records, key=lambda item: item["timestamp_utc"]):
        unique.setdefault(record["event_id"], record)
    stats["deduplicated_native_events"] += len(records) - len(unique)
    return [record for record in unique.values() if start <= utc(record["timestamp_utc"]) < end]


def claude_records(s: dict, start: datetime, end: datetime, stats: Counter) -> list[dict]:
    records = []
    for path in native_files(s):
        stats["files"] += 1
        turn, completed = "unknown", set()
        recognized = False
        for number, row in json_rows(path, stats):
            if row.get("type") in {"user", "assistant", "system", "mode", "permission-mode", "file-history-snapshot"}:
                recognized = True
            if row.get("isSidechain") or row.get("isMeta"):
                continue
            if row.get("type") == "system" and row.get("subtype") == "turn_duration":
                try:
                    if utc(row["timestamp"]) < end:
                        completed.add(turn)
                except (ValueError, KeyError, TypeError, OverflowError):
                    stats["missing_timestamps"] += 1
                continue
            if row.get("type") not in {"user", "assistant"}:
                continue
            message = row.get("message", {})
            if not isinstance(message, dict):
                stats["unsupported_message_rows"] += 1
                continue
            content = message.get("content")
            if row["type"] == "user" and isinstance(content, list) and any(isinstance(x, dict) and x.get("type") == "tool_result" for x in content):
                continue
            text = text_content(content, {"text", "input_text"})
            if row["type"] == "user" and text.strip() == "[Request interrupted by user for tool use]":
                turn = str(row.get("uuid") or number)  # Keep the interruption boundary without a human event.
                continue
            if not text or row["type"] == "user" and injected_context(text):
                continue
            if row["type"] == "user":
                turn = str(row.get("uuid") or number)
            try:
                t = utc(row["timestamp"])
            except (ValueError, KeyError, TypeError, OverflowError):
                stats["missing_timestamps"] += 1
                continue
            if message.get("stop_reason") == "end_turn" and t < end:
                completed.add(turn)
            if start <= t < end:
                records.append(event(s, str(row.get("sessionId") or row.get("session_id") or path.stem), turn, t,
                                     row["type"], text, f"{path}:{number}"))
        for record in records:
            if record["origin_ref"].startswith(str(path) + ":") and record["turn_id"] in completed:
                record["outcome"] = "completed_unverified"
        if not recognized:
            stats["unrecognized_files"] += 1
    return records


def hermes_records(s: dict, start: datetime, end: datetime, stats: Counter) -> list[dict]:
    path = Path(s["path"])
    if not path.is_file():
        raise ValueError("Hermes source must be a state.db file")
    db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=5)
    db.row_factory = sqlite3.Row
    records = []
    try:
        db.execute("BEGIN")
        columns = {r[1] for r in db.execute("PRAGMA table_info(sessions)")}
        parent = "s.parent_session_id" if "parent_session_id" in columns else "NULL"
        query = f"SELECT m.id, m.session_id, m.role, m.content, m.timestamp, s.ended_at, {parent} AS parent_id FROM messages m JOIN sessions s ON s.id=m.session_id WHERE m.role IN ('user','assistant') AND m.timestamp>=? AND m.timestamp<? ORDER BY m.timestamp,m.id"
        stats["files"] = 1
        for row in db.execute(query, (start.timestamp(), end.timestamp())):
            text = row["content"]
            if not isinstance(text, str) or not text:
                continue
            outcome = "completed_unverified" if row["ended_at"] is not None and row["ended_at"] < end.timestamp() else "open"
            records.append(event(s, row["session_id"], "unknown", utc(row["timestamp"]), row["role"], text,
                                 f"{path}#messages:{row['id']}", outcome, parent_session_id=row["parent_id"]))
        stats["missing_timestamps"] += db.execute("SELECT count(*) FROM messages WHERE role IN ('user','assistant') AND timestamp IS NULL").fetchone()[0]
    finally:
        db.rollback()
        db.close()
    return records


def collect(sources: list[dict], end: datetime, days: int = 30, since: datetime | None = None,
            cursors: dict | None = None) -> dict:
    if days <= 0:
        raise ValueError("days must be positive")
    coverage, records = [], []
    for s in sources:
        start = since or end - timedelta(days=days)
        previous = (cursors or {}).get(s["source_id"])
        if since is None and previous:
            start = min(start, utc(previous))
        if start >= end:
            raise ValueError("since must be before until")
        stats = Counter()
        c = {**s, "since_utc": iso(start), "until_utc": iso(end)}
        if not s["available"]:
            c.update(status="missing", events=0, reason="source_not_found")
        else:
            try:
                native = {"codex": codex_records, "claude": claude_records, "hermes": hermes_records}[s["agent"]](s, start, end, stats)
                records.extend(native)
                status = "partial" if any(stats[key] for key in ("malformed_rows", "missing_timestamps", "unrecognized_files", "unsupported_message_rows")) else "complete" if native else "empty"
                c.update(status=status, events=len(native), diagnostics=dict(stats))
            except (OSError, ValueError, sqlite3.Error, KeyError, TypeError) as exc:
                c.update(status="partial", events=0, reason=type(exc).__name__, diagnostics=dict(stats))
        coverage.append(c)
    unique = {}
    for record in sorted(records, key=lambda e: (e["timestamp_utc"], e["event_id"])):
        if record["event_id"] not in unique:
            unique[record["event_id"]] = record
        elif record["outcome"] == "aborted" or unique[record["event_id"]]["outcome"] in {"unknown", "open"}:
            unique[record["event_id"]]["outcome"] = record["outcome"]
    return {"schema_version": 1, "generated_utc": iso(datetime.now(timezone.utc)),
            "coverage": coverage, "evidence": list(unique.values()),
            "deduplicated_events": len(records) - len(unique) + sum(c.get("diagnostics", {}).get("deduplicated_native_events", 0) for c in coverage), "shared_export_reviewed": False}


def validate_summary(row: dict) -> dict:
    required = {"schema_version", "environment_id", "agent", "profile", "session_id", "event_id", "timestamp_utc", "role", "summary", "outcome", "origin_ref"}
    if required - row.keys() or row.get("schema_version") != 1:
        raise ValueError("summary missing required fields or unsupported schema")
    if row["role"] not in {"user", "assistant", "observation"} or row["outcome"] not in OUTCOMES:
        raise ValueError("invalid role or outcome")
    if any(not isinstance(row[key], str) or not row[key].strip() for key in required - {"schema_version"}):
        raise ValueError("summary fields must be nonempty strings")
    if row["outcome"].startswith("verified_") and not row.get("verification_ref"):
        raise ValueError("verified outcome requires verification_ref")
    result = {key: row[key] for key in required}
    result["timestamp_utc"] = iso(utc(row["timestamp_utc"]))
    result["summary"] = redact(row["summary"])
    result["origin_ref"] = redact(row["origin_ref"])
    if row.get("verification_ref"):
        result["verification_ref"] = redact(str(row["verification_ref"]))
    return result


def relative_target(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("target must be a string")
    path = Path(value)
    if not value or path.is_absolute() or ".." in path.parts or "\\" in value or ":" in value:
        raise ValueError("target must be a safe shared-root relative file")
    if path.parts[0] not in {"skills", "memories", "mcp", "scripts", "state"} and value not in {"README.md", "AGENTS.md", "CLAUDE.md"}:
        raise ValueError("target outside shared maintenance scope")
    return path.as_posix()


def validate_change_artifacts(candidate: dict, package_dir: Path | None, *, historical: bool = False) -> None:
    if "change_artifacts" not in candidate:
        return
    artifacts = candidate["change_artifacts"]
    if not isinstance(artifacts, dict):
        raise ValueError("change_artifacts must map package-relative files to SHA-256")
    for name, expected in artifacts.items():
        if not isinstance(name, str):
            raise ValueError("artifact path must be a string")
        path = Path(name)
        if (not path.parts or path.as_posix() != name or path.is_absolute() or name.startswith("/")
                or ".." in path.parts or "\\" in name or ":" in name):
            raise ValueError("artifact must be a safe package-relative file")
        if not isinstance(expected, str) or not re.fullmatch(r"[a-f0-9]{64}", expected):
            raise ValueError("artifact hash must be SHA-256")
        if historical:
            continue  # Historical readability does not prove live artifacts or authorization.
        if package_dir is None:
            raise ValueError("package directory required for artifact verification")
        base = package_dir.resolve()
        target = (base / name).resolve()
        if not target.is_relative_to(base):
            raise ValueError("artifact escapes package through a link: " + name)
        if not target.is_file():
            raise ValueError("artifact is missing or not a file: " + name)
        if hashlib.sha256(target.read_bytes()).hexdigest() != expected:
            raise ValueError("artifact changed: " + name)


def validate_package(package: dict, root: Path | None = None, *, historical: bool = False,
                     package_dir: Path | None = None) -> list[str]:
    if package.get("schema_version") not in {1, 2} or not package.get("review_id") or not package.get("coverage_ref"):
        raise ValueError("invalid review package header")
    if not historical and package["schema_version"] != 2:
        raise ValueError("new review packages require schema 2; use historical mode for old records")
    candidates = package.get("candidates")
    if not isinstance(candidates, list) or len(candidates) > 5 or any(not isinstance(c, dict) for c in candidates):
        raise ValueError("review package allows at most five candidates")
    memory = [c for c in candidates if c.get("owner") == "memories"]
    if len(memory) > 3 or memory and (not memory[0].get("related_group") or any(c.get("related_group") != memory[0]["related_group"] for c in memory)):
        raise ValueError("memory changes must be at most three and one related group")
    ids, keys = set(), set()
    checked = []
    for c in candidates:
        for key in ("id", "proposal_key", "problem", "existing_coverage", "exact_change", "impact", "validation", "rollback"):
            if not isinstance(c.get(key), str) or not c[key].strip():
                raise ValueError("missing candidate field: " + key)
        if not historical and (c.get("proposal_revision") is None or c.get("proposal_digest") is None):
            raise ValueError("new candidates require proposal_revision and proposal_digest")
        validate_revision(c)
        validate_memory_update(c)
        validate_change_artifacts(c, package_dir, historical=historical)
        if c["id"] in ids or c["proposal_key"] in keys:
            raise ValueError("duplicate candidate")
        ids.add(c["id"]); keys.add(c["proposal_key"])
        if c.get("status") != "proposed" or c.get("owner") not in {"skills", "memories", "mcps", "scripts", "state"}:
            raise ValueError("package must contain proposed shared-system candidates")
        if c.get("cause") not in {"rule_missing", "rule_conflict", "not_followed", "environment", "insufficient_evidence"}:
            raise ValueError("invalid cause")
        if package["schema_version"] == 2:
            assessment = c.get("platform_assessment")
            if not isinstance(assessment, dict) or set(assessment) != {"macos", "windows", "wsl"}:
                raise ValueError("new candidates require macOS, Windows and WSL assessment")
            for platform, item in assessment.items():
                if not isinstance(item, dict) or type(item.get("applies")) is not bool:
                    raise ValueError("platform applicability must be explicit: " + platform)
                if any(not isinstance(item.get(k), str) or not item[k].strip() for k in ("impact", "validation")):
                    raise ValueError("platform impact and verification required: " + platform)
                if item.get("verification_status") not in {"verified", "unverified", "not_applicable"}:
                    raise ValueError("invalid platform verification status: " + platform)
                if not item["applies"] and item["verification_status"] != "not_applicable":
                    raise ValueError("unaffected platforms must be marked not_applicable: " + platform)
                if item["applies"] and item["verification_status"] == "not_applicable":
                    raise ValueError("applicable platforms require a verification status: " + platform)
        if not isinstance(c.get("evidence_ids"), list) or not c["evidence_ids"] or any(not isinstance(x, str) or not x for x in c["evidence_ids"]):
            raise ValueError("evidence references required")
        if not isinstance(c.get("targets"), list) or not c["targets"] or not isinstance(c.get("baseline"), dict) or set(c["targets"]) != set(c["baseline"]):
            raise ValueError("each target requires baseline")
        for name, baseline in c["baseline"].items():
            relative_target(name)
            if baseline is not None and (not isinstance(baseline, str) or not re.fullmatch(r"[a-f0-9]{64}", baseline)):
                raise ValueError("baseline must be SHA-256 or null")
            if root:
                target = (root / name).resolve()
                if not target.is_relative_to(root.resolve()):
                    raise ValueError("target escapes root through a link")
                actual = hashlib.sha256(target.read_bytes()).hexdigest() if target.is_file() else None
                if actual != baseline:
                    raise ValueError("target changed: " + name)
        checked.append(c["id"])
    return checked


def rejection_has_new_evidence(candidate: dict, decisions: list[dict]) -> bool:
    rejected = [d for d in decisions if d.get("proposal_key") == candidate["proposal_key"] and d.get("decision") == "rejected"]
    if not rejected:
        return True
    seen = set().union(*(set(d.get("evidence_ids", [])) for d in rejected))
    return bool(set(candidate.get("evidence_ids", [])) - seen)


def commit_review(report: dict, reference: str, cursors: dict) -> dict:
    if not reference.strip() or report.get("schema_version") != 1:
        raise ValueError("review reference required")
    updated = dict(cursors)
    for c in report["coverage"]:
        if c["status"] in {"complete", "empty"}:
            value = iso(utc(c["until_utc"]))
            if c["source_id"] not in updated or utc(updated[c["source_id"]]) < utc(value):
                updated[c["source_id"]] = value
    return updated


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("discover", "collect"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--source", action="append")
        if name == "collect":
            cmd.add_argument("--days", type=int)
            cmd.add_argument("--since")
            cmd.add_argument("--until")
            cmd.add_argument("--output", type=Path)
    cmd = sub.add_parser("import-summary")
    cmd.add_argument("--input", type=Path, required=True)
    cmd.add_argument("--output", type=Path, required=True)
    cmd = sub.add_parser("validate-package")
    cmd.add_argument("--package", type=Path, required=True)
    cmd.add_argument("--historical", action="store_true", help="Read legacy structure without inventing version-bound approval.")
    cmd.add_argument("--root", type=Path)
    cmd.add_argument("--decisions", type=Path)
    cmd = sub.add_parser("commit-review")
    cmd.add_argument("--report", type=Path, required=True)
    cmd.add_argument("--reference", required=True)
    args = parser.parse_args()
    try:
        if args.command == "discover":
            print(json.dumps({"environment_id": detect_environment().environment_id, "sources": discover(explicit=args.source)}, ensure_ascii=False, indent=2))
        elif args.command == "collect":
            cursor_path = safe_local(LOCAL_ROOT / "review-cursors.json")
            cursors = json.loads(cursor_path.read_text(encoding="utf-8")) if cursor_path.exists() else {}
            end = utc(args.until) if args.until else datetime.now(timezone.utc)
            report = collect(discover(explicit=args.source), end, args.days if args.days is not None else (7 if cursors else 30), utc(args.since) if args.since else None, cursors)
            output = args.output or LOCAL_ROOT / "runs" / (end.strftime("%Y%m%dT%H%M%SZ") + ".json")
            path = write_local(output, report)
            print(json.dumps({"output": str(path), "events": len(report["evidence"]), "deduplicated": report["deduplicated_events"], "coverage": [{k: c.get(k) for k in ("agent", "profile", "status", "events", "diagnostics")} for c in report["coverage"]]}, ensure_ascii=False))
        elif args.command == "import-summary":
            rows = [validate_summary(json.loads(line)) for line in args.input.read_text(encoding="utf-8").splitlines() if line.strip()]
            unique = {(r["environment_id"], r["agent"], r["profile"], r["event_id"]): r for r in rows}
            path = write_local(args.output, {"schema_version": 1, "evidence": list(unique.values()), "shared_export_reviewed": False})
            print(json.dumps({"output": str(path), "events": len(unique)}))
        elif args.command == "validate-package":
            package = json.loads(args.package.read_text(encoding="utf-8"))
            checked = validate_package(package, args.root, historical=args.historical, package_dir=args.package.resolve().parent)
            ledger = args.decisions or (args.root / "evolution" / "decisions.jsonl" if args.root else None)
            if ledger and ledger.exists():
                decisions = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines() if line.strip()]
                for c in package["candidates"]:
                    if not rejection_has_new_evidence(c, decisions):
                        raise ValueError("previously rejected without new evidence: " + c["id"])
            print(json.dumps({"valid": True, "candidates": checked}, ensure_ascii=False))
        else:
            path = safe_local(LOCAL_ROOT / "review-cursors.json")
            cursors = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
            report = json.loads(args.report.read_text(encoding="utf-8"))
            write_local(path, commit_review(report, args.reference, cursors))
            print(json.dumps({"review_reference": args.reference, "cursor_file": str(path)}))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"error": redact(str(exc))}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
