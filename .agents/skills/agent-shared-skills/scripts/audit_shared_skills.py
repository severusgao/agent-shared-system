#!/usr/bin/env python3
"""Audit shared-source shared skills without modifying them."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Set

SCRIPT_DIR = Path(__file__).resolve().parent
SHARED_SCRIPTS = SCRIPT_DIR.parents[2] / "scripts"
sys.path.insert(0, str(SHARED_SCRIPTS))
sys.path.insert(0, str(SCRIPT_DIR))

from resolve_skills_root import resolve_skills_root  # noqa: E402
from shared_environment import StateConflict, detect_environment, load_json_state  # noqa: E402
from skill_metadata import MetadataError, read_frontmatter, read_yaml
from summarize_shared_skills import summarize  # noqa: E402


DESCRIPTION_MAX_LENGTH = 1024
SHORT_DESCRIPTION_MIN_LENGTH = 25
SHORT_DESCRIPTION_MAX_LENGTH = 64
TRIGGER_PATTERNS = (
    re.compile(r"触发词\s*[:：]"),
    re.compile(r"\buse when\b", re.IGNORECASE),
    re.compile(r"\bwhen\b", re.IGNORECASE),
    re.compile(r"用于"),
    re.compile(r"适用于"),
    re.compile(r"当.+时"),
    re.compile(r"(?:用户|Agent|智能体).*(?:要求|需要|提到|询问)"),
)


def _same_path(left: Path, right: Path) -> bool:
    try:
        return left.samefile(right)
    except OSError:
        return str(left.resolve()) == str(right.resolve())


def _local_entry_status(root: Path, skill_name: str) -> Dict[str, Any]:
    entry = Path.home() / ".agents" / "skills" / skill_name
    target = root / skill_name
    exists = entry.exists() or entry.is_symlink()
    status: Dict[str, Any] = {
        "entry": str(entry),
        "exists": exists,
        "is_symlink": entry.is_symlink(),
        "resolved": None,
        "matches": None,
    }
    if not exists:
        return status
    try:
        resolved = entry.resolve()
        status["resolved"] = str(resolved)
        status["matches"] = _same_path(resolved, target)
    except OSError:
        status["matches"] = False
    return status


def _skill_invocation_metadata(skill_dir: Path) -> Dict[str, Any]:
    metadata = read_frontmatter(skill_dir / "SKILL.md")
    openai_path = skill_dir / "agents" / "openai.yaml"
    openai_present = openai_path.is_file()
    openai = read_yaml(openai_path.read_text(encoding="utf-8-sig")) if openai_present else {}
    policy, interface = openai.get("policy", {}), openai.get("interface", {})
    if not isinstance(policy, dict) or not isinstance(interface, dict):
        raise MetadataError("OpenAI policy/interface must be mappings")
    implicit = policy.get("allow_implicit_invocation", True)
    if not isinstance(implicit, bool):
        raise MetadataError("allow_implicit_invocation must be a boolean")
    short = interface.get("short_description")
    if short is not None and not isinstance(short, str):
        raise MetadataError("short_description must be a string")
    explicit = metadata.get("disable-model-invocation", False)
    return {"claude_explicit": explicit, "openai_present": openai_present,
            "openai_explicit": not implicit, "user_invoked": explicit or not implicit,
            "short_description": short}


def _has_trigger_clause(description: str) -> bool:
    return any(pattern.search(description) for pattern in TRIGGER_PATTERNS)


def audit(root: Path) -> Dict[str, Any]:
    current = detect_environment()
    rows = summarize(root)
    errors: List[str] = []
    warnings: List[str] = []
    shared_system = _shared_system_status(root, current)

    for child in sorted(root.iterdir()):
        if child.is_dir() and not (child / "SKILL.md").is_file():
            warnings.append(f"directory without SKILL.md: {child.name}")

    seen_names: Set[str] = set()
    for row in rows:
        folder = str(row["folder"])
        name = row.get("name")
        description = row.get("description")
        skill_dir = root / folder
        if row.get("metadata_error"):
            errors.append(f"{folder}: {row['metadata_error']}")
            continue
        try:
            invocation = _skill_invocation_metadata(skill_dir)
        except (MetadataError, OSError) as exc:
            errors.append(f"{folder}: {exc}")
            continue
        for nested in row.get("nested_skills", []):
            nested_dir = skill_dir / Path(nested["path"]).parent
            try:
                _skill_invocation_metadata(nested_dir)
                if nested.get("name") != nested_dir.name or not nested.get("description"):
                    raise MetadataError("nested name must match folder and description must be present")
            except (MetadataError, OSError) as exc:
                errors.append(f"{folder}/{nested['path']}: {exc}")

        if not name:
            errors.append(f"{folder}: missing name in SKILL.md")
        elif name != folder:
            errors.append(f"{folder}: SKILL.md name is {name!r}, expected {folder!r}")
        elif name in seen_names:
            errors.append(f"{folder}: duplicate skill name {name!r}")
        else:
            seen_names.add(str(name))

        description_text = str(description or "").strip()
        if not description_text:
            warnings.append(f"{folder}: description is missing")
        elif len(description_text) > DESCRIPTION_MAX_LENGTH:
            warnings.append(
                f"{folder}: description exceeds {DESCRIPTION_MAX_LENGTH} characters"
            )
        elif not invocation["user_invoked"] and not _has_trigger_clause(description_text):
            warnings.append(f"{folder}: model-invoked description has no trigger clause")

        if invocation["openai_present"] and (
            invocation["claude_explicit"] != invocation["openai_explicit"]
        ):
            warnings.append(
                f"{folder}: invocation policy mismatch "
                f"(Claude explicit={invocation['claude_explicit']}, "
                f"OpenAI explicit={invocation['openai_explicit']})"
            )

        short_description = invocation["short_description"]
        if short_description is not None and not (
            SHORT_DESCRIPTION_MIN_LENGTH
            <= len(short_description)
            <= SHORT_DESCRIPTION_MAX_LENGTH
        ):
            warnings.append(
                f"{folder}: short_description must be "
                f"{SHORT_DESCRIPTION_MIN_LENGTH}-{SHORT_DESCRIPTION_MAX_LENGTH} characters"
            )

        local_status = _local_entry_status(root, folder)
        if local_status["exists"] and local_status["matches"] is False:
            warnings.append(f"{folder}: local discovery entry points elsewhere: {local_status.get('resolved')}")

    warnings.extend(_content_warnings(root))
    likely_overlap = _detect_likely_overlap(rows)
    warnings.extend(likely_overlap)
    if shared_system.get("error"):
        warnings.append(shared_system["error"])
    elif not shared_system.get("recorded", False):
        warnings.append(
            "current environment is not recorded in .agents/state/shared_system_instances.json"
        )

    return {
        "root": str(root.resolve()),
        "environment_id": current.environment_id,
        "platform": current.platform,
        "machine_display": current.machine_display,
        "wsl_distro": current.wsl_distro,
        "shared_system_state": shared_system,
        "skills_count": len(rows),
        "errors": errors,
        "warnings": warnings,
        "skills": rows,
    }


def _content_warnings(root: Path) -> List[str]:
    """Check explicit Markdown file links; skip code examples, URLs and anchor-only links."""
    import os
    from urllib.parse import unquote, urlsplit
    findings = []
    excluded = {"__pycache__", ".git", "node_modules", ".venv", ".pytest_cache"}
    for directory, dirs, files in os.walk(root, followlinks=False):
        for name in dirs[:]:
            path = Path(directory) / name
            if name in excluded:
                findings.append(f"generated/vendor directory: {path.relative_to(root).as_posix()}")
                dirs.remove(name)
            elif path.is_symlink():
                dirs.remove(name)
        for name in files:
            path = Path(directory) / name
            if name.endswith('.pyc') or name == '.git':
                findings.append(f"generated/repository file: {path.relative_to(root).as_posix()}")
            if path.suffix.lower() != '.md':
                continue
            content = path.read_text(encoding="utf-8-sig", errors="replace")
            content = re.sub(r"(?ms)^```.*?^```[^\n]*", "", content)
            content = re.sub(r"`[^`\n]+`", "", content)
            for match in re.finditer(r"!?\[[^\]\n]*\]\((<[^>]+>|[^\s)]+)(?:\s+[^)]*)?\)", content):
                value = match.group(1).strip('<>')
                if value.startswith(('#', '/', '\\')) or urlsplit(value).scheme:
                    continue
                value = unquote(value.split('#', 1)[0].split('?', 1)[0])
                if not value or any(c in value for c in ('*', '{', '}', '<', '>')):
                    continue
                target = path.parent / value
                if not target.exists():
                    findings.append(f"broken local link: {path.relative_to(root).as_posix()} -> {value}")
    return sorted(set(findings))


def _detect_likely_overlap(rows: List[Dict[str, Any]]) -> List[str]:
    warnings: List[str] = []
    desc_words: Dict[str, Set[str]] = {}
    stop = {
        "and",
        "or",
        "the",
        "with",
        "when",
        "use",
        "agent",
        "agents",
        "shared",
        "skill",
        "skills",
        "使用",
        "用于",
        "需要",
        "用户",
        "任务",
        "技能",
        "共享",
        "智能",
        "能体",
        "进行",
        "处理",
    }
    for row in rows:
        name = str(row.get("name") or row.get("folder"))
        desc = str(row.get("description") or "").lower()
        words = {word for word in re.findall(r"[a-z0-9]{4,}", desc) if word not in stop}
        for sequence in re.findall(r"[\u3400-\u9fff]+", desc):
            for size in (2, 3):
                words.update(
                    sequence[index : index + size]
                    for index in range(len(sequence) - size + 1)
                    if sequence[index : index + size] not in stop
                )
        desc_words[name] = words

    names = sorted(desc_words)
    for index, left in enumerate(names):
        for right in names[index + 1 :]:
            common = desc_words[left] & desc_words[right]
            smaller = min(len(desc_words[left]), len(desc_words[right]))
            overlap_ratio = len(common) / smaller if smaller else 0.0
            if len(common) >= 8 and overlap_ratio >= 0.45:
                warnings.append(f"{left}/{right}: possible overlapping descriptions ({', '.join(sorted(common)[:8])})")
    return warnings


def _shared_system_state_file(root: Path) -> Path:
    resolved_root = root.expanduser().resolve()
    if resolved_root.name == "skills" and resolved_root.parent.name == ".agents":
        return resolved_root.parent / "state" / "shared_system_instances.json"

    discovered = resolve_skills_root(start=resolved_root)
    if discovered.get("ok"):
        skills_root = Path(str(discovered["skills_root"])).resolve()
        if skills_root.name == "skills" and skills_root.parent.name == ".agents":
            return skills_root.parent / "state" / "shared_system_instances.json"

    return resolved_root.parent / "state" / "shared_system_instances.json"


def _shared_system_status(root: Path, current: Any) -> Dict[str, Any]:
    state_file = _shared_system_state_file(root)
    status: Dict[str, Any] = {
        "state_file": str(state_file),
        "exists": state_file.is_file(),
        "recorded": False,
        "error": None,
    }
    if not state_file.is_file():
        return status
    try:
        data = load_json_state(state_file)
    except StateConflict as exc:
        status["error"] = str(exc)
        return status
    environments = data.get("environments", [])
    status["recorded"] = any(
        item.get("environment_id") == current.environment_id for item in environments
    )
    return status


def render_markdown(result: Dict[str, Any]) -> str:
    lines = [
        "# Shared Skills Audit",
        "",
        f"- Root: `{result['root']}`",
        f"- Environment ID: `{result['environment_id']}`",
        f"- Platform: `{result['platform']}`",
        f"- Machine: `{result['machine_display']}`",
        f"- WSL distro: `{result['wsl_distro'] or 'n/a'}`",
        f"- Shared system state: `{result['shared_system_state']['state_file']}`",
        f"- Current environment recorded: `{result['shared_system_state']['recorded']}`",
        f"- Skills found: {result['skills_count']}",
        f"- Errors: {len(result['errors'])}",
        f"- Warnings: {len(result['warnings'])}",
        "",
    ]
    if result["errors"]:
        lines.extend(["## Errors", ""])
        lines.extend(f"- {item}" for item in result["errors"])
        lines.append("")
    if result["warnings"]:
        lines.extend(["## Warnings", ""])
        lines.extend(f"- {item}" for item in result["warnings"])
        lines.append("")
    lines.extend(["## Skills", "", "| Folder | Name | References | Scripts | OpenAI metadata |", "|---|---|---:|---:|---:|"])
    for row in result["skills"]:
        lines.append(
            "| `{}` | `{}` | {} | {} | {} |".format(
                row["folder"],
                row.get("name"),
                "yes" if row.get("has_references") else "no",
                "yes" if row.get("has_scripts") else "no",
                "yes" if row.get("has_openai_yaml") else "no",
            )
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=None, help="Shared skills root. Defaults to discovery.")
    parser.add_argument("--format", choices=["json", "markdown"], default="markdown")
    args = parser.parse_args()

    if args.root:
        root = Path(args.root).expanduser()
    else:
        resolved = resolve_skills_root()
        if not resolved.get("ok"):
            print(json.dumps(resolved, ensure_ascii=False, indent=2), file=sys.stderr)
            return 1
        root = Path(str(resolved["skills_root"]))

    result = audit(root)
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(result))
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
