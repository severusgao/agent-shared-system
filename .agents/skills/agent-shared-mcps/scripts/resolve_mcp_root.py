#!/usr/bin/env python3
"""Resolve the shared MCP registry root for the shared Agent system."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, Optional


def _is_mcp_root(path: Path) -> bool:
    return (
        path.is_dir()
        and (path / "catalog").is_dir()
        and (path / "targets").is_dir()
        and (path / "README.md").is_file()
    )


def _system_root_from_mcp(path: Path) -> Optional[Path]:
    parts = path.parts
    if len(parts) >= 2 and parts[-2:] == (".agents", "mcp"):
        return path.parent
    return None


def _same_path(left: Path, right: Path) -> bool:
    try:
        return left.samefile(right)
    except OSError:
        return str(left.resolve()) == str(right.resolve())


def _walk_up(start: Path) -> Iterable[Path]:
    current = start.resolve()
    if current.is_file():
        current = current.parent
    yield current
    yield from current.parents


def _candidate(method: str, root: Path) -> Dict[str, Any]:
    resolved = root.resolve()
    system_root = _system_root_from_mcp(resolved)
    local_entry = Path.home() / ".agents" / "mcp"
    local_resolved = None
    local_matches = None
    if local_entry.exists() or local_entry.is_symlink():
        try:
            local_resolved = local_entry.resolve()
            local_matches = _same_path(local_resolved, resolved)
        except OSError:
            local_matches = False
    return {
        "ok": True,
        "method": method,
        "mcp_root": str(resolved),
        "shared_system_root": str(system_root) if system_root else None,
        "local_entry": str(local_entry),
        "local_resolved": str(local_resolved) if local_resolved else None,
        "local_entry_matches": local_matches,
    }


def resolve_mcp_root(start: Optional[Path] = None) -> Dict[str, Any]:
    start = start or Path.cwd()
    if _is_mcp_root(start.expanduser()):
        return _candidate("explicit_mcp_root", start.expanduser())

    script_path = Path(__file__).resolve()
    for parent in script_path.parents:
        if parent.name == ".agents":
            candidate = parent / "mcp"
            if _is_mcp_root(candidate):
                return _candidate("skill_real_path", candidate)

    for parent in _walk_up(start):
        candidate = parent / ".agents" / "mcp"
        if _is_mcp_root(candidate):
            return _candidate("cwd_upward_search", candidate)

    system_root = os.environ.get("AGENT_SHARED_SYSTEM_ROOT")
    if system_root:
        candidate = Path(system_root).expanduser() / "mcp"
        if _is_mcp_root(candidate):
            return _candidate("AGENT_SHARED_SYSTEM_ROOT", candidate)

    env_root = os.environ.get("AGENT_SHARED_MCPS_ROOT")
    if env_root:
        candidate = Path(env_root).expanduser()
        if _is_mcp_root(candidate):
            return _candidate("AGENT_SHARED_MCPS_ROOT", candidate)

    local_entry = Path.home() / ".agents" / "mcp"
    if local_entry.exists() or local_entry.is_symlink():
        try:
            candidate = local_entry.resolve()
            if _is_mcp_root(candidate):
                return _candidate("local_discovery_entry", candidate)
        except OSError:
            pass

    return {
        "ok": False,
        "error": "shared MCP root not found",
        "hint": "Run from the shared system root, set AGENT_SHARED_SYSTEM_ROOT or AGENT_SHARED_MCPS_ROOT, or run the MCP sync launcher.",
    }


def render_markdown(result: Dict[str, Any]) -> str:
    if not result.get("ok"):
        return (
            "# Shared MCP Root\n\n"
            f"- Status: error\n- Error: {result.get('error')}\n- Hint: {result.get('hint')}\n"
        )
    return "\n".join(
        [
            "# Shared MCP Root",
            "",
            "- Status: ok",
            f"- Method: `{result.get('method')}`",
            f"- MCP root: `{result.get('mcp_root')}`",
            f"- Shared system root: `{result.get('shared_system_root')}`",
            f"- Local entry: `{result.get('local_entry')}`",
            f"- Local resolved: `{result.get('local_resolved')}`",
            f"- Local entry matches: `{result.get('local_entry_matches')}`",
            "",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default=None, help="Optional start path for upward discovery.")
    parser.add_argument("--format", choices=["json", "markdown"], default="json")
    args = parser.parse_args()

    result = resolve_mcp_root(Path(args.start).expanduser() if args.start else None)
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.format == "json" else render_markdown(result))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
