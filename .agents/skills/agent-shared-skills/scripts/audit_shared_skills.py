#!/usr/bin/env python3
"""Audit shared-source shared skills without modifying them."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Set

sys.dont_write_bytecode = True

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
MANIFEST_RELATIVE = Path("agent-shared-skills") / "references" / "skills_manifest.json"
MANIFEST_OPTIONAL_FILES = ("agents/openai.yaml", "local/ADAPTATION.md")
# iCloud names a conflicting copy "name 2.ext" next to "name.ext".
ICLOUD_CONFLICT = re.compile(r"^(?P<stem>.+) \d+(?P<suffix>\.[^.]+)?$")


def manifest_path(root: Path) -> Path:
    return root / MANIFEST_RELATIVE


def load_manifest(root: Path) -> Dict[str, List[str]] | None:
    path = manifest_path(root)
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    skills = data.get("skills") if isinstance(data, dict) else None
    if not isinstance(skills, dict) or not all(
        isinstance(files, list) and all(isinstance(item, str) for item in files)
        for files in skills.values()
    ):
        raise ValueError(f"{path}: `skills` must map skill names to lists of required files")
    return skills


def build_manifest(root: Path) -> Dict[str, Any]:
    skills: Dict[str, List[str]] = {}
    for child in sorted(root.iterdir()):
        if child.is_dir() and (child / "SKILL.md").is_file():
            skills[child.name] = ["SKILL.md"] + [
                item for item in MANIFEST_OPTIONAL_FILES if (child / item).is_file()
            ]
    return {
        "version": 1,
        "description": "Expected shared skills and their required files. Update with "
        "audit_shared_skills.py --write-manifest after an approved install, update or retirement.",
        "skills": skills,
    }


def _manifest_findings(root: Path, manifest: Dict[str, List[str]] | None) -> tuple[List[str], List[str]]:
    errors: List[str] = []
    warnings: List[str] = []
    if manifest is None:
        warnings.append(f"no expected-skills manifest at {MANIFEST_RELATIVE.as_posix()}; missing skills cannot be detected")
        return errors, warnings
    for name, files in sorted(manifest.items()):
        if not (root / name).is_dir():
            errors.append(f"expected skill missing: {name}")
            continue
        for item in files:
            if not (root / name / item).is_file():
                errors.append(f"expected file missing: {name}/{item}")
    for child in sorted(root.iterdir()):
        if child.is_dir() and (child / "SKILL.md").is_file() and child.name not in manifest:
            warnings.append(f"skill not in manifest: {child.name}; run --write-manifest after review")
    return errors, warnings


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
            errors.append(f"directory without SKILL.md: {child.name}")

    try:
        manifest_errors, manifest_warnings = _manifest_findings(root, load_manifest(root))
    except (OSError, ValueError) as exc:
        manifest_errors, manifest_warnings = [f"manifest unreadable: {exc}"], []
    errors.extend(manifest_errors)
    warnings.extend(manifest_warnings)

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

    content_errors, content_warnings = _content_findings(root)
    errors.extend(content_errors)
    warnings.extend(content_warnings)
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


def _content_findings(root: Path) -> tuple[List[str], List[str]]:
    """Check explicit Markdown file links and sync conflict copies.

    Missing Markdown targets and iCloud-style conflict copies are errors; other
    findings stay warnings. Code examples, URLs and anchor-only links are skipped.
    """
    import os
    from urllib.parse import unquote, urlsplit
    findings = []
    problems = []
    excluded = {"__pycache__", ".git", "node_modules", ".venv", ".pytest_cache"}
    for directory, dirs, files in os.walk(root, followlinks=False):
        names = set(files) | set(dirs)
        for name in list(files) + list(dirs):
            match = ICLOUD_CONFLICT.match(name)
            if match and f"{match.group('stem')}{match.group('suffix') or ''}" in names:
                rel = (Path(directory) / name).relative_to(root).as_posix()
                problems.append(f"possible sync conflict copy: {rel}")
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
                    message = f"broken local link: {path.relative_to(root).as_posix()} -> {value}"
                    (problems if value.lower().endswith(".md") else findings).append(message)
    return sorted(set(problems)), sorted(set(findings))


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
    parser.add_argument(
        "--write-manifest",
        action="store_true",
        help="Record the current complete skill set as the expected manifest. "
        "Use only after an approved install, update or retirement.",
    )
    args = parser.parse_args()

    if args.root:
        root = Path(args.root).expanduser()
    else:
        resolved = resolve_skills_root()
        if not resolved.get("ok"):
            print(json.dumps(resolved, ensure_ascii=False, indent=2), file=sys.stderr)
            return 1
        root = Path(str(resolved["skills_root"]))

    if args.write_manifest:
        incomplete = [
            child.name for child in sorted(root.iterdir())
            if child.is_dir() and not (child / "SKILL.md").is_file()
        ]
        if incomplete:
            print(
                "Refusing to write manifest: directories without SKILL.md: " + ", ".join(incomplete),
                file=sys.stderr,
            )
            return 1
        target = manifest_path(root)
        target.write_text(
            json.dumps(build_manifest(root), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"Wrote {target}")

    result = audit(root)
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(result))
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
