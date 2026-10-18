from __future__ import annotations

import argparse
import copy
import json
import os
import platform as platform_module
import re
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


@dataclass(frozen=True)
class EnvironmentIdentity:
    environment_id: str
    platform: str
    machine_display: str
    machine_key: str
    user: str
    home: str
    wsl_distro: str | None = None


class ConcurrentStateChange(RuntimeError):
    pass


class StateConflict(RuntimeError):
    pass


DEFAULT_STATE = {
    "schema_version": 1,
    "updated": None,
    "environments": [],
}

DEFAULT_STATE_FILE = (
    Path(__file__).resolve().parents[1] / "state" / "shared_system_instances.json"
)


def normalize_identity_part(value: str) -> str:
    return value.strip().casefold().replace(":", "-")


def build_environment_identity(
    platform_name: str,
    machine: str,
    user: str,
    home: str,
    wsl_distro: str | None = None,
) -> EnvironmentIdentity:
    platform_name = platform_name.casefold()
    machine_display = machine.strip() or "unknown-machine"
    machine_key = normalize_identity_part(machine_display)
    user_key = normalize_identity_part(user or "unknown-user")
    if platform_name == "wsl":
        if not wsl_distro:
            raise ValueError("WSL identity requires wsl_distro")
        environment_id = f"wsl:{machine_key}:{normalize_identity_part(wsl_distro)}:{user_key}"
    elif platform_name in {"macos", "windows", "linux"}:
        environment_id = f"{platform_name}:{machine_key}:{user_key}"
    else:
        raise ValueError(f"unsupported platform: {platform_name}")
    return EnvironmentIdentity(
        environment_id=environment_id,
        platform=platform_name,
        machine_display=machine_display,
        machine_key=machine_key,
        user=user,
        home=home,
        wsl_distro=wsl_distro,
    )


def detect_environment(
    *,
    platform_name: str | None = None,
    machine: str | None = None,
    user: str | None = None,
    home: str | None = None,
    wsl_distro: str | None = None,
) -> EnvironmentIdentity:
    detected_home = str(Path(home).expanduser()) if home else str(Path.home())
    detected_user = user or os.environ.get("USER") or os.environ.get("USERNAME") or Path(
        detected_home
    ).name

    env_wsl_distro = wsl_distro or os.environ.get("WSL_DISTRO_NAME")
    if platform_name:
        detected_platform = platform_name.casefold()
    elif env_wsl_distro:
        detected_platform = "wsl"
    elif sys_platform_is_windows():
        detected_platform = "windows"
    elif os.name == "posix" and platform_module.system().casefold() == "darwin":
        detected_platform = "macos"
    else:
        detected_platform = "linux"

    detected_machine = (
        machine
        or os.environ.get("COMPUTERNAME")
        or platform_module.node()
        or "unknown-machine"
    )
    return build_environment_identity(
        platform_name=detected_platform,
        machine=detected_machine,
        user=detected_user,
        home=detected_home,
        wsl_distro=env_wsl_distro,
    )


