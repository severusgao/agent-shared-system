#!/usr/bin/env python3
"""Audit the shared MCP registry without modifying agent configs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

import sys

sys.dont_write_bytecode = True

from resolve_mcp_root import resolve_mcp_root
from sync_agent_mcp import (  # noqa: E402
    ALLOWED_RESOLUTION_STATUSES,
    BRIDGE_RESOLVERS,
    LOCAL_INSTALL_INFO,
    VERIFIED_COMMAND_RESOLVERS,
    _normalize_resolver,
    _spec_from_resolver,
    _target_config_path,
    mcp_instance_key,
)


REQUIRED_CATALOG_FIELDS = {"id", "server_name", "label", "description", "resolution"}
ALLOWED_PLATFORMS = {"macos", "windows", "linux", "wsl"}
ALLOWED_RESOLVERS = {LOCAL_INSTALL_INFO, *VERIFIED_COMMAND_RESOLVERS, *BRIDGE_RESOLVERS}
ALLOWED_RESOLUTION_KINDS = {"catalog_platforms", "open_design_install_info"}
ALLOWED_TARGET_STRATEGIES = {"cli", "json", "manual"}
ALLOWED_ENTRY_SHAPES = {"opencode-local"}


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def audit(root: Path | None = None) -> Dict[str, Any]:
    resolved = {"ok": True, "mcp_root": str(root.resolve())} if root else resolve_mcp_root()
    if not resolved.get("ok"):
        return {"ok": False, "errors": [resolved.get("error")], "resolver": resolved}

    mcp_root = Path(str(resolved["mcp_root"]))
    errors: List[str] = []
    warnings: List[str] = []
    catalogs: List[Dict[str, Any]] = []

    catalog_dir = mcp_root / "catalog"
    for path in sorted(catalog_dir.glob("*.json")):
        try:
            data = _load_json(path)
        except Exception as exc:  # noqa: BLE001 - report deterministic lint failure.
            errors.append(f"{path.name}: invalid JSON: {exc}")
            continue
        missing = sorted(REQUIRED_CATALOG_FIELDS - set(data))
        if missing:
            errors.append(f"{path.name}: missing fields {', '.join(missing)}")
        if data.get("id") and path.stem != data.get("id"):
            errors.append(f"{path.name}: filename does not match id `{data.get('id')}`")
        _validate_catalog(path.name, data, errors)
        if data.get("resolution", {}).get("fallback", {}).get("command") == "od":
            warnings.append(f"{path.name}: has od fallback; verify `od` is Open Design before use")
        catalogs.append(
            {
                "file": path.name,
                "id": data.get("id"),
                "server_name": data.get("server_name"),
                "label": data.get("label"),
                "safe_to_share": data.get("safe_to_share"),
            }
        )

    targets_file = mcp_root / "targets" / "agents.json"
    targets: Dict[str, Any] = {}
    if targets_file.is_file():
        try:
            targets_data = _load_json(targets_file)
            targets = targets_data.get("agents", {}) if isinstance(targets_data, dict) else {}
            _validate_targets(targets_data, mcp_root, errors)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"targets/agents.json: invalid JSON: {exc}")
    else:
        errors.append("targets/agents.json is missing")

    state_file = mcp_root / "state" / "mcp_instances.json"
    state_count = 0
    if state_file.is_file():
        try:
            state_data = _load_json(state_file)
            state_count = _validate_state(state_data, errors)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"state/mcp_instances.json: invalid JSON: {exc}")
    else:
        warnings.append("state/mcp_instances.json is missing")

    return {
        "ok": not errors,
        "resolver": resolved,
        "mcp_root": str(mcp_root),
        "catalog_count": len(catalogs),
        "catalogs": catalogs,
        "target_agents": sorted(targets.keys()),
        "state_count": state_count,
        "errors": errors,
        "warnings": warnings,
    }


def _validate_state(state_data: Any, errors: List[str]) -> int:
    if not isinstance(state_data, dict):
        errors.append("state/mcp_instances.json: state must be an object")
        return 0
    if state_data.get("version") != 2:
        errors.append("state/mcp_instances.json: version must be 2")
    instances = state_data.get("instances")
    if not isinstance(instances, list):
        errors.append("state/mcp_instances.json: instances must be a list")
        return 0
    seen_keys: set[tuple[str | None, str | None, str | None, str | None]] = set()
    for index, instance in enumerate(instances):
        prefix = f"state/mcp_instances.json: instances[{index}]"
        if not isinstance(instance, dict):
            errors.append(f"{prefix} must be an object")
            continue
        for field in ("mcp", "agent", "server_name", "environment_id"):
            _validate_required_instance_string(prefix, instance, field, errors)
        key = mcp_instance_key(instance)
        if key in seen_keys:
            errors.append(f"{prefix} duplicate instance key `{key}`")
        seen_keys.add(key)
        resolution_status = instance.get("resolution_status")
        if resolution_status not in ALLOWED_RESOLUTION_STATUSES:
            errors.append(f"{prefix} has invalid resolution_status `{resolution_status}`")
        verification = instance.get("verification")
        if not isinstance(verification, dict):
            errors.append(f"{prefix} missing verification object")
            continue
        for field in ("configured", "registered", "operational"):
            if field not in verification:
                errors.append(f"{prefix}.verification missing {field}")
        for field in ("configured", "registered"):
            if field in verification and not isinstance(verification[field], bool):
                errors.append(f"{prefix}.verification.{field} must be boolean")
        operational = verification.get("operational")
        if operational is not None and not isinstance(operational, bool):
            errors.append(f"{prefix}.verification.operational must be boolean or null")
    return len(instances)


def _validate_catalog(file_name: str, data: Any, errors: List[str]) -> None:
    if not isinstance(data, dict):
        errors.append(f"{file_name}: catalog entry must be an object")
        return
    for field in ("id", "server_name"):
        if field in data and not _non_empty_string(data.get(field)):
            errors.append(f"{file_name}: {field} must be a non-empty string")

    resolution = data.get("resolution")
    if not isinstance(resolution, dict):
        errors.append(f"{file_name}: resolution must be an object")
        resolution = {}
    kind = resolution.get("kind")
    if kind not in ALLOWED_RESOLUTION_KINDS:
        errors.append(f"{file_name}: unsupported resolution kind `{kind}`")
    fallback = resolution.get("fallback")
    if fallback is not None and not isinstance(fallback, dict):
        errors.append(f"{file_name}: resolution.fallback must be an object")
    if isinstance(fallback, dict):
        _validate_spec_shape(f"{file_name}: resolution.fallback", fallback, errors)

    platforms = data.get("platforms")
    if platforms is None:
        return
    if not isinstance(platforms, dict):
        errors.append(f"{file_name}: platforms must be an object")
        return
    for platform_name, entry in platforms.items():
        platform_prefix = f"{file_name}: platforms.{platform_name}"
        if platform_name not in ALLOWED_PLATFORMS:
            errors.append(f"{file_name}: unsupported platform `{platform_name}`")
        if not isinstance(entry, dict):
            errors.append(f"{platform_prefix} must be an object")
            continue
        status = entry.get("status")
        if status is not None and status not in ALLOWED_RESOLUTION_STATUSES:
            errors.append(f"{platform_prefix} has invalid status `{status}`")
        resolvers = entry.get("resolvers")
        if not isinstance(resolvers, list):
            errors.append(f"{platform_prefix}.resolvers must be a list")
            continue
        for index, raw_resolver in enumerate(resolvers):
            resolver = _normalize_resolver(raw_resolver, resolution)
            name = resolver.get("name")
            resolver_prefix = f"{platform_prefix}.resolvers[{index}]"
            if name not in ALLOWED_RESOLVERS:
                errors.append(f"{resolver_prefix}: unsupported resolver `{name}`")
                continue
            if name in VERIFIED_COMMAND_RESOLVERS or name in BRIDGE_RESOLVERS:
                _validate_spec_shape(resolver_prefix, _spec_from_resolver(resolver), errors)


def _validate_targets(targets_data: Any, mcp_root: Path, errors: List[str]) -> None:
    if not isinstance(targets_data, dict):
        errors.append("targets/agents.json: targets must be an object")
        return
    agents = targets_data.get("agents")
    if not isinstance(agents, dict):
        errors.append("targets/agents.json: agents must be an object")
        return
    for agent_id, target in agents.items():
        prefix = f"targets/agents.json: agents.{agent_id}"
        _validate_target(prefix, target, mcp_root, errors)


def _validate_target(prefix: str, target: Any, mcp_root: Path, errors: List[str]) -> None:
    if not isinstance(target, dict):
        errors.append(f"{prefix} must be an object")
        return
    strategy = target.get("strategy")
    if strategy not in ALLOWED_TARGET_STRATEGIES:
        errors.append(f"{prefix}: unsupported strategy `{strategy}`")
        return

    variants = target.get("platforms")
    if variants is not None:
        if not isinstance(variants, dict):
            errors.append(f"{prefix}.platforms must be an object")
        else:
            for platform_name, variant in variants.items():
                if platform_name not in ALLOWED_PLATFORMS:
                    errors.append(f"{prefix}: unsupported platform `{platform_name}`")
                if not isinstance(variant, dict):
                    errors.append(f"{prefix}.platforms.{platform_name} must be an object")

    if strategy == "cli":
        _require_non_empty_string(prefix, target, "bin", errors)
        _require_list(prefix, target, "add_prefix", errors)
        for field in ("remove_prefix", "list_args"):
            if field in target:
                _require_list(prefix, target, field, errors)
        if "env_flag" in target and not isinstance(target.get("env_flag"), str):
            errors.append(f"{prefix}.env_flag must be a string")
        return

    if strategy == "json":
        _require_non_empty_string(prefix, target, "config_path", errors)
        _reject_shared_config_path(prefix, target, mcp_root, errors)
        if "key_path" in target:
            _require_list(prefix, target, "key_path", errors)
        if "entry_extra" in target and not isinstance(target.get("entry_extra"), dict):
            errors.append(f"{prefix}.entry_extra must be an object")
        entry_shape = target.get("entry_shape")
        if entry_shape is not None and entry_shape not in ALLOWED_ENTRY_SHAPES:
            errors.append(f"{prefix}: unsupported entry_shape `{entry_shape}`")
        return

    if strategy == "manual" and "reason" in target and not isinstance(target.get("reason"), str):
        errors.append(f"{prefix}.reason must be a string")


def _validate_spec_shape(prefix: str, spec: Any, errors: List[str]) -> None:
    if not isinstance(spec, dict):
        errors.append(f"{prefix} must be an object")
        return
    if not _non_empty_string(spec.get("command")):
        errors.append(f"{prefix}.command must be a non-empty string")
    if "args" in spec and not isinstance(spec.get("args"), list):
        errors.append(f"{prefix}.args must be a list")
    if "env" in spec and not isinstance(spec.get("env"), dict):
        errors.append(f"{prefix}.env must be an object")


def _reject_shared_config_path(prefix: str, target: dict[str, Any], mcp_root: Path, errors: List[str]) -> None:
    if not _non_empty_string(target.get("config_path")):
        return
    try:
        config_path = _target_config_path(target)
    except Exception as exc:  # noqa: BLE001 - malformed env expansion should be reported as audit failure.
        errors.append(f"{prefix}.config_path is invalid: {exc}")
        return
    if _is_relative_to(config_path.resolve(strict=False), mcp_root.resolve(strict=False)):
        errors.append(f"{prefix}.config_path must not point inside shared MCP root")


def _validate_required_instance_string(prefix: str, instance: dict[str, Any], field: str, errors: List[str]) -> None:
    if not _non_empty_string(instance.get(field)):
        errors.append(f"{prefix}.{field} must be a non-empty string")


def _require_non_empty_string(prefix: str, data: dict[str, Any], field: str, errors: List[str]) -> None:
    if not _non_empty_string(data.get(field)):
        errors.append(f"{prefix}.{field} must be a non-empty string")


def _require_list(prefix: str, data: dict[str, Any], field: str, errors: List[str]) -> None:
    value = data.get(field)
    if not isinstance(value, list):
        errors.append(f"{prefix}.{field} must be a list")
        return
    if not all(isinstance(item, str) for item in value):
        errors.append(f"{prefix}.{field} entries must be strings")


def _non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def render_markdown(result: Dict[str, Any]) -> str:
    lines = [
        "# Shared MCP Audit",
        "",
        f"- Status: `{'ok' if result.get('ok') else 'error'}`",
        f"- MCP root: `{result.get('mcp_root')}`",
        f"- Catalog entries: `{result.get('catalog_count', 0)}`",
        f"- Target agents: `{', '.join(result.get('target_agents', []))}`",
        f"- Recorded instances: `{result.get('state_count', 0)}`",
        "",
        "## Catalog",
        "",
        "| ID | Server | Label | Safe to share |",
        "|---|---|---|---|",
    ]
    for item in result.get("catalogs", []):
        lines.append(
            f"| `{item.get('id')}` | `{item.get('server_name')}` | {item.get('label')} | `{item.get('safe_to_share')}` |"
        )
    if result.get("warnings"):
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {w}" for w in result["warnings"])
    if result.get("errors"):
        lines.extend(["", "## Errors", ""])
        lines.extend(f"- {e}" for e in result["errors"])
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=None, help="Shared MCP root. Defaults to discovery.")
    parser.add_argument("--format", choices=["json", "markdown"], default="json")
    args = parser.parse_args()

    result = audit(Path(args.root).expanduser() if args.root else None)
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.format == "json" else render_markdown(result))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
