#!/usr/bin/env python3
"""Resolve the shared memories root for the shared Agent system."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional


SKILL_NAME = "agent-shared-memories"


def _parents(start: Path) -> Iterable[Path]:
    current = start.expanduser().resolve()
    if current.is_file():
        current = current.parent
    yield current
    yield from current.parents


def _valid_memories_root(path: Path) -> bool:
    return path.is_dir() and (path / "INDEX.md").is_file()


def _system_root_from_memories(path: Path) -> Path | None:
    parts = path.parts
    if len(parts) >= 2 and parts[-2:] == (".agents", "memories"):
        return path.parent
    return None


def _same_path(left: Path, right: Path) -> bool:
    try:
        return left.samefile(right)
    except OSError:
        try:
            return str(left.resolve()) == str(right.resolve())
        except OSError:
            return str(left) == str(right)


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
    if path.is_dir():
        return "directory"
    if path.is_file():
        return "file"
    return "missing"


def _entry_target(path: Path, kind: str) -> Optional[str]:
    if kind == "symlink":
        try:
            return os.readlink(path)
        except OSError:
            return None
    if kind == "junction":
        try:
            return str(path.resolve())
        except OSError:
            return None
    return None


def _runtime_environment(
    env: Mapping[str, str],
    *,
    sys_platform_name: str | None = None,
    os_name_value: str | None = None,
) -> dict[str, Any]:
    sys_platform = (sys_platform_name or sys.platform).casefold()
    os_name = (os_name_value or os.name).casefold()
    wsl_distro = env.get("WSL_DISTRO_NAME") or None

    if wsl_distro:
        platform = "wsl"
    elif sys_platform == "darwin":
        platform = "macos"
    elif os_name == "nt" or sys_platform.startswith("win"):
        platform = "windows"
    else:
        platform = "linux"

    return {
        "platform": platform,
        "sys_platform": sys_platform,
        "os_name": os_name,
        "wsl_distro": wsl_distro,
    }


def describe_local_entry(home: Path | None = None) -> dict[str, Any]:
    home = (home or Path.home()).expanduser()
    entry = home / ".agents" / "memories"
    kind = _entry_kind(entry)
    target = _entry_target(entry, kind)
    resolved: Optional[Path] = None
    warnings: list[str] = []

    if kind in {"symlink", "junction"}:
        try:
            resolved_candidate = entry.resolve(strict=True)
            resolved = resolved_candidate if _valid_memories_root(resolved_candidate) else None
            if resolved is None:
                warnings.append("broken local stable entry")
        except OSError:
            warnings.append("broken local stable entry")

    return {
        "local_entry": str(entry),
        "local_entry_kind": kind,
        "local_entry_target": target,
        "local_entry_resolved": str(resolved) if resolved else None,
        "local_entry_valid": bool(resolved),
        "warnings": warnings,
    }


def _candidate_from_cwd(start: Path) -> tuple[str, Path] | None:
    expanded = start.expanduser()
    if _valid_memories_root(expanded):
        return "explicit-memories-root", expanded.resolve()
    for parent in _parents(expanded):
        candidate = parent / ".agents" / "memories"
        if _valid_memories_root(candidate):
            return "cwd-upward", candidate.resolve()
    return None


def _candidate_from_skill() -> tuple[str, Path] | None:
    script_path = Path(__file__).resolve()
    skill_root = script_path.parents[1]
    if (
        skill_root.name == SKILL_NAME
        and (skill_root / "SKILL.md").is_file()
        and skill_root.parent.name == "skills"
        and skill_root.parent.parent.name == ".agents"
    ):
        candidate = skill_root.parent.parent / "memories"
        if _valid_memories_root(candidate):
            return "skill-realpath", candidate.resolve()
    return None


def _candidate_from_agent_root(env: Mapping[str, str]) -> tuple[str, Path] | None:
    root = env.get("AGENT_SHARED_MEMORIES_ROOT")
    if root:
        candidate = Path(root).expanduser()
        if _valid_memories_root(candidate):
            return "AGENT_SHARED_MEMORIES_ROOT", candidate.resolve()
    return None


def _candidate_from_system_root(env: Mapping[str, str]) -> tuple[str, Path] | None:
    root = env.get("AGENT_SHARED_SYSTEM_ROOT")
    if root:
        candidate = Path(root).expanduser() / "memories"
        if _valid_memories_root(candidate):
            return "AGENT_SHARED_SYSTEM_ROOT", candidate.resolve()
    return None


def _candidate_from_local_entry(local_info: Mapping[str, Any]) -> tuple[str, Path] | None:
    resolved = local_info.get("local_entry_resolved")
    if resolved:
        return "local-stable-entry", Path(str(resolved)).resolve()
    return None


def _result_payload(
    method: str,
    memories_root: Path,
    runtime: Mapping[str, Any],
    local_info: Mapping[str, Any],
    warnings: list[str],
    checked: list[str],
) -> dict[str, Any]:
    resolved_root = memories_root.resolve()
    system_root = _system_root_from_memories(resolved_root)
    skill_real = Path(__file__).resolve().parents[1]
    local_resolved = local_info.get("local_entry_resolved")
    local_matches = None
    if local_resolved:
        local_matches = _same_path(Path(str(local_resolved)), resolved_root)
    return {
        "ok": True,
        "method": method,
        "platform": runtime.get("platform"),
        "sys_platform": runtime.get("sys_platform"),
        "os_name": runtime.get("os_name"),
        "wsl_distro": runtime.get("wsl_distro"),
        "memories_root": str(resolved_root),
        "shared_system_root": str(system_root) if system_root else None,
        "skill_real_path": str(skill_real),
        "local_entry": local_info.get("local_entry"),
        "local_entry_kind": local_info.get("local_entry_kind"),
        "local_entry_target": local_info.get("local_entry_target"),
        "local_entry_resolved": local_resolved,
        "local_entry_matches_root": local_matches,
        "warnings": warnings,
        "checked": checked,
    }


def resolve(
    start: Path | None = None,
    home: Path | None = None,
    env: Mapping[str, str] | None = None,
    sys_platform_name: str | None = None,
    os_name_value: str | None = None,
) -> dict[str, Any]:
    start = start or Path.cwd()
    env = os.environ if env is None else env
    runtime = _runtime_environment(
        env,
        sys_platform_name=sys_platform_name,
        os_name_value=os_name_value,
    )
    local_info = describe_local_entry(home=home)
    warnings = list(local_info.get("warnings", []))
    checked: list[str] = []

    for label, finder in (
        ("cwd-upward", lambda: _candidate_from_cwd(start)),
        ("skill-realpath", _candidate_from_skill),
        ("AGENT_SHARED_MEMORIES_ROOT", lambda: _candidate_from_agent_root(env)),
        ("AGENT_SHARED_SYSTEM_ROOT", lambda: _candidate_from_system_root(env)),
        ("local-stable-entry", lambda: _candidate_from_local_entry(local_info)),
    ):
        checked.append(label)
        result = finder()
        if result:
            method, memories_root = result
            return _result_payload(method, memories_root, runtime, local_info, warnings, checked)

    return {
        "ok": False,
        "error": "Shared memories root not found.",
        "hint": (
            "Run from the shared system root, keep this skill in the shared system, "
            "set AGENT_SHARED_SYSTEM_ROOT or AGENT_SHARED_MEMORIES_ROOT, "
            "or create ~/.agents/memories."
        ),
        "platform": runtime.get("platform"),
        "sys_platform": runtime.get("sys_platform"),
        "os_name": runtime.get("os_name"),
        "wsl_distro": runtime.get("wsl_distro"),
        "local_entry": local_info.get("local_entry"),
        "local_entry_kind": local_info.get("local_entry_kind"),
        "local_entry_target": local_info.get("local_entry_target"),
        "local_entry_resolved": local_info.get("local_entry_resolved"),
        "warnings": warnings,
        "checked": checked,
    }


def ensure_local_entry(
    canonical_root: Path,
    *,
    home: Path | None = None,
    apply: bool = False,
    yes: bool = False,
) -> dict[str, Any]:
    canonical_root = canonical_root.expanduser().resolve()
    home = (home or Path.home()).expanduser()
    local_info = describe_local_entry(home=home)
    entry = Path(str(local_info["local_entry"]))
    kind = str(local_info["local_entry_kind"])
    resolved = local_info.get("local_entry_resolved")

    result = {
        "entry": str(entry),
        "entry_kind": kind,
        "entry_target": local_info.get("local_entry_target"),
        "canonical_root": str(canonical_root),
        "apply_requested": apply,
        "yes_requested": yes,
        "action": "skip",
        "reason": "",
        "performed": False,
    }

    if not _valid_memories_root(canonical_root):
        result["action"] = "conflict"
        result["reason"] = f"canonical memories root is invalid: {canonical_root}"
        return result

    if kind == "missing":
        result["action"] = "create"
        result["reason"] = "local stable entry is missing"
        if apply and yes:
            entry.parent.mkdir(parents=True, exist_ok=True)
            entry.symlink_to(canonical_root, target_is_directory=True)
            result["performed"] = True
            result["entry_kind"] = "symlink"
            result["entry_target"] = str(canonical_root)
        return result

    if kind in {"symlink", "junction"} and resolved:
        if _same_path(Path(str(resolved)), canonical_root):
            result["action"] = "skip"
            result["reason"] = "local stable entry already matches canonical root"
            return result

    result["action"] = "conflict"
    if kind in {"symlink", "junction"}:
        result["reason"] = "local stable entry points elsewhere or is broken"
    else:
        result["reason"] = "real file or directory occupies local stable entry"
    return result


def render_markdown(data: Mapping[str, Any]) -> str:
    lines = ["# Shared Memories Root", ""]
    if data.get("ok"):
        lines.extend(
            [
                "- Status: ok",
                f"- Method: `{data.get('method')}`",
                f"- Platform: `{data.get('platform')}`",
                f"- sys.platform: `{data.get('sys_platform')}`",
                f"- os.name: `{data.get('os_name')}`",
                f"- WSL distro: `{data.get('wsl_distro')}`",
                f"- Memories root: `{data.get('memories_root')}`",
                f"- Vault root: `{data.get('vault_root')}`",
                f"- Skill real path: `{data.get('skill_real_path')}`",
                f"- Local entry: `{data.get('local_entry')}`",
                f"- Local entry kind: `{data.get('local_entry_kind')}`",
                f"- Local entry target: `{data.get('local_entry_target')}`",
                f"- Local entry resolved: `{data.get('local_entry_resolved')}`",
                f"- Local entry matches root: `{data.get('local_entry_matches_root')}`",
            ]
        )
    else:
        lines.extend(
            [
                "- Status: error",
                f"- Error: {data.get('error')}",
                f"- Hint: {data.get('hint')}",
                f"- Platform: `{data.get('platform')}`",
                f"- sys.platform: `{data.get('sys_platform')}`",
                f"- os.name: `{data.get('os_name')}`",
                f"- WSL distro: `{data.get('wsl_distro')}`",
                f"- Local entry: `{data.get('local_entry')}`",
                f"- Local entry kind: `{data.get('local_entry_kind')}`",
                f"- Local entry target: `{data.get('local_entry_target')}`",
                f"- Local entry resolved: `{data.get('local_entry_resolved')}`",
            ]
        )

    warnings = list(data.get("warnings") or [])
    lines.extend(["", "## Warnings"])
    if warnings:
        lines.extend(f"- {warning}" for warning in warnings)
    else:
        lines.append("- none")

    ensure = data.get("ensure_local_entry")
    if isinstance(ensure, Mapping):
        lines.extend(
            [
                "",
                "## Local Entry Plan",
                f"- Action: `{ensure.get('action')}`",
                f"- Entry: `{ensure.get('entry')}`",
                f"- Entry kind: `{ensure.get('entry_kind')}`",
                f"- Entry target: `{ensure.get('entry_target')}`",
                f"- Canonical root: `{ensure.get('canonical_root')}`",
                f"- Reason: {ensure.get('reason')}",
                f"- Write: {'applied' if ensure.get('performed') else 'skipped (requires both --apply and --yes)'}",
            ]
        )

    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default=None, help="Optional start path for upward discovery.")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    parser.add_argument(
        "--ensure-local-entry",
        action="store_true",
        help="Preview or create ~/.agents/memories for the resolved canonical root.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Allow writes when used together with --yes.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirm the write when used together with --apply.",
    )
    args = parser.parse_args()

    start = Path(args.start).expanduser() if args.start else None
    data = resolve(start=start)
    if args.ensure_local_entry and data.get("ok"):
        data["ensure_local_entry"] = ensure_local_entry(
            Path(str(data["memories_root"])),
            apply=args.apply,
            yes=args.yes,
        )

    if args.format == "json":
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(data))
    return 0 if data.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
