#!/usr/bin/env python3
"""Resolve the shared skills root for the shared Agent system."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, Optional


SKILL_NAME = "agent-shared-skills"


def _is_skills_root(path: Path) -> bool:
    if not path.is_dir():
        return False
    own_skill = path / SKILL_NAME / "SKILL.md"
    if own_skill.is_file():
        return True
    try:
        return any((child / "SKILL.md").is_file() for child in path.iterdir() if child.is_dir())
    except OSError:
        return False


def _system_root_from_skills(path: Path) -> Optional[Path]:
    parts = path.parts
    if len(parts) >= 2 and parts[-2:] == (".agents", "skills"):
        return path.parent
    return None


def _candidate_result(method: str, skills_root: Path) -> Dict[str, Any]:
    resolved_root = skills_root.resolve()
    system_root = _system_root_from_skills(resolved_root)
    home = Path.home()
    global_entry = home / ".agents" / "skills" / SKILL_NAME
    global_resolved: Optional[Path] = None
    global_matches: Optional[bool] = None
    global_kind = _entry_kind(global_entry)

    if global_kind != "missing":
        try:
            global_resolved = global_entry.resolve()
            expected = resolved_root / SKILL_NAME
            global_matches = _same_path(global_resolved, expected)
        except OSError:
            global_resolved = None
            global_matches = False

    return {
        "ok": True,
        "method": method,
        "skills_root": str(resolved_root),
        "shared_system_root": str(system_root) if system_root else None,
        "global_skill_entry": str(global_entry),
        "global_entry_kind": global_kind,
        "global_skill_resolved": str(global_resolved) if global_resolved else None,
        "global_entry_matches_skill": global_matches,
    }


def _same_path(left: Path, right: Path) -> bool:
    try:
        return left.samefile(right)
    except OSError:
        return str(left.resolve()) == str(right.resolve())


def _entry_kind(path: Path) -> str:
    if path.is_symlink():
        return "symlink"
    isjunction = getattr(os.path, "isjunction", None)
    if callable(isjunction):
        try:
            if bool(isjunction(path)):
                return "junction"
        except OSError:
            pass
    if path.exists():
        return "direct"
    return "missing"


def _walk_up(start: Path) -> Iterable[Path]:
    current = start.resolve()
    if current.is_file():
        current = current.parent
    yield current
    yield from current.parents


def resolve_skills_root(start: Optional[Path] = None) -> Dict[str, Any]:
    start = start or Path.cwd()

    script_path = Path(__file__).resolve()
    for parent in script_path.parents:
        if parent.name == "skills" and parent.parent.name == ".agents" and _is_skills_root(parent):
            return _candidate_result("skill_real_path", parent)

    for parent in _walk_up(start):
        candidate = parent / ".agents" / "skills"
        if _is_skills_root(candidate):
            return _candidate_result("cwd_upward_search", candidate)

    env_root = os.environ.get("AGENT_SHARED_SKILLS_ROOT")
    if env_root:
        candidate = Path(env_root).expanduser()
        if _is_skills_root(candidate):
            return _candidate_result("AGENT_SHARED_SKILLS_ROOT", candidate)

    system_root = os.environ.get("AGENT_SHARED_SYSTEM_ROOT")
    if system_root:
        candidate = Path(system_root).expanduser() / "skills"
        if _is_skills_root(candidate):
            return _candidate_result("AGENT_SHARED_SYSTEM_ROOT", candidate)

    global_entry = Path.home() / ".agents" / "skills" / SKILL_NAME
    if global_entry.exists() or global_entry.is_symlink():
        try:
            resolved_skill = global_entry.resolve()
            candidate = resolved_skill.parent
            if _is_skills_root(candidate):
                return _candidate_result("local_discovery_entry", candidate)
        except OSError:
            pass

    return {
        "ok": False,
        "error": "shared skills root not found",
        "hint": "Run from the shared system root, set AGENT_SHARED_SYSTEM_ROOT or AGENT_SHARED_SKILLS_ROOT, or use the local discovery link.",
    }


def render_markdown(result: Dict[str, Any]) -> str:
    if not result.get("ok"):
        return f"# Shared Skills Root\n\n- Status: error\n- Error: {result.get('error')}\n- Hint: {result.get('hint')}\n"

    lines = [
        "# Shared Skills Root",
        "",
        f"- Status: ok",
        f"- Method: `{result.get('method')}`",
        f"- Skills root: `{result.get('skills_root')}`",
        f"- Shared system root: `{result.get('shared_system_root')}`",
        f"- Global skill entry: `{result.get('global_skill_entry')}`",
        f"- Global entry kind: `{result.get('global_entry_kind')}`",
        f"- Global skill resolved: `{result.get('global_skill_resolved')}`",
        f"- Global entry matches skill: `{result.get('global_entry_matches_skill')}`",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default=None, help="Optional start path for upward discovery.")
    parser.add_argument("--format", choices=["json", "markdown"], default="json")
    args = parser.parse_args()

    result = resolve_skills_root(Path(args.start).expanduser() if args.start else None)
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(result))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
