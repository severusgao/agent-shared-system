#!/usr/bin/env python3
"""Audit or deploy local unified skills into each Agent skill directory."""

from __future__ import annotations

import argparse
import copy
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath
from typing import Any, Dict, Iterable, List, Optional, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
SHARED_SCRIPTS_DIR = SCRIPT_DIR.parents[2] / "scripts"
sys.path.insert(0, str(SHARED_SCRIPTS_DIR))
sys.path.insert(0, str(SCRIPT_DIR))

from resolve_skills_root import resolve_skills_root  # noqa: E402
from shared_environment import (  # noqa: E402
    EnvironmentIdentity,
    atomic_update_json,
    build_environment_identity,
    detect_environment,
    normalize_identity_part,
)


DEFAULT_REGISTRY = SCRIPT_DIR.parent / "references" / "agent_targets.json"
DEFAULT_STATE = SCRIPT_DIR.parent / "state" / "agent_skill_instances.json"
STATE_DEFAULT = {
    "version": 2,
    "updated": None,
    "instances": [],
}


def current_environment() -> EnvironmentIdentity:
    return detect_environment()


def registry_platform_key(platform_name: str) -> str:
    return "linux" if platform_name == "wsl" else platform_name


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def normalize_text_arg(value: str) -> str:
    stripped = value.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in {"'", '"'}:
        stripped = stripped[1:-1].strip()
    return stripped


def normalize_agent_id(value: Optional[str], root: Optional[Path] = None) -> str:
    raw = normalize_text_arg(value or "")
    if not raw and root:
        name = root.name
        if name.lower() in {"skill", "skills"} or name.lower().startswith("skills-"):
            name = root.parent.name
        raw = name
    if not raw:
        raw = "custom-agent"
    chars: List[str] = []
    previous_dash = False
    for char in raw.lower():
        if char.isalnum():
            chars.append(char)
            previous_dash = False
        elif not previous_dash:
            chars.append("-")
            previous_dash = True
    normalized = "".join(chars).strip("-")
    return normalized or "custom-agent"


def default_strategy(platform_name: str) -> str:
    return "junction" if platform_name == "windows" else "symlink"


def expand_template(value: str) -> Path:
    value = normalize_text_arg(value)
    home = str(Path.home())
    replacements = {
        "$HOME": home,
        "${HOME}": home,
        "%USERPROFILE%": os.environ.get("USERPROFILE", home),
        "%HOME%": os.environ.get("HOME", home),
    }
    expanded = value
    for key, replacement in replacements.items():
        expanded = expanded.replace(key, replacement)
    expanded = os.path.expandvars(os.path.expanduser(expanded))
    return Path(expanded)


def normalize_target_dir(
    value: str,
    known_skill_names: Optional[Iterable[str]] = None,
) -> Tuple[Path, Optional[str]]:
    path = expand_template(value).absolute()
    warning = None
    known = set(known_skill_names or [])

    if (path / "SKILL.md").is_file() or path.name in known:
        warning = (
            f"target directory looked like one skill entry (`{path}`); "
            f"using its parent skills directory (`{path.parent}`)"
        )
        path = path.parent

    return path, warning


def same_path(left: Path, right: Path) -> bool:
    try:
        return left.samefile(right)
    except OSError:
        try:
            return str(left.resolve()) == str(right.resolve())
        except OSError:
            return str(left) == str(right)


def is_link_like(path: Path) -> bool:
    if path.is_symlink():
        return True
    isjunction = getattr(os.path, "isjunction", None)
    if callable(isjunction):
        try:
            return bool(isjunction(path))
        except OSError:
            return False
    return False


def read_link_target(path: Path) -> Optional[str]:
    if path.is_symlink():
        try:
            return os.readlink(path)
        except OSError:
            return None
    if os.name == "nt" and is_link_like(path):
        try:
            return str(path.resolve())
        except OSError:
            return None
    return None


def has_skill_md(path: Path) -> bool:
    return (path / "SKILL.md").is_file()


def skill_names(root: Path) -> List[str]:
    if not root.is_dir():
        return []
    return sorted(
        child.name for child in root.iterdir() if child.is_dir() and has_skill_md(child)
    )


def classify_local_unified(
    shared_root: Path,
    local_root: Path,
    shared: List[str],
) -> Dict[str, Any]:
    local = skill_names(local_root)
    local_set = set(local)
    shared_set = set(shared)
    syncable: List[str] = []
    missing: List[str] = []
    mismatched: List[Dict[str, str]] = []

    for name in shared:
        local_entry = local_root / name
        shared_entry = shared_root / name
        if name not in local_set:
            missing.append(name)
            continue
        try:
            resolved = local_entry.resolve()
        except OSError:
            resolved = local_entry
        if same_path(resolved, shared_entry):
            syncable.append(name)
        else:
            mismatched.append(
                {
                    "skill": name,
                    "local_entry": str(local_entry),
                    "expected": str(shared_entry),
                    "resolved": str(resolved),
                }
            )

    return {
        "all_local": local,
        "syncable": syncable,
        "missing": missing,
        "mismatched": mismatched,
        "extras": sorted(local_set - shared_set),
    }


