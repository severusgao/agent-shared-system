#!/usr/bin/env python3
"""Lint the shared memories directory."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from pathlib import Path
from typing import Any, Mapping, Optional

import sys

sys.dont_write_bytecode = True

from resolve_memories_root import describe_local_entry, resolve


REQUIRED_FILES = [
    "INDEX.md",
    "USER_PROFILE.md",
    "ENVIRONMENT.md",
    "AGENT_RULES.md",
    "AGENT_PROFILES.md",
    "TOOLS.md",
    "DECISIONS.md",
    "WORKFLOWS.md",
    "SOURCES.md",
    "CHANGELOG.md",
]

ALLOWED_DIRS: set[str] = set()
STAGING_DIRS = {"total memories"}
RUNTIME_NAMES = {"state", "tmp"}
RUNTIME_SUFFIXES = (".lock", ".bak", ".tmp", ".state")
REQUIRED_FRONTMATTER = {"tags", "created", "updated", "type", "status", "sources"}
DELETED_STAGING_SOURCE = re.compile(r"(?:\.agents/memories/)?total memories/")

SECRET_PATTERNS = {
    "openai_like_key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "firecrawl_like_key": re.compile(r"\bfc-[A-Za-z0-9]{20,}\b"),
    "jwt_like_token": re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    "generic_private_key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
}


def _scan_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _parse_frontmatter(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    text = _scan_text(path)
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None, "missing frontmatter"

    try:
        closing = next(index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---")
    except StopIteration:
        return None, "unclosed frontmatter"

    data: dict[str, Any] = {}
    current_list: str | None = None
    for raw_line in lines[1:closing]:
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("-") and current_list:
            value = stripped[1:].strip().strip('"').strip("'")
            data.setdefault(current_list, []).append(value)
            continue
        if ":" not in raw_line:
            current_list = None
            continue
        key, value = raw_line.split(":", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if value == "[]":
            data[key] = []
            current_list = key
        elif value:
            data[key] = value
            current_list = None
        else:
            data[key] = []
            current_list = key
    return data, None


def _valid_iso_date(value: Any) -> bool:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return False
    try:
        dt.date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _validate_frontmatter(path: Path, rel: Path, errors: list[str]) -> dict[str, Any] | None:
    metadata, parse_error = _parse_frontmatter(path)
    if parse_error:
        errors.append(f"{rel}: {parse_error}")
        return None
    assert metadata is not None

    missing = sorted(REQUIRED_FRONTMATTER - metadata.keys())
    if missing:
        errors.append(f"{rel}: missing frontmatter fields: {', '.join(missing)}")
    for field in ("created", "updated"):
        if field in metadata and not _valid_iso_date(metadata[field]):
            errors.append(f"{rel}: invalid {field} date: {metadata[field]!r}")
    return metadata


def _runtime_artifact(path: Path) -> bool:
    lower = path.name.lower()
    return lower in RUNTIME_NAMES or lower.endswith(RUNTIME_SUFFIXES) or ".bak." in lower


def lint(
    root: Path,
    *,
    strict: bool = False,
    root_source: str = "explicit",
    local_info: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    root = root.expanduser().resolve()
    local_info = dict(local_info or describe_local_entry())
    errors: list[str] = []
    warnings: list[str] = list(local_info.get("warnings", []))

    result = {
        "ok": False,
        "errors": errors,
        "warnings": warnings,
        "root": str(root),
        "root_source": root_source,
        "local_entry": local_info.get("local_entry"),
        "local_entry_kind": local_info.get("local_entry_kind"),
        "local_entry_target": local_info.get("local_entry_target"),
        "local_entry_resolved": local_info.get("local_entry_resolved"),
        "local_entry_matches_root": None,
    }

    local_resolved = local_info.get("local_entry_resolved")
    if local_resolved:
        result["local_entry_matches_root"] = str(root) == str(Path(str(local_resolved)).resolve())

    if not root.is_dir():
        errors.append(f"missing memories root: {root}")
        return result

    for name in REQUIRED_FILES:
        path = root / name
        if not path.is_file():
            errors.append(f"missing required file: {name}")
            continue
        metadata = _validate_frontmatter(path, Path(name), errors)
        if metadata:
            for source in metadata.get("sources", []):
                if DELETED_STAGING_SOURCE.search(str(source)):
                    errors.append(f"{name}: deleted staging source: {source}")

    for item in sorted(root.iterdir(), key=lambda path: path.name.lower()):
        name = item.name
        lower = name.lower()
        if name == ".DS_Store":
            errors.append("remove .DS_Store from memories root")
            continue
        if "conflicted copy" in lower or "冲突" in name:
            errors.append(f"iCloud conflict copy found: {item.relative_to(root)}")
        if item.is_dir():
            if name in STAGING_DIRS:
                message = f"temporary staging directory present: {name}"
                if strict:
                    errors.append(message)
                else:
                    warnings.append(message)
            elif lower in RUNTIME_NAMES:
                errors.append(f"runtime directory in formal memories: {name}")
            elif name not in ALLOWED_DIRS:
                errors.append(f"unexpected top-level directory: {name}")
        elif item.is_file():
            if _runtime_artifact(item):
                errors.append(f"runtime/backup file in formal memories: {name}")
            elif name not in REQUIRED_FILES and name not in {"USER_PROFILE.example.md", "ENVIRONMENT.example.md", "AGENT_PROFILES.example.md"}:
                errors.append(f"unexpected top-level file: {name}")

    for path in sorted(root.rglob("*"), key=lambda item: str(item).lower()):
        rel = path.relative_to(root)
        rel_text = str(rel)
        lower_name = path.name.lower()
        if ".git" in path.parts:
            if path.name != ".git":
                continue
            warnings.append(f"git metadata under memories root: {rel_text}")
            continue
        if path.name == ".DS_Store":
            errors.append(f"remove .DS_Store: {rel_text}")
        if "conflicted copy" in lower_name or "冲突" in path.name:
            errors.append(f"iCloud conflict copy found: {rel_text}")
        if _runtime_artifact(path):
            if "total memories" in path.parts:
                warnings.append(f"staging runtime file ignored: {rel_text}")
            else:
                errors.append(f"runtime/backup file in formal memories: {rel_text}")
        if path.is_dir() and path.name.lower() in RUNTIME_NAMES:
            errors.append(f"runtime directory in formal memories: {rel_text}")
        if path.is_file() and path.suffix.lower() in {".py", ".ps1", ".cmd", ".sh"} and "total memories" not in path.parts:
            warnings.append(f"script file under formal memories: {rel_text}")
        if (
            path.is_file()
            and path.suffix.lower() in {".md", ".txt", ".yaml", ".yml", ".json"}
            and "total memories" not in path.parts
        ):
            text = _scan_text(path)
            for label, pattern in SECRET_PATTERNS.items():
                if pattern.search(text):
                    errors.append(f"{label} found in {rel_text}")

    errors[:] = list(dict.fromkeys(errors))
    warnings[:] = list(dict.fromkeys(warnings))
    result["ok"] = not errors
    return result


def _resolved_root(explicit_root: str | None) -> tuple[Optional[Path], str, dict[str, Any] | None]:
    if explicit_root:
        root = Path(explicit_root).expanduser()
        return root, "explicit", None

    resolved = resolve()
    if not resolved.get("ok"):
        return None, "resolver-error", resolved
    return Path(str(resolved["memories_root"])), str(resolved["method"]), resolved


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=None)
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    parser.add_argument("--strict", action="store_true", help="Treat temporary staging directories as errors.")
    args = parser.parse_args()

    root, root_source, resolved = _resolved_root(args.root)
    local_info: Mapping[str, Any]
    if resolved:
        local_info = {
            "local_entry": resolved.get("local_entry"),
            "local_entry_kind": resolved.get("local_entry_kind"),
            "local_entry_target": resolved.get("local_entry_target"),
            "local_entry_resolved": resolved.get("local_entry_resolved"),
            "warnings": resolved.get("warnings", []),
        }
    else:
        local_info = describe_local_entry()

    if root is None:
        result = {
            "ok": False,
            "errors": [str((resolved or {}).get("error") or "unable to resolve shared memories root")],
            "warnings": list(local_info.get("warnings", [])),
            "root": None,
            "root_source": root_source,
            "local_entry": local_info.get("local_entry"),
            "local_entry_kind": local_info.get("local_entry_kind"),
            "local_entry_target": local_info.get("local_entry_target"),
            "local_entry_resolved": local_info.get("local_entry_resolved"),
            "local_entry_matches_root": None,
            "hint": (resolved or {}).get("hint"),
        }
    else:
        result = lint(root, strict=args.strict, root_source=root_source, local_info=local_info)

    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("# Shared Memories Lint")
        print()
        print(f"- root: `{result['root']}`")
        print(f"- root source: `{result['root_source']}`")
        print(f"- local entry: `{result['local_entry']}`")
        print(f"- local entry kind: `{result['local_entry_kind']}`")
        print(f"- local entry target: `{result['local_entry_target']}`")
        print(f"- local entry resolved: `{result['local_entry_resolved']}`")
        print(f"- local entry matches root: `{result['local_entry_matches_root']}`")
        print(f"- ok: `{str(result['ok']).lower()}`")
        if result.get("hint"):
            print(f"- hint: `{result['hint']}`")
        print()
        print("## Errors")
        if result["errors"]:
            for error in result["errors"]:
                print(f"- {error}")
        else:
            print("- none")
        print()
        print("## Warnings")
        if result["warnings"]:
            for warning in result["warnings"]:
                print(f"- {warning}")
        else:
            print("- none")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