def load_json_state(
    path: str | Path,
    *,
    default_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    target = Path(path)
    fallback = copy.deepcopy(default_state or DEFAULT_STATE)
    if not target.exists():
        return fallback

    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise StateConflict(f"invalid JSON in state file: {target}") from exc

    if not isinstance(data, dict):
        raise StateConflict(f"state file must contain a JSON object: {target}")

    normalized = dict(data)
    normalized.setdefault("schema_version", fallback.get("schema_version", 1))
    normalized.setdefault("updated", fallback.get("updated"))
    environments = normalized.get("environments")
    if environments is None:
        normalized["environments"] = []
    else:
        normalized["environments"] = _validate_environments(
            environments,
            source=target,
        )
    return normalized


def atomic_update_json(
    path: str | Path,
    update: Callable[[dict[str, Any]], dict[str, Any]],
    *,
    default_state: dict[str, Any] | None = None,
    before_replace: Callable[[], None] | None = None,
) -> dict[str, Any]:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    _reject_conflicted_siblings(target)

    exists = target.exists()
    original = target.read_bytes() if exists else b""
    data = (
        load_json_state(target, default_state=default_state)
        if exists
        else copy.deepcopy(default_state or DEFAULT_STATE)
    )
    next_data = update(copy.deepcopy(data))
    if not isinstance(next_data, dict):
        raise StateConflict("updated state must be a JSON object")

    serialized = (json.dumps(next_data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=str(target.parent),
    )
    temp_path = Path(temp_name)

    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())

        try:
            parsed = json.loads(temp_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise StateConflict("generated invalid JSON") from exc

        if not isinstance(parsed, dict):
            raise StateConflict("generated state must be a JSON object")

        current = target.read_bytes() if target.exists() else b""
        if current != original:
            raise ConcurrentStateChange(f"state changed while updating: {target}")

        if before_replace is not None:
            before_replace()

        _reject_conflicted_siblings(target)
        current = target.read_bytes() if target.exists() else b""
        if current != original:
            raise ConcurrentStateChange(f"state changed while updating: {target}")

        os.replace(temp_path, target)
        _fsync_directory(target.parent)
        return parsed
    finally:
        if temp_path.exists():
            temp_path.unlink()


def record_environment(
    path: str | Path,
    identity: EnvironmentIdentity,
    *,
    unified_root: str,
    windows_agents_root: str | None,
    audit: dict[str, Any],
    before_replace: Callable[[], None] | None = None,
) -> dict[str, Any]:
    record_holder: dict[str, Any] = {}

    def apply_update(data: dict[str, Any]) -> dict[str, Any]:
        state = dict(data)
        environments = [dict(item) for item in state.get("environments", [])]
        existing_index = next(
            (
                index
                for index, item in enumerate(environments)
                if item.get("environment_id") == identity.environment_id
            ),
            None,
        )
        existing = environments[existing_index] if existing_index is not None else None
        record = _build_environment_record(
            identity=identity,
            unified_root=unified_root,
            windows_agents_root=windows_agents_root,
            audit=audit,
            existing=existing,
        )
        if existing_index is None:
            environments.append(record)
        else:
            environments[existing_index] = record

        state["schema_version"] = 1
        state["updated"] = record["last_sync"]
        state["environments"] = environments
        record_holder["record"] = record
        return state

    state = atomic_update_json(
        path,
        apply_update,
        default_state=DEFAULT_STATE,
        before_replace=before_replace,
    )
    result = dict(state)
    result["record"] = record_holder.get("record")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Preview or record shared cross-platform environment identity."
    )
    parser.add_argument("--state-file", default=str(DEFAULT_STATE_FILE))
    parser.add_argument("--platform", dest="platform_name")
    parser.add_argument("--machine")
    parser.add_argument("--user")
    parser.add_argument("--home")
    parser.add_argument("--wsl-distro")
    parser.add_argument("--unified-root")
    parser.add_argument("--windows-agents-root")
    parser.add_argument("--audit-skills", default="unknown")
    parser.add_argument("--audit-mcp", default="unknown")
    parser.add_argument("--audit-memories", default="unknown")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args(argv)

    identity = detect_environment(
        platform_name=args.platform_name,
        machine=args.machine,
        user=args.user,
        home=args.home,
        wsl_distro=args.wsl_distro,
    )
    state_path = Path(args.state_file).expanduser()
    unified_root = args.unified_root or str(Path(identity.home) / ".agents")
    windows_agents_root = args.windows_agents_root
    audit = {
        "skills": args.audit_skills,
        "mcp": args.audit_mcp,
        "memories": args.audit_memories,
    }

    write_enabled = args.apply and args.yes
    current_state = load_json_state(state_path, default_state=DEFAULT_STATE)
    preview_state = _merge_environment_state(
        current_state,
        identity=identity,
        unified_root=unified_root,
        windows_agents_root=windows_agents_root,
        audit=audit,
    )

    if write_enabled:
        final_state = record_environment(
            state_path,
            identity,
            unified_root=unified_root,
            windows_agents_root=windows_agents_root,
            audit=audit,
        )
        payload = _build_cli_payload(
            mode="apply",
            state_file=state_path,
            identity=identity,
            unified_root=unified_root,
            windows_agents_root=windows_agents_root,
            audit=audit,
            current_state=current_state,
            final_state=final_state,
            write_enabled=True,
        )
    else:
        payload = _build_cli_payload(
            mode="preview",
            state_file=state_path,
            identity=identity,
            unified_root=unified_root,
            windows_agents_root=windows_agents_root,
            audit=audit,
            current_state=current_state,
            final_state=preview_state,
            write_enabled=False,
        )

    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render_markdown_report(payload))
    return 0


def render_markdown_report(payload: dict[str, Any]) -> str:
    identity = payload["identity"]
    lines = [
        "# Shared Environment State",
        "",
        f"- Mode: {payload['mode']}",
        f"- State file: {payload['state_file']}",
        f"- Environment ID: {identity['environment_id']}",
        f"- Platform: {identity['platform']}",
        f"- Machine: {identity['machine_display']}",
        f"- User: {identity['user']}",
        f"- Home: {identity['home']}",
        f"- Unified root: {payload['unified_root']}",
        f"- Windows unified root: {payload['windows_agents_root'] or 'n/a'}",
        f"- WSL distro: {identity['wsl_distro'] or 'n/a'}",
        f"- Existing records: {payload['environment_count_before']}",
        f"- Result records: {payload['environment_count_after']}",
        f"- Audit: skills={payload['audit']['skills']}, mcp={payload['audit']['mcp']}, memories={payload['audit']['memories']}",
    ]
    if payload["write_enabled"]:
        lines.append("- Write: applied")
    else:
        lines.append("- Write: skipped (requires both --apply and --yes)")
    return "\n".join(lines)