def load_registry(path: Path, platform_name: str) -> List[Dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    registry_key = registry_platform_key(platform_name)
    targets: List[Dict[str, Any]] = []
    for raw in data.get("targets", []):
        if not raw.get("enabled", True) or not raw.get("supports_skills", True):
            continue
        skill_dirs = raw.get("skill_dirs", {}).get(registry_key, [])
        strategy = raw.get("link_strategy", {}).get(registry_key) or default_strategy(
            platform_name
        )
        if not skill_dirs:
            targets.append(
                {
                    "id": raw.get("id"),
                    "label": raw.get("label") or raw.get("id"),
                    "root": None,
                    "strategy": strategy,
                    "status": "unsupported_platform",
                    "source": "registry",
                }
            )
            continue
        roots = [expand_template(item) for item in skill_dirs]
        targets.append(
            {
                "id": raw.get("id"),
                "label": raw.get("label") or raw.get("id"),
                "root": roots[0],
                "strategy": strategy,
                "status": "configured",
                "source": "registry",
            }
        )
    return targets


def _default_state() -> Dict[str, Any]:
    return copy.deepcopy(STATE_DEFAULT)


def _raw_state(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return _default_state()
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"state file must contain an object: {path}")
    return data


def _legacy_user(platform_name: str, home: str) -> str:
    if platform_name == "windows":
        return PureWindowsPath(home).name or "unknown-user"
    return Path(home).name or "unknown-user"


def instance_key(item: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(item.get("environment_id") or "legacy"),
        str(item.get("agent_id") or "recorded-agent"),
        str(item.get("skills_dir") or ""),
    )


def normalize_state(data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("state must be a JSON object")

    raw_instances = data.get("instances", [])
    if raw_instances is None:
        raw_instances = []
    if not isinstance(raw_instances, list):
        raise ValueError("state.instances must be a list")

    normalized: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_instances):
        if not isinstance(raw, dict):
            raise ValueError(f"state.instances[{index}] must be an object")
        item = dict(raw)
        item.setdefault("label", item.get("agent_id") or "Recorded Agent")
        if item.get("machine") and not item.get("machine_display"):
            item["machine_display"] = item.get("machine")

        if not item.get("environment_id"):
            platform_name = str(item.get("platform") or "unknown").casefold()
            machine = str(
                item.get("machine_display") or item.get("machine") or "unknown-machine"
            )
            home = str(item.get("home") or "")
            user = str(item.get("user") or _legacy_user(platform_name, home))
            if platform_name in {"macos", "windows", "linux"}:
                item["environment_id"] = build_environment_identity(
                    platform_name,
                    machine,
                    user,
                    home,
                ).environment_id
            else:
                item["environment_id"] = (
                    f"legacy:{normalize_identity_part(machine)}:"
                    f"{normalize_identity_part(user)}"
                )
            item["status"] = "legacy"
        normalized.append(item)

    return {
        "version": 2,
        "updated": data.get("updated"),
        "instances": normalized,
    }


def load_state(path: Path) -> Dict[str, Any]:
    return normalize_state(_raw_state(path))


def classify_records(
    instances: list[dict[str, Any]],
    current: EnvironmentIdentity,
) -> list[dict[str, Any]]:
    current_keys = {
        (str(item.get("agent_id")), str(item.get("skills_dir")))
        for item in instances
        if item.get("environment_id") == current.environment_id
    }
    classified: list[dict[str, Any]] = []
    for raw in instances:
        item = dict(raw)
        if item.get("environment_id") == current.environment_id:
            item["status"] = "current"
        elif (
            item.get("status") == "legacy"
            and (str(item.get("agent_id")), str(item.get("skills_dir"))) in current_keys
        ):
            item["status"] = "superseded_candidate"
        elif item.get("status") == "legacy":
            item["status"] = "legacy"
        else:
            item["status"] = "other_environment"
        classified.append(item)
    return classified


def state_item_to_target(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("agent_id") or "recorded-agent",
        "label": item.get("label") or item.get("agent_id") or "Recorded Agent",
        "root": Path(str(item["skills_dir"])),
        "strategy": item.get("link_strategy")
        or default_strategy(str(item.get("platform") or "linux")),
        "status": "recorded",
        "source": "state",
        "environment_id": item.get("environment_id"),
        "record_status": item.get("status"),
        "platform": item.get("platform"),
        "machine_display": item.get("machine_display") or item.get("machine"),
        "wsl_distro": item.get("wsl_distro"),
    }


def classified_state_records(
    state_path: Path,
    current: EnvironmentIdentity,
) -> list[dict[str, Any]]:
    state = load_state(state_path)
    return classify_records(state["instances"], current)


def recorded_targets(state_path: Path, current: EnvironmentIdentity) -> list[dict[str, Any]]:
    instances = classified_state_records(state_path, current)
    return [
        state_item_to_target(item)
        for item in instances
        if item.get("status") == "current" and item.get("skills_dir")
    ]


def dedupe_targets(targets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: set[Tuple[str, str]] = set()
    deduped: List[Dict[str, Any]] = []
    for target in targets:
        root = target.get("root")
        key = (str(target.get("id")), str(root) if root else "")
        if key in seen:
            continue
        seen.add(key)
        deduped.append(target)
    return deduped


def build_direct_target(
    target_dir: str,
    target_id: Optional[str],
    target_label: Optional[str],
    strategy: Optional[str],
    current_platform: str,
    known_skill_names: Iterable[str],
) -> Tuple[Dict[str, Any], Optional[str]]:
    root, warning = normalize_target_dir(target_dir, known_skill_names)
    agent_id = normalize_agent_id(target_id, root)
    return (
        {
            "id": agent_id,
            "label": target_label or agent_id,
            "root": root,
            "strategy": strategy or default_strategy(current_platform),
            "status": "direct",
            "source": "direct",
        },
        warning,
    )


def local_unified_root(default_root: Optional[str]) -> Path:
    if default_root:
        return Path(default_root).expanduser().resolve()
    return Path.home() / ".agents" / "skills"


def plan_entry(agent_root: Path, local_root: Path, skill: str, replace_local: bool = False) -> Dict[str, Any]:
    agent_entry = agent_root / skill
    local_entry = local_root / skill
    row: Dict[str, Any] = {
        "skill": skill,
        "agent_entry": str(agent_entry),
        "expected": str(local_entry),
        "existing_target": None,
        "plan": "unknown",
        "reason": "",
    }

    row["observed"] = entry_snapshot(agent_entry)
    if not os.path.lexists(agent_entry):
        row["plan"] = "create"
        row["reason"] = "missing from agent skill directory"
        return row

    if is_link_like(agent_entry):
        row["existing_target"] = read_link_target(agent_entry)
        try:
            resolved = agent_entry.resolve()
            if same_path(resolved, local_entry):
                row["plan"] = "skip"
                row["reason"] = "already resolves to local unified skill"
            else:
                row["plan"] = "relink"
                row["reason"] = "existing link points elsewhere"
        except OSError:
            row["plan"] = "relink"
            row["reason"] = "existing link cannot be resolved"
        return row

    if agent_entry.is_dir():
        row["plan"] = "replace-local" if replace_local else "conflict"
        row["reason"] = "real directory exists in agent skill directory"
        return row

    row["plan"] = "conflict"
    row["reason"] = "non-directory file exists in agent skill directory"
    return row


def _record_metadata(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": item.get("status"),
        "environment_id": item.get("environment_id"),
        "agent_id": item.get("agent_id"),
        "label": item.get("label"),
        "platform": item.get("platform"),
        "machine_display": item.get("machine_display") or item.get("machine"),
        "wsl_distro": item.get("wsl_distro"),
        "skills_dir": item.get("skills_dir"),
        "link_strategy": item.get("link_strategy"),
        "source": item.get("source"),
    }


def audit(
    shared_root: Path,
    local_root: Path,
    registry: Path,
    state_path: Path,
    agents_filter: Optional[List[str]],
    skills_filter: Optional[List[str]],
    use_registry: bool,
    include_recorded: bool,
    all_recorded: bool = False,
    direct_target: Optional[Dict[str, Any]] = None,
    target_warnings: Optional[List[str]] = None,
    create_roots: bool = False,
    replace_local: bool = False,
) -> Dict[str, Any]:
    current = current_environment()
    targets = load_registry(registry, current.platform) if use_registry else []

    classified_records: List[dict[str, Any]] = []
    if include_recorded or all_recorded:
        classified_records = classified_state_records(state_path, current)
    if include_recorded:
        targets.extend(
            state_item_to_target(item)
            for item in classified_records
            if item.get("status") == "current" and item.get("skills_dir")
        )
    if direct_target:
        targets.append(direct_target)
    targets = dedupe_targets(targets)
    if agents_filter:
        wanted = {item.strip() for item in agents_filter if item.strip()}
        targets = [target for target in targets if str(target.get("id")) in wanted]

    shared = skill_names(shared_root)
    local_state = classify_local_unified(shared_root, local_root, shared)
    local = local_state["all_local"]
    syncable = local_state["syncable"]
    requested_missing: List[str] = []
    if skills_filter:
        wanted_skills = {item.strip() for item in skills_filter if item.strip()}
        requested_missing = sorted(wanted_skills - set(syncable))
        syncable = [name for name in syncable if name in wanted_skills]

    agent_results: List[Dict[str, Any]] = []
    for target in targets:
        root = target.get("root")
        result: Dict[str, Any] = {
            "id": target.get("id"),
            "label": target.get("label"),
            "root": str(root) if root else None,
            "strategy": target.get("strategy"),
            "source": target.get("source") or "registry",
            "environment_id": target.get("environment_id") or current.environment_id,
            "record_status": target.get("record_status"),
            "platform": target.get("platform") or current.platform,
            "machine_display": target.get("machine_display") or current.machine_display,
            "wsl_distro": target.get("wsl_distro") or current.wsl_distro,
            "root_exists": False,
            "root_action": "none",
            "status": target.get("status"),
            "skills_count": 0,
            "plans": [],
            "summary": {},
        }

        if not root:
            result["root_action"] = "skip"
            result["summary"] = {
                "create": 0,
                "skip": 0,
                "relink": 0,
                "replace-local": 0,
                "conflict": 0,
            }
            agent_results.append(result)
            continue

        root_path = Path(root)
        result["root_exists"] = root_path.is_dir()
        if not root_path.is_dir():
            result["root_action"] = "create-root" if create_roots else "skip-missing-root"
            if create_roots:
                plans = [plan_entry(root_path, local_root, skill, replace_local) for skill in syncable]
                result["plans"] = plans
                result["summary"] = {
                    "create": len(plans),
                    "skip": 0,
                    "relink": 0,
                    "replace-local": 0,
                    "conflict": 0,
                }
            else:
                result["summary"] = {
                    "create": 0,
                    "skip": 0,
                    "relink": 0,
                    "replace-local": 0,
                    "conflict": 0,
                }
            agent_results.append(result)
            continue

        plans = [plan_entry(root_path, local_root, skill, replace_local) for skill in syncable]
        counts: Dict[str, int] = {}
        for item in plans:
            counts[item["plan"]] = counts.get(item["plan"], 0) + 1
        result["skills_count"] = len(skill_names(root_path))
        result["plans"] = plans
        result["summary"] = counts
        agent_results.append(result)

    return {
        "ok": True,
        "replace_local": replace_local,
        "explicit_targets": bool(direct_target or agents_filter),
        "explicit_skills": bool(skills_filter),
        "unknown_agents": sorted(set(agents_filter or []) - {str(t.get("id")) for t in targets}),
        "environment_id": current.environment_id,
        "platform": current.platform,
        "machine": current.machine_display,
        "machine_display": current.machine_display,
        "wsl_distro": current.wsl_distro,
        "shared_root": str(shared_root.resolve()),
        "local_unified_root": str(local_root),
        "local_unified_exists": local_root.is_dir(),
        "registry": str(registry),
        "use_registry": use_registry,
        "state_file": str(state_path),
        "include_recorded": include_recorded,
        "all_recorded": all_recorded,
        "target_warnings": target_warnings or [],
        "shared_skill_count": len(shared),
        "local_unified_skill_count": len(local),
        "local_unified_shared_skill_count": len(syncable),
        "local_missing_from_shared": local_state["missing"],
        "local_shared_mismatched": local_state["mismatched"],
        "local_extra_not_in_shared": local_state["extras"],
        "requested_skills_unavailable": requested_missing,
        "recorded_instances": [_record_metadata(item) for item in classified_records]
        if all_recorded
        else [],
        "agents": agent_results,
    }


def remove_link(path: Path) -> None:
    if path.is_symlink():
        path.unlink()
        return
    if os.name == "nt" and is_link_like(path):
        os.rmdir(path)
        return
    raise RuntimeError(f"not a link: {path}")


def create_link(link_path: Path, target_path: Path, strategy: Optional[str]) -> None:
    link_path.parent.mkdir(parents=True, exist_ok=True)
    if os.name == "nt" and strategy == "junction":
        completed = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link_path), str(target_path)],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or completed.stdout.strip())
        return
    link_path.symlink_to(target_path, target_is_directory=True)


class LinkApplyError(RuntimeError):
    pass


def entry_snapshot(path: Path) -> tuple:
    if not os.path.lexists(path):
        return ("missing",)
    stat = path.lstat()
    return ("link" if is_link_like(path) else "real", stat.st_dev, stat.st_ino,
            stat.st_mtime_ns, os.readlink(path) if is_link_like(path) else None)


def plan_problems(result: Dict[str, Any]) -> list[str]:
    problems = []
    for key in ("requested_skills_unavailable", "unknown_agents"):
        if result.get(key):
            problems.append(f"{key}: {', '.join(result[key])}")
    for agent in result.get("agents", []):
        if agent.get("root_action") in {"skip-missing-root", "skip"}:
            problems.append(f"Unavailable target: {agent['id']}")
        for plan in agent.get("plans", []):
            if plan["plan"] == "conflict":
                problems.append(f"Conflict: {plan['agent_entry']}")
    return problems


def apply_plans(result: Dict[str, Any], backup_root: Path, assume_yes: bool) -> List[str]:
    if not result.get("explicit_targets"):
        raise LinkApplyError("Apply requires --target-dir or --agents")
    if result.get("replace_local") and not result.get("explicit_skills"):
        raise LinkApplyError("--replace-local requires --skills")
    problems = plan_problems(result)
    if problems:
        raise LinkApplyError("; ".join(problems))
    pending = [(agent, plan) for agent in result["agents"]
               for plan in agent.get("plans", []) if plan["plan"] != "skip"]
    roots = [Path(a["root"]) for a in result["agents"] if a.get("root_action") == "create-root"]
    if not pending and not roots:
        return ["No changes needed."]
    snapshots = {str(Path(p["agent_entry"])): p.get("observed", entry_snapshot(Path(p["agent_entry"]))) for _, p in pending}
    if not assume_yes and input(f"Apply {len(pending)} planned link change(s)? Type Y to continue: ").strip().lower() != "y":
        return ["Cancelled. No links were changed."]
    import uuid
    backup_dir = backup_root.resolve() / (datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8])
    journal = []
    created_roots = []
    messages = []
    try:
        for root in roots:
            ancestors = []
            current = root
            while not current.exists():
                ancestors.append(current)
                current = current.parent
            for directory in reversed(ancestors):
                directory.mkdir()
                created_roots.append(directory)
        for index, (agent, plan) in enumerate(pending):
            entry = Path(plan["agent_entry"])
            expected = Path(plan["expected"])
            if entry_snapshot(entry) != snapshots[str(entry)]:
                raise LinkApplyError(f"Target changed after preview: {entry}")
            fresh = plan_entry(entry.parent, expected.parent, plan["skill"], result.get("replace_local", False))
            if fresh["plan"] != plan["plan"] or not (expected / "SKILL.md").is_file():
                raise LinkApplyError(f"Plan or source changed: {entry}")
            original = None
            if plan["plan"] in {"relink", "replace-local"}:
                if backup_dir == entry.resolve() or entry.resolve() in backup_dir.parents:
                    raise LinkApplyError(f"Backup must be outside target: {entry}")
                backup_dir.mkdir(parents=True, exist_ok=True)
                original = backup_dir / str(index)
                # Rename preserves junctions and relative symlinks without following them.
                os.rename(entry, original)
            record = {"entry": entry, "original": original, "created": None}
            journal.append(record)
            try:
                create_link(entry, expected, agent.get("strategy"))
            finally:
                if is_link_like(entry):
                    record["created"] = entry_snapshot(entry)
            if not is_link_like(entry) or not same_path(entry, expected):
                raise LinkApplyError(f"Link verification failed: {entry}")
            messages.append(f"Linked: {entry}" + (f"; preserved original: {original}" if original else ""))
        for agent in result["agents"]:
            for plan in agent.get("plans", []):
                if not same_path(Path(plan["agent_entry"]), Path(plan["expected"])):
                    raise LinkApplyError(f"Final verification failed: {plan['agent_entry']}")
    except (Exception, KeyboardInterrupt) as exc:
        recovery_errors = []
        for record in reversed(journal):
            entry, original = record["entry"], record["original"]
            try:
                if os.path.lexists(entry):
                    if record["created"] is None or entry_snapshot(entry) != record["created"]:
                        raise LinkApplyError("entry changed externally; preserved for manual recovery")
                    remove_link(entry)
                if original is not None:
                    os.rename(original, entry)
            except Exception as recovery:
                recovery_errors.append(f"{entry}: {recovery}; original={original}")
        for root in reversed(created_roots):
            try:
                root.rmdir()
            except OSError as recovery:
                recovery_errors.append(f"{root}: {recovery}")
        detail = "; ".join(recovery_errors) if recovery_errors else "all changes in this batch restored"
        raise LinkApplyError(f"Apply failed: {exc}. Recovery: {detail}") from exc
    return messages