def sys_platform_is_windows() -> bool:
    return os.name == "nt" or platform_module.system().casefold() == "windows"


def _merge_environment_state(
    data: dict[str, Any],
    *,
    identity: EnvironmentIdentity,
    unified_root: str,
    windows_agents_root: str | None,
    audit: dict[str, Any],
) -> dict[str, Any]:
    state = dict(data)
    environments = _validate_environments(state.get("environments", []), source=None)
    existing_index = next(
        (
            index
            for index, item in enumerate(environments)
            if item.get("environment_id") == identity.environment_id
        ),
        None,
    )
    existing = environments[existing_index] if existing_index is not None else None
    record = _build_environment_record(
        identity=identity,
        unified_root=unified_root,
        windows_agents_root=windows_agents_root,
        audit=audit,
        existing=existing,
    )
    if existing_index is None:
        environments.append(record)
    else:
        environments[existing_index] = record
    state["schema_version"] = 1
    state["updated"] = record["last_sync"]
    state["environments"] = environments
    state["record"] = record
    return state


def _build_environment_record(
    *,
    identity: EnvironmentIdentity,
    unified_root: str,
    windows_agents_root: str | None,
    audit: dict[str, Any],
    existing: dict[str, Any] | None,
) -> dict[str, Any]:
    timestamp = _utc_timestamp()
    record = {
        "environment_id": identity.environment_id,
        "platform": identity.platform,
        "machine_display": identity.machine_display,
        "machine_key": identity.machine_key,
        "user": identity.user,
        "home": identity.home,
        "wsl_distro": identity.wsl_distro,
        "windows_host_display": identity.machine_display if identity.platform == "wsl" else None,
        "windows_host_key": identity.machine_key if identity.platform == "wsl" else None,
        "unified_root": unified_root,
        "windows_agents_root": windows_agents_root,
        "audit": dict(audit),
        "first_seen": existing.get("first_seen") if existing else timestamp,
        "last_sync": timestamp,
    }
    return record


def _build_cli_payload(
    *,
    mode: str,
    state_file: Path,
    identity: EnvironmentIdentity,
    unified_root: str,
    windows_agents_root: str | None,
    audit: dict[str, Any],
    current_state: dict[str, Any],
    final_state: dict[str, Any],
    write_enabled: bool,
) -> dict[str, Any]:
    return {
        "mode": mode,
        "state_file": str(state_file),
        "identity": asdict(identity),
        "unified_root": unified_root,
        "windows_agents_root": windows_agents_root,
        "audit": dict(audit),
        "environment_count_before": len(current_state.get("environments", [])),
        "environment_count_after": len(final_state.get("environments", [])),
        "record": final_state.get("record"),
        "write_enabled": write_enabled,
    }


def _reject_conflicted_siblings(path: Path) -> None:
    parent = path.parent
    if not parent.exists():
        return
    # iCloud names a conflicting copy "<stem> 2<suffix>" next to the original.
    icloud_copy = re.compile(re.escape(path.stem) + r" \d+" + re.escape(path.suffix) + "$", re.IGNORECASE)
    for sibling in parent.iterdir():
        name = sibling.name.casefold()
        if "conflicted copy" in name or "冲突" in name or icloud_copy.match(sibling.name):
            raise StateConflict(f"conflicted sibling blocks state update: {sibling}")


def _validate_environments(
    environments: Any,
    *,
    source: Path | None,
) -> list[dict[str, Any]]:
    if not isinstance(environments, list):
        if source is None:
            raise StateConflict("state has non-list environments")
        raise StateConflict(f"state file has non-list environments: {source}")

    validated: list[dict[str, Any]] = []
    seen_ids: dict[str, int] = {}
    for index, item in enumerate(environments):
        if not isinstance(item, dict):
            if source is None:
                raise StateConflict(f"state has non-object environment at index {index}")
            raise StateConflict(
                f"state file has non-object environment at index {index}: {source}"
            )

        copied = dict(item)
        validated.append(copied)

        environment_id = copied.get("environment_id")
        if environment_id is None:
            continue
        if not isinstance(environment_id, str):
            if source is None:
                raise StateConflict(f"state has non-string environment_id at index {index}")
            raise StateConflict(
                f"state file has non-string environment_id at index {index}: {source}"
            )

        previous_index = seen_ids.get(environment_id)
        if previous_index is not None:
            if source is None:
                raise StateConflict(
                    f"state has duplicate environment_id {environment_id!r} at indexes "
                    f"{previous_index} and {index}"
                )
            raise StateConflict(
                f"state file has duplicate environment_id {environment_id!r} at indexes "
                f"{previous_index} and {index}: {source}"
            )
        seen_ids[environment_id] = index

    return validated


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(str(path), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


if __name__ == "__main__":
    raise SystemExit(main())