def _state_default_payload() -> dict[str, Any]:
    return {
        "version": 2,
        "updated": None,
        "instances": [],
    }


def _clean_state_payload(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": data.get("version", 2),
        "updated": data.get("updated"),
        "instances": data.get("instances", []),
    }


def record_synced_instances(
    result: Dict[str, Any],
    state_path: Path,
    current: EnvironmentIdentity,
) -> List[str]:
    timestamp = now_iso()
    recorded: List[str] = []

    def update_state(raw: dict[str, Any]) -> dict[str, Any]:
        state = normalize_state(raw)
        existing: Dict[Tuple[str, str, str], Dict[str, Any]] = {
            instance_key(item): dict(item) for item in state.get("instances", [])
        }

        for agent in result.get("agents", []):
            root = agent.get("root")
            if not root or agent.get("status") == "unsupported_platform":
                continue
            root_path = Path(str(root))
            if not root_path.exists() and agent.get("root_action") != "create-root":
                continue

            summary = agent.get("summary") or {}
            key = (
                current.environment_id,
                str(agent.get("id") or "recorded-agent"),
                str(root_path),
            )
            previous = existing.get(key, {})
            item = {
                "environment_id": current.environment_id,
                "agent_id": agent.get("id"),
                "label": agent.get("label"),
                "platform": current.platform,
                "machine": current.machine_display,
                "machine_display": current.machine_display,
                "machine_key": current.machine_key,
                "user": current.user,
                "home": current.home,
                "wsl_distro": current.wsl_distro,
                "skills_dir": str(root_path),
                "link_strategy": agent.get("strategy") or default_strategy(current.platform),
                "source": agent.get("source") or "registry",
                "first_seen": previous.get("first_seen") or timestamp,
                "last_sync": timestamp,
                "last_audit": {
                    "root_exists": agent.get("root_exists"),
                    "root_action": agent.get("root_action"),
                    "shared_skill_count": result.get("shared_skill_count"),
                    "local_unified_shared_skill_count": result.get(
                        "local_unified_shared_skill_count"
                    ),
                    "skip": summary.get("skip", 0),
                    "create": summary.get("create", 0),
                    "relink": summary.get("relink", 0),
                    "replace_local": summary.get("replace-local", 0),
                    "conflict": summary.get("conflict", 0),
                },
            }
            existing[key] = item
            recorded.append(f"{agent.get('id')} -> {root_path}")

        return {
            "version": 2,
            "updated": timestamp,
            "instances": sorted(existing.values(), key=instance_key),
        }

    atomic_update_json(
        state_path,
        update_state,
        default_state=_state_default_payload(),
    )
    return recorded


def migrate_state_only(state_path: Path) -> dict[str, Any]:
    return atomic_update_json(
        state_path,
        lambda raw: normalize_state(raw),
        default_state=_state_default_payload(),
    )


def render_markdown(result: Dict[str, Any]) -> str:
    lines = [
        "# Agent Skill Link Audit",
        "",
        f"- Environment ID: `{result['environment_id']}`",
        f"- Platform: `{result['platform']}`",
        f"- Machine: `{result['machine_display']}`",
        f"- WSL distro: `{result['wsl_distro'] or 'n/a'}`",
        f"- Shared skills root: `{result['shared_root']}`",
        f"- Local unified root: `{result['local_unified_root']}`",
        f"- Local unified root exists: `{result['local_unified_exists']}`",
        f"- Registry: `{result['registry']}`",
        f"- Use registry targets: `{result['use_registry']}`",
        f"- State file: `{result['state_file']}`",
        f"- Include recorded instances: `{result['include_recorded']}`",
        f"- Show all recorded metadata: `{result['all_recorded']}`",
        f"- Shared skills: {result['shared_skill_count']}",
        f"- Local unified skills: {result['local_unified_skill_count']}",
        f"- Local unified shared-link skills managed here: {result['local_unified_shared_skill_count']}",
        "",
    ]

    if result["target_warnings"]:
        lines.extend(["## Target Warnings", ""])
        lines.extend(f"- {warning}" for warning in result["target_warnings"])
        lines.append("")

    if result["local_missing_from_shared"]:
        lines.extend(["## Local Unified Root Gaps", ""])
        lines.append("Missing from local unified root:")
        lines.extend(f"- `{name}`" for name in result["local_missing_from_shared"])
        lines.append("")
    if result["local_extra_not_in_shared"]:
        lines.extend(["## Local Unified Extras Ignored By This Script", ""])
        lines.extend(f"- `{name}`" for name in result["local_extra_not_in_shared"])
        lines.append("")
    if result["requested_skills_unavailable"]:
        lines.extend(["## Requested Skills Not Available For Sync", ""])
        lines.extend(f"- `{name}`" for name in result["requested_skills_unavailable"])
        lines.append("")
    if result["local_shared_mismatched"]:
        lines.extend(["## Local Unified Shared Skill Link Problems", ""])
        lines.extend(
            ["| Skill | Local entry | Resolves to | Expected shared skill |", "|---|---|---|---|"]
        )
        for item in result["local_shared_mismatched"]:
            lines.append(
                "| `{}` | `{}` | `{}` | `{}` |".format(
                    item["skill"],
                    item["local_entry"],
                    item["resolved"],
                    item["expected"],
                )
            )
        lines.append("")

    if result["recorded_instances"]:
        lines.extend(
            [
                "## Recorded Instances",
                "",
                "| Status | Environment | Agent | Platform | Machine | WSL distro | Skills dir |",
                "|---|---|---|---|---|---|---|",
            ]
        )
        for item in result["recorded_instances"]:
            lines.append(
                "| `{}` | `{}` | `{}` | `{}` | `{}` | `{}` | `{}` |".format(
                    item.get("status"),
                    item.get("environment_id"),
                    item.get("agent_id"),
                    item.get("platform"),
                    item.get("machine_display"),
                    item.get("wsl_distro") or "n/a",
                    item.get("skills_dir"),
                )
            )
        lines.append("")

    lines.extend(
        [
            "## Agent Targets",
            "",
            "| Agent | Source | Root exists | Root action | Agent skills | Skip | Create | Relink | Replace local | Conflict |",
            "|---|---|---:|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for agent in result["agents"]:
        summary = agent.get("summary") or {}
        lines.append(
            "| `{}` | `{}` | {} | `{}` | {} | {} | {} | {} | {} | {} |".format(
                agent["id"],
                agent.get("source"),
                "yes" if agent.get("root_exists") else "no",
                agent.get("root_action"),
                agent.get("skills_count", 0),
                summary.get("skip", 0),
                summary.get("create", 0),
                summary.get("relink", 0),
                summary.get("replace-local", 0),
                summary.get("conflict", 0),
            )
        )
    lines.append("")

    for agent in result["agents"]:
        actionable = [
            item
            for item in agent.get("plans", [])
            if item["plan"] in {"create", "relink", "replace-local", "conflict"}
        ]
        if not actionable and agent.get("root_action") == "none":
            continue
        lines.extend([f"## `{agent['id']}` Details", ""])
        lines.append(f"- Environment ID: `{agent.get('environment_id')}`")
        lines.append(f"- Platform: `{agent.get('platform')}`")
        lines.append(f"- Machine: `{agent.get('machine_display')}`")
        lines.append(f"- WSL distro: `{agent.get('wsl_distro') or 'n/a'}`")
        if agent.get("record_status"):
            lines.append(f"- Recorded status: `{agent.get('record_status')}`")
        lines.append("")
        if agent.get("root_action") != "none":
            lines.append(f"- Root: `{agent.get('root')}`")
            lines.append(f"- Root action: `{agent.get('root_action')}`")
            lines.append("")
        if actionable:
            lines.extend(["| Skill | Plan | Reason | Entry | Expected |", "|---|---|---|---|---|"])
            for item in actionable:
                lines.append(
                    "| `{}` | `{}` | {} | `{}` | `{}` |".format(
                        item["skill"],
                        item["plan"],
                        item["reason"],
                        item["agent_entry"],
                        item["expected"],
                    )
                )
            lines.append("")

    return "\n".join(lines)


def render_state_migration_markdown(
    state_path: Path,
    state: dict[str, Any],
    *,
    applied: bool,
) -> str:
    lines = [
        "# Agent Skill State Migration",
        "",
        f"- State file: `{state_path}`",
        f"- Version: `{state.get('version')}`",
        f"- Instances: {len(state.get('instances', []))}",
        f"- Write: {'applied' if applied else 'skipped (requires both --apply and --yes)'}",
        "",
    ]
    legacy = [item for item in state.get("instances", []) if item.get("status") == "legacy"]
    current_env = current_environment().environment_id
    current = [item for item in state.get("instances", []) if item.get("environment_id") == current_env]
    lines.append(f"- Current environment id: `{current_env}`")
    lines.append(f"- Current environment instances: {len(current)}")
    lines.append(f"- Legacy instances: {len(legacy)}")
    lines.append("")
    return "\n".join(lines)


def parse_agents(value: Optional[str]) -> Optional[List[str]]:
    if not value:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


def parse_skills(value: Optional[str]) -> Optional[List[str]]:
    if not value:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--shared-root",
        default=None,
        help="Shared-source skills root. Defaults to discovery.",
    )
    parser.add_argument(
        "--local-root",
        default=None,
        help="Local unified skills root. Defaults to ~/.agents/skills.",
    )
    parser.add_argument(
        "--registry",
        default=str(DEFAULT_REGISTRY),
        help="Agent target registry JSON.",
    )
    parser.add_argument(
        "--state-file",
        default=str(DEFAULT_STATE),
        help="Recorded Agent skill instance state file.",
    )
    parser.add_argument(
        "--agents",
        default=None,
        help="Comma-separated target ids to audit or deploy.",
    )
    parser.add_argument(
        "--include-recorded",
        action="store_true",
        help="Also audit Agent skill directories recorded for the current environment.",
    )
    parser.add_argument(
        "--recorded-only",
        action="store_true",
        help="Audit only Agent skill directories recorded for the current environment.",
    )
    parser.add_argument(
        "--all-recorded",
        action="store_true",
        help="Render all recorded Agent instances as metadata without probing remote paths.",
    )
    parser.add_argument(
        "--target-id", default=None, help="Direct target id used with --target-dir."
    )
    parser.add_argument(
        "--target-label",
        default=None,
        help="Direct target display label used with --target-dir.",
    )
    parser.add_argument(
        "--target-dir",
        default=None,
        help="Direct Agent skills directory to audit or deploy.",
    )
    parser.add_argument(
        "--target-strategy",
        choices=["symlink", "junction"],
        default=None,
        help="Link strategy for --target-dir.",
    )
    parser.add_argument(
        "--skills",
        default=None,
        help="Comma-separated skill names to audit or deploy. Defaults to all shared-source local unified skills.",
    )
    parser.add_argument(
        "--create-roots",
        action="store_true",
        help="Create missing Agent skill roots when applying.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply planned link changes. Without this, audit only.",
    )
    parser.add_argument(
        "--yes", action="store_true", help="Skip confirmation when --apply is set."
    )
    parser.add_argument(
        "--no-record",
        action="store_true",
        help="Do not update the Agent instance state file after --apply.",
    )
    parser.add_argument(
        "--migrate-state-only",
        action="store_true",
        help="Normalize the state file to version 2 without changing any Agent links.",
    )
    parser.add_argument(
        "--backup-root",
        default=None,
        help="Backup root for replaced real directories.",
    )
    parser.add_argument("--format", choices=["json", "markdown"], default="markdown")
    parser.add_argument("--replace-local", action="store_true", help="Explicitly back up and replace selected real directories; requires --skills and a target.")
    args = parser.parse_args()
    if args.apply and not args.migrate_state_only and not (parse_agents(args.agents) or args.target_dir):
        parser.error("--apply requires --target-dir or --agents")
    if args.replace_local and not ((parse_agents(args.agents) or args.target_dir) and parse_skills(args.skills)):
        parser.error("--replace-local requires a target and --skills")

    if args.shared_root:
        shared_root = Path(args.shared_root).expanduser()
    else:
        resolved = resolve_skills_root()
        if not resolved.get("ok"):
            print(json.dumps(resolved, ensure_ascii=False, indent=2), file=sys.stderr)
            return 1
        shared_root = Path(str(resolved["skills_root"]))

    local_root = local_unified_root(args.local_root)
    registry = Path(args.registry).expanduser()
    state_path = Path(args.state_file).expanduser()
    backup_root = (
        Path(args.backup_root).expanduser()
        if args.backup_root
        else local_root.parent / "backups" / "agent-skill-link-deploy"
    )

    if args.migrate_state_only:
        migrated = load_state(state_path)
        applied = False
        if args.apply and args.yes:
            migrated = migrate_state_only(state_path)
            applied = True
        if args.format == "json":
            print(json.dumps(_clean_state_payload(migrated), ensure_ascii=False, indent=2))
        else:
            print(render_state_migration_markdown(state_path, migrated, applied=applied))
        return 0

    current = current_environment()
    target_warnings: List[str] = []
    direct_target: Optional[Dict[str, Any]] = None
    if args.target_dir:
        direct_target, warning = build_direct_target(
            target_dir=args.target_dir,
            target_id=args.target_id,
            target_label=args.target_label,
            strategy=args.target_strategy,
            current_platform=current.platform,
            known_skill_names=skill_names(shared_root),
        )
        if warning:
            target_warnings.append(warning)
            if args.apply:
                print(f"Refusing normalized target during apply: {warning}. Pass the intended skills root explicitly.", file=sys.stderr)
                return 1
    include_recorded = args.include_recorded or args.recorded_only or args.all_recorded
    use_registry = not args.recorded_only and not (
        direct_target and not args.agents and not include_recorded
    )

    result = audit(
        shared_root=shared_root,
        local_root=local_root,
        registry=registry,
        state_path=state_path,
        agents_filter=parse_agents(args.agents),
        skills_filter=parse_skills(args.skills),
        use_registry=use_registry,
        include_recorded=include_recorded,
        all_recorded=args.all_recorded,
        direct_target=direct_target,
        target_warnings=target_warnings,
        create_roots=args.create_roots,
        replace_local=args.replace_local,
    )

    messages: List[str] = []
    if args.apply:
        try:
            messages = apply_plans(result, backup_root=backup_root, assume_yes=args.yes)
        except LinkApplyError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        result = audit(
            shared_root=shared_root,
            local_root=local_root,
            registry=registry,
            state_path=state_path,
            agents_filter=parse_agents(args.agents),
            skills_filter=parse_skills(args.skills),
            use_registry=use_registry,
            include_recorded=include_recorded,
            all_recorded=args.all_recorded,
            direct_target=direct_target,
            target_warnings=target_warnings,
            create_roots=args.create_roots,
            replace_local=args.replace_local,
        )
        if not args.no_record and not any(
            message.startswith("Cancelled") or message.startswith("Conflicts")
            for message in messages
        ):
            if plan_problems(result) or any(p["plan"] != "skip" for a in result["agents"] for p in a.get("plans", [])):
                print("Post-apply verification failed; no success state recorded", file=sys.stderr)
                return 1
            try:
                recorded = record_synced_instances(result, state_path, current)
            except Exception as exc:
                print(f"state_pending: links verified but state write failed: {exc}", file=sys.stderr)
                return 1
            if recorded:
                messages.append("Recorded Agent skill instance(s):")
                messages.extend(f"  {item}" for item in recorded)
        result["apply_messages"] = messages

    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if messages:
            print("# Apply Result\n")
            for message in messages:
                print(f"- {message}")
            print()
        print(render_markdown(result))

    return 1 if plan_problems(result) else 0


if __name__ == "__main__":
    raise SystemExit(main())
