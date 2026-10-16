#!/usr/bin/env python3
"""Preview or install one shared MCP entry into one local agent."""

from __future__ import annotations

import argparse
import copy
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
SHARED_SCRIPT_DIR = SCRIPT_DIR.parents[2] / "scripts"
if str(SHARED_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_SCRIPT_DIR))

from resolve_mcp_root import resolve_mcp_root
from shared_environment import (  # noqa: E402
    EnvironmentIdentity,
    StateConflict,
    atomic_update_json,
    build_environment_identity,
    detect_environment,
    normalize_identity_part,
)


ALLOWED_RESOLUTION_STATUSES = {"native", "bridge", "unsupported", "unverified"}
LOCAL_INSTALL_INFO = "local-install-info"
VERIFIED_COMMAND_RESOLVERS = {"verified-command", "verified-linux-command"}
BRIDGE_RESOLVERS = {"verified-windows-bridge"}
DEFAULT_MCP_STATE = {"version": 2, "instances": []}
PortDiscovery = Callable[[EnvironmentIdentity], Iterable[int]]


@dataclass(frozen=True)
class ResolutionResult:
    status: str
    spec: dict[str, Any] | None
    evidence: list[str]
    errors: list[str]


@dataclass(frozen=True)
class VerificationResult:
    configured: bool
    registered: bool
    operational: bool | None
    evidence: list[str]


def current_environment() -> EnvironmentIdentity:
    return detect_environment()


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _save_json_atomic(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        json.loads(temp_path.read_text(encoding="utf-8"))
        os.replace(temp_path, path)
        _fsync_directory(path.parent)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(str(path), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fetch_install_info(base_url: str, timeout: float = 2.0) -> Optional[Dict[str, Any]]:
    url = base_url.rstrip("/") + "/api/mcp/install-info"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310 - local daemon only.
            if resp.status != 200:
                return None
            data = json.loads(resp.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError, TimeoutError):
        return None
    if isinstance(data, dict) and isinstance(data.get("command"), str) and isinstance(data.get("args"), list):
        return data
    return None


def _lsof_open_design_ports() -> Iterable[int]:
    if platform.system().lower() != "darwin":
        return []
    try:
        out = subprocess.check_output(
            ["lsof", "-nP", "-iTCP", "-sTCP:LISTEN"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError):
        return []
    ports = []
    for line in out.splitlines():
        if "Open" not in line and "open" not in line:
            continue
        match = re.search(r"127\.0\.0\.1:(\d+)", line)
        if match:
            ports.append(int(match.group(1)))
    return sorted(set(ports))


def _windows_open_design_ports() -> Iterable[int]:
    if platform.system().lower() != "windows":
        return []
    ports: list[int] = []
    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if powershell:
        script = (
            "Get-NetTCPConnection -State Listen -LocalAddress 127.0.0.1 "
            "| ForEach-Object { "
            "$p = Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue; "
            "if ($p -and $p.ProcessName -match 'Open.?Design|open-design|Electron') { $_.LocalPort } "
            "}"
        )
        try:
            out = subprocess.check_output(
                [powershell, "-NoProfile", "-Command", script],
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=3,
            )
            ports.extend(_parse_ports(out))
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
            pass

    if ports:
        return sorted(set(ports))

    netstat = shutil.which("netstat")
    if not netstat:
        return []
    try:
        out = subprocess.check_output(
            [netstat, "-ano", "-p", "tcp"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=3,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return []
    for line in out.splitlines():
        if "LISTEN" not in line.upper():
            continue
        match = re.search(r"(?:127\.0\.0\.1|\[::1\]):(\d+)", line)
        if match:
            ports.append(int(match.group(1)))
    return sorted(set(ports))


def _parse_ports(output: str) -> list[int]:
    ports: list[int] = []
    for match in re.finditer(r"\b(\d{2,5})\b", output):
        port = int(match.group(1))
        if 1 <= port <= 65535:
            ports.append(port)
    return sorted(set(ports))


def _default_open_design_port_discovery(environment: EnvironmentIdentity) -> Iterable[int]:
    if environment.platform == "macos":
        return _lsof_open_design_ports()
    if environment.platform == "windows":
        return _windows_open_design_ports()
    return []


def _install_info_candidates(
    daemon_url: Optional[str],
    environment: EnvironmentIdentity,
    port_discovery: PortDiscovery | None = None,
) -> list[str]:
    candidates: list[str] = []
    if daemon_url:
        candidates.append(daemon_url)
    if os.environ.get("OD_DAEMON_URL"):
        candidates.append(os.environ["OD_DAEMON_URL"])
    if os.environ.get("OPEN_DESIGN_DAEMON_URL"):
        candidates.append(os.environ["OPEN_DESIGN_DAEMON_URL"])
    discover_ports = port_discovery or _default_open_design_port_discovery
    for raw_port in discover_ports(environment):
        try:
            port = int(raw_port)
        except (TypeError, ValueError):
            continue
        if 1 <= port <= 65535:
            candidates.append(f"http://127.0.0.1:{port}")
    if environment.platform == "macos" or (
        environment.platform == "windows" and platform.system().lower() == "windows"
    ):
        candidates.append("http://127.0.0.1:7456")

    seen: set[str] = set()
    ordered: list[str] = []
    for candidate in candidates:
        if candidate and candidate not in seen:
            ordered.append(candidate)
            seen.add(candidate)
    return ordered


def platform_catalog_entry(catalog: dict[str, Any], platform_name: str) -> dict[str, Any]:
    platforms = catalog.get("platforms")
    if not isinstance(platforms, dict):
        raise ValueError("catalog has no platform resolver declarations")
    normalized = "macos" if platform_name == "darwin" else platform_name.casefold()
    entry = platforms.get(normalized)
    if entry is None and normalized == "wsl":
        entry = platforms.get("linux")
    if not isinstance(entry, dict):
        raise ValueError(f"catalog has no resolver for platform `{normalized}`")
    return entry


def resolve_catalog_spec(
    catalog: dict[str, Any],
    environment: EnvironmentIdentity,
    daemon_url: Optional[str],
    port_discovery: PortDiscovery | None = None,
) -> ResolutionResult:
    resolution = catalog.get("resolution") or {}
    kind = resolution.get("kind")
    evidence: list[str] = []
    errors: list[str] = []

    if kind == "open_design_install_info" and "platforms" not in catalog:
        return resolve_open_design_spec(argparse.Namespace(daemon_url=daemon_url), environment, port_discovery)

    try:
        entry = platform_catalog_entry(catalog, environment.platform)
    except ValueError as exc:
        if kind == "open_design_install_info":
            evidence.append(str(exc))
            return resolve_open_design_spec(argparse.Namespace(daemon_url=daemon_url), environment, port_discovery)
        return ResolutionResult("unverified", None, evidence, [str(exc)])

    if entry.get("status") == "unsupported":
        return ResolutionResult(
            "unsupported",
            None,
            [f"{environment.platform} catalog entry marks MCP unsupported"],
            [],
        )

    resolvers = entry.get("resolvers") or []
    if not isinstance(resolvers, list):
        return ResolutionResult("unverified", None, evidence, ["platform resolvers must be a list"])

    for raw_resolver in resolvers:
        resolver = _normalize_resolver(raw_resolver, resolution)
        name = resolver.get("name")
        if name == LOCAL_INSTALL_INFO:
            result = _resolve_install_info_resolver(daemon_url, environment, port_discovery)
            evidence.extend(result.evidence)
            errors.extend(result.errors)
            if result.spec:
                native_errors = validate_native_spec(result.spec, environment)
                if not native_errors:
                    return result
                errors.extend(native_errors)
            continue

        if name in VERIFIED_COMMAND_RESOLVERS:
            spec = _spec_from_resolver(resolver)
            if resolver.get("identity_gated") and not resolver.get("identity_confirmed"):
                evidence.append(f"{name} is identity-gated and not confirmed")
                continue
            native_errors = validate_native_spec(spec, environment)
            if native_errors:
                errors.extend(native_errors)
                continue
            return ResolutionResult("native", spec, [f"resolved native via {name}"], [])

        if name in BRIDGE_RESOLVERS:
            spec = _spec_from_resolver(resolver)
            bridge_errors = validate_wsl_bridge_spec(spec)
            if bridge_errors:
                errors.extend(bridge_errors)
                continue
            return ResolutionResult("bridge", spec, [f"resolved bridge via {name}"], [])

        errors.append(f"unsupported resolver `{name}`")

    status = "unsupported" if entry.get("status") == "unsupported" else "unverified"
    if not evidence and not errors:
        evidence.append(f"no usable resolver for {environment.platform}")
    return ResolutionResult(status, None, evidence, errors)


def resolve_open_design_spec(
    args: argparse.Namespace,
    environment: EnvironmentIdentity,
    port_discovery: PortDiscovery | None = None,
) -> ResolutionResult:
    evidence: list[str] = []
    errors: list[str] = []
    for base in _install_info_candidates(getattr(args, "daemon_url", None), environment, port_discovery):
        info = _fetch_install_info(base)
        if not info:
            evidence.append(f"no install-info response from {base}")
            continue
        spec = _install_info_spec(info, base)
        native_errors = validate_native_spec(spec, environment)
        if native_errors:
            errors.extend(native_errors)
            continue
        return ResolutionResult("native", spec, [f"resolved via {base}"], [])

    evidence.append("Open Design daemon not discovered; open the app or pass --daemon-url")
    return ResolutionResult("unverified", None, evidence, errors)


def _resolve_install_info_resolver(
    daemon_url: Optional[str],
    environment: EnvironmentIdentity,
    port_discovery: PortDiscovery | None = None,
) -> ResolutionResult:
    for base in _install_info_candidates(daemon_url, environment, port_discovery):
        info = _fetch_install_info(base)
        if info:
            return ResolutionResult("native", _install_info_spec(info, base), [f"resolved via {base}"], [])
    return ResolutionResult(
        "unverified",
        None,
        ["local install-info endpoint not discovered"],
        [],
    )


def _install_info_spec(info: dict[str, Any], base_url: str) -> dict[str, Any]:
    return {
        "command": info["command"],
        "args": [str(x) for x in info.get("args", [])],
        "env": {str(k): str(v) for k, v in (info.get("env") or {}).items()},
        "daemonUrl": info.get("daemonUrl") or base_url,
        "reusable_across_environments": False,
    }


def _normalize_resolver(raw_resolver: Any, resolution: dict[str, Any]) -> dict[str, Any]:
    if isinstance(raw_resolver, str):
        resolver: dict[str, Any] = {"name": raw_resolver}
        fallback = resolution.get("fallback")
        if raw_resolver in VERIFIED_COMMAND_RESOLVERS and isinstance(fallback, dict):
            resolver.update(fallback)
            resolver.setdefault("identity_gated", True)
        return resolver
    if isinstance(raw_resolver, dict):
        resolver = dict(raw_resolver)
        resolver.setdefault("name", raw_resolver.get("resolver"))
        return resolver
    return {"name": str(raw_resolver)}


def _spec_from_resolver(resolver: dict[str, Any]) -> dict[str, Any]:
    return {
        "command": str(resolver.get("command") or ""),
        "args": [str(item) for item in resolver.get("args", [])],
        "env": {str(key): str(value) for key, value in (resolver.get("env") or {}).items()},
        "daemonUrl": resolver.get("daemonUrl"),
        "reusable_across_environments": bool(resolver.get("reusable_across_environments", False)),
    }


def validate_native_spec(spec: dict[str, Any], environment: EnvironmentIdentity) -> list[str]:
    errors: list[str] = []
    command = str(spec.get("command") or "")
    if not command:
        return ["launch spec has no command"]

    if environment.platform in {"macos", "linux", "wsl"} and _looks_like_windows_path(command):
        errors.append(f"command is not executable in {environment.platform}: {command}")

    if Path(command).name == "od" and not spec.get("identity_confirmed"):
        resolved = shutil.which(command) if not os.path.isabs(command) else command
        if resolved == "/usr/bin/od" or command == "od":
            errors.append("od command identity is unverified")

    if os.path.isabs(command) or os.sep in command:
        if not Path(command).is_file():
            errors.append(f"command not found: {command}")
        elif not os.access(command, os.X_OK):
            errors.append(f"command is not executable: {command}")
    elif shutil.which(command) is None:
        errors.append(f"command not found on PATH: {command}")

    for key, value in (spec.get("env") or {}).items():
        if environment.platform in {"macos", "linux", "wsl"} and _looks_like_windows_path(str(value)):
            errors.append(f"env {key} has a Windows path not usable in {environment.platform}")
        if environment.platform == "wsl" and _looks_like_named_pipe(str(value)):
            errors.append(f"env {key} uses a Windows named pipe not usable directly from WSL")
    return errors


def validate_wsl_bridge_spec(spec: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    command = str(spec.get("command") or "")
    if not command:
        errors.append("bridge spec has no command")
    if _looks_like_windows_path(command):
        errors.append("WSL bridge command is a Windows path and is not directly executable")
    elif os.path.isabs(command):
        if not Path(command).is_file():
            errors.append(f"bridge command not found: {command}")
        elif not os.access(command, os.X_OK):
            errors.append(f"bridge command is not executable: {command}")
    elif shutil.which(command) is None:
        errors.append(f"bridge command not found on PATH: {command}")

    for key, value in (spec.get("env") or {}).items():
        value_text = str(value)
        if _looks_like_named_pipe(value_text):
            errors.append(f"bridge env {key} uses a Windows named pipe")
        if value_text.startswith("/var/run/") or value_text.startswith("/tmp/"):
            errors.append(f"bridge env {key} uses a local Unix socket that may not cross environments")
    return errors


def _looks_like_windows_path(value: str) -> bool:
    return bool(re.match(r"^[A-Za-z]:\\", value)) or value.startswith("\\\\")


def _looks_like_named_pipe(value: str) -> bool:
    return value.startswith(r"\\.\pipe\\") or value.startswith(r"\\.\pipe")


def shell_join(parts: List[str]) -> str:
    import shlex

    return " ".join(shlex.quote(p) for p in parts)


def build_cli_command(target: Dict[str, Any], server_name: str, spec: Dict[str, Any]) -> List[str]:
    cmd = [target["bin"], *target["add_prefix"], server_name]
    env_flag = target.get("env_flag")
    for key, value in spec.get("env", {}).items():
        if env_flag:
            cmd.extend([env_flag, f"{key}={value}"])
    cmd.extend(["--", spec["command"], *spec.get("args", [])])
    return cmd


def build_json_entry(target: Dict[str, Any], spec: Dict[str, Any]) -> Dict[str, Any]:
    if target.get("entry_shape") == "opencode-local":
        entry: Dict[str, Any] = {
            "type": "local",
            "command": [spec["command"], *spec.get("args", [])],
            "enabled": True,
        }
        if spec.get("env"):
            entry["environment"] = spec["env"]
        return entry
    entry = {"command": spec["command"], "args": spec.get("args", [])}
    entry.update(target.get("entry_extra") or {})
    if spec.get("env"):
        entry["env"] = spec["env"]
    return entry


def deep_set_server(config: Dict[str, Any], key_path: List[str], server_name: str, entry: Dict[str, Any]) -> Dict[str, Any]:
    next_config = copy.deepcopy(config)
    cursor = next_config
    for key in key_path:
        next_value = cursor.get(key)
        if not isinstance(next_value, dict):
            next_value = {}
            cursor[key] = next_value
        cursor = next_value
    cursor[server_name] = entry
    return next_config


def verify_agent_registration(target: dict[str, Any], server_name: str) -> VerificationResult:
    strategy = target.get("strategy")
    evidence: list[str] = []
    if strategy == "cli":
        binary = target.get("bin")
        if not binary or shutil.which(binary) is None:
            return VerificationResult(False, False, None, [f"{binary or 'agent'} binary not found"])
        list_args = target.get("list_args")
        if not isinstance(list_args, list):
            return VerificationResult(True, False, None, ["no list_args verification command configured"])
        try:
            completed = subprocess.run(
                [binary, *[str(item) for item in list_args]],
                text=True,
                capture_output=True,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return VerificationResult(True, False, None, [f"registration verification failed: {exc}"])
        output = f"{completed.stdout}\n{completed.stderr}"
        registered = completed.returncode == 0 and server_name in output
        evidence.append(f"{binary} {' '.join(list_args)} exited {completed.returncode}")
        return VerificationResult(True, registered, None, evidence)

    if strategy == "json":
        config_path = _target_config_path(target)
        key_path = target.get("key_path") or ["mcpServers"]
        if not config_path.is_file():
            return VerificationResult(False, False, None, [f"config file not found: {config_path}"])
        try:
            data = _load_json(config_path)
        except (OSError, json.JSONDecodeError) as exc:
            return VerificationResult(False, False, None, [f"config read failed: {exc}"])
        cursor: Any = data
        for key in key_path:
            cursor = cursor.get(key) if isinstance(cursor, dict) else None
        registered = isinstance(cursor, dict) and server_name in cursor
        return VerificationResult(True, registered, None, [f"checked JSON config {config_path}"])

    return VerificationResult(False, False, None, ["manual target cannot be verified automatically"])


def mcp_instance_key(record: dict[str, Any]) -> tuple[str | None, str | None, str | None, str | None]:
    return (
        record.get("environment_id"),
        record.get("agent"),
        record.get("mcp"),
        record.get("server_name"),
    )


def record_instance(mcp_root: Path, record: Dict[str, Any]) -> None:
    state_file = mcp_root / "state" / "mcp_instances.json"

    def update(data: dict[str, Any]) -> dict[str, Any]:
        state = _normalize_mcp_state(data)
        incoming = dict(record)
        incoming.setdefault("last_sync", int(time.time()))
        incoming.setdefault("resolution_status", "unverified")
        incoming.setdefault("verification", {"configured": True, "registered": False, "operational": None})
        incoming.setdefault("evidence", {"migration": "recorded by sync_agent_mcp"})
        instances = [
            item
            for item in state.get("instances", [])
            if mcp_instance_key(item) != mcp_instance_key(incoming)
        ]
        instances.append(incoming)
        state["version"] = 2
        state["instances"] = instances
        return state

    atomic_update_json(state_file, update, default_state=DEFAULT_MCP_STATE)


def migrate_mcp_state(mcp_root: Path, apply: bool = False) -> dict[str, Any]:
    state_file = mcp_root / "state" / "mcp_instances.json"
    if apply:
        state = atomic_update_json(state_file, _normalize_mcp_state, default_state=DEFAULT_MCP_STATE)
    elif state_file.exists():
        state = _normalize_mcp_state(_load_json(state_file))
    else:
        state = _normalize_mcp_state(copy.deepcopy(DEFAULT_MCP_STATE))
    return {
        "ok": True,
        "apply": bool(apply),
        "state_path": str(state_file),
        "state": state,
        "state_count": len(state.get("instances", [])),
    }


def _normalize_mcp_state(data: dict[str, Any]) -> dict[str, Any]:
    instances = data.get("instances", [])
    if not isinstance(instances, list):
        raise StateConflict("MCP state instances must be a list")
    normalized_instances = []
    for item in instances:
        if not isinstance(item, dict):
            raise StateConflict("MCP state instance must be an object")
        copied = dict(item)
        copied.setdefault("environment_id", _legacy_environment_id(copied))
        if copied.get("platform") == "darwin":
            copied["platform"] = "macos"
        copied.setdefault("resolution_status", _legacy_resolution_status(copied))
        copied["verification"] = _normalize_verification(copied.get("verification"), copied)
        copied["evidence"] = _normalize_evidence(copied)
        if "daemonUrl" in copied:
            if isinstance(copied["evidence"], dict):
                copied["evidence"].setdefault("daemonUrl", copied.get("daemonUrl"))
                copied["evidence"].setdefault("reusable_across_environments", False)
        normalized_instances.append(copied)
    return {"version": 2, "instances": normalized_instances}


def _legacy_resolution_status(record: dict[str, Any]) -> str:
    existing = record.get("resolution_status")
    if existing in ALLOWED_RESOLUTION_STATUSES:
        return str(existing)
    if record.get("daemonUrl"):
        return "native"
    return "unverified"


def _normalize_verification(raw_verification: Any, record: dict[str, Any]) -> dict[str, bool | None]:
    configured_default = bool(record.get("strategy") or record.get("agent") or record.get("server_name"))
    if isinstance(raw_verification, dict):
        operational = raw_verification.get("operational")
        return {
            "configured": bool(raw_verification.get("configured", configured_default)),
            "registered": bool(raw_verification.get("registered", False)),
            "operational": operational if isinstance(operational, bool) else None,
        }
    return {
        "configured": configured_default,
        "registered": False,
        "operational": None,
    }


def _normalize_evidence(record: dict[str, Any]) -> dict[str, Any]:
    raw_evidence = record.get("evidence")
    if isinstance(raw_evidence, dict):
        evidence = dict(raw_evidence)
    else:
        evidence = {}
        if raw_evidence is not None:
            evidence["legacy_evidence"] = raw_evidence
    evidence.setdefault("migration", "normalized from MCP state")
    if record.get("daemonUrl"):
        evidence.setdefault("daemonUrl", record.get("daemonUrl"))
        evidence.setdefault("reusable_across_environments", False)
    return evidence


def _legacy_environment_id(record: dict[str, Any]) -> str:
    raw_platform = str(record.get("platform") or "linux").casefold()
    platform_name = "macos" if raw_platform in {"darwin", "macos"} else raw_platform
    if platform_name not in {"macos", "windows", "linux", "wsl"}:
        platform_name = "linux"
    machine = str(record.get("machine") or record.get("machine_display") or "legacy-machine")
    user = str(record.get("user") or "legacy-user")
    if platform_name == "wsl":
        distro = str(record.get("wsl_distro") or "legacy-wsl")
        return build_environment_identity(platform_name, machine, user, str(Path.home()), distro).environment_id
    return build_environment_identity(platform_name, machine, user, str(Path.home())).environment_id


def sync(args: argparse.Namespace) -> Dict[str, Any]:
    if getattr(args, "migrate_state_only", False):
        if args.apply and not args.yes:
            return {"ok": False, "errors": ["Refusing to apply without --yes."], "apply": True}
        root_result = resolve_mcp_root(Path(args.start).expanduser() if args.start else None)
        if not root_result.get("ok"):
            return {"ok": False, "errors": [root_result.get("error")], "resolver": root_result}
        result = migrate_mcp_state(Path(root_result["mcp_root"]), apply=bool(args.apply))
        result["resolver"] = root_result
        return result

    if args.apply and not args.yes:
        return {"ok": False, "errors": ["Refusing to apply without --yes."], "apply": True}

    root_result = resolve_mcp_root(Path(args.start).expanduser() if args.start else None)
    if not root_result.get("ok"):
        return {"ok": False, "errors": [root_result.get("error")], "resolver": root_result}

    mcp_root = Path(root_result["mcp_root"])
    catalog_file = mcp_root / "catalog" / f"{args.mcp}.json"
    targets_file = mcp_root / "targets" / "agents.json"
    if not catalog_file.is_file():
        return {"ok": False, "errors": [f"MCP catalog not found: {catalog_file}"]}
    catalog = _load_json(catalog_file)
    targets = _load_json(targets_file).get("agents", {})
    target = targets.get(args.agent)
    if not target:
        return {"ok": False, "errors": [f"Unknown agent `{args.agent}`. Known: {', '.join(sorted(targets))}"]}

    environment = _environment_from_args(args)
    target = target_for_environment(target, environment)
    resolution = resolve_catalog_spec(catalog, environment, args.daemon_url)
    server_name = args.name or catalog.get("server_name") or args.mcp
    strategy = target.get("strategy")
    plan: Dict[str, Any] = {
        "ok": resolution.spec is not None and resolution.status in {"native", "bridge"},
        "mcp": args.mcp,
        "server_name": server_name,
        "agent": args.agent,
        "strategy": strategy,
        "environment": asdict(environment),
        "resolution_status": resolution.status,
        "notes": resolution.evidence,
        "errors": list(resolution.errors),
        "apply": bool(args.apply),
    }
    if resolution.spec is None:
        if not plan["errors"]:
            plan["errors"] = [f"MCP resolution is {resolution.status}"]
        return plan

    spec = resolution.spec
    if strategy == "cli":
        command = build_cli_command(target, server_name, spec)
        plan["command"] = command
        plan["command_text"] = shell_join(command)
        if args.apply:
            result = subprocess.run(command, text=True)
            plan["exit_code"] = result.returncode
            plan["ok"] = result.returncode == 0
            if result.returncode != 0:
                plan.setdefault("errors", []).append(f"{target['bin']} exited with code {result.returncode}")
            verification = verify_agent_registration(target, server_name) if plan.get("ok") else VerificationResult(False, False, None, [])
            plan["verification"] = asdict(verification)
            if plan.get("ok"):
                _record_applied_instance(mcp_root, args, strategy, server_name, spec, environment, resolution, verification)
        return plan

    if strategy == "json":
        config_path = _target_config_path(target)
        entry = build_json_entry(target, spec)
        key_path = target.get("key_path") or ["mcpServers"]
        existing: Dict[str, Any] = {}
        if config_path.is_file():
            loaded = _load_json(config_path)
            existing = loaded if isinstance(loaded, dict) else {}
        next_config = deep_set_server(existing, key_path, server_name, entry)
        plan["config_path"] = str(config_path)
        plan["entry"] = entry
        plan["key_path"] = key_path
        if args.apply:
            _save_json_atomic(config_path, next_config)
            verification = verify_agent_registration(target, server_name)
            plan["verification"] = asdict(verification)
            _record_applied_instance(mcp_root, args, strategy, server_name, spec, environment, resolution, verification)
        return plan

    snippet = {
        "mcpServers": {
            server_name: {
                "command": spec["command"],
                "args": spec.get("args", []),
                "env": spec.get("env", {}),
            }
        }
    }
    plan["ok"] = False
    plan["manual"] = True
    plan["reason"] = target.get("reason", "Manual setup required.")
    plan["snippet"] = snippet
    return plan


def target_for_environment(target: dict[str, Any], environment: EnvironmentIdentity) -> dict[str, Any]:
    merged = copy.deepcopy(target)
    variants = target.get("platforms")
    if isinstance(variants, dict):
        variant = variants.get(environment.platform)
        if variant is None and environment.platform == "wsl":
            variant = variants.get("linux")
        if isinstance(variant, dict):
            merged.update(variant)
    return merged


def _target_config_path(target: dict[str, Any]) -> Path:
    raw_path = str(target["config_path"])
    return Path(os.path.expandvars(raw_path)).expanduser()


def _environment_from_args(args: argparse.Namespace) -> EnvironmentIdentity:
    return detect_environment(
        platform_name=getattr(args, "platform_name", None),
        machine=getattr(args, "machine", None),
        user=getattr(args, "user", None),
        home=getattr(args, "home", None),
        wsl_distro=getattr(args, "wsl_distro", None),
    )


def _record_applied_instance(
    mcp_root: Path,
    args: argparse.Namespace,
    strategy: str,
    server_name: str,
    spec: dict[str, Any],
    environment: EnvironmentIdentity,
    resolution: ResolutionResult,
    verification: VerificationResult,
) -> None:
    evidence = {
        "resolution": resolution.evidence,
        "reusable_across_environments": bool(spec.get("reusable_across_environments", False)),
    }
    if spec.get("daemonUrl"):
        evidence["daemonUrl"] = spec.get("daemonUrl")
        evidence["reusable_across_environments"] = False
    record_instance(
        mcp_root,
        {
            "environment_id": environment.environment_id,
            "mcp": args.mcp,
            "agent": args.agent,
            "strategy": strategy,
            "server_name": server_name,
            "machine": socket.gethostname(),
            "platform": environment.platform,
            "last_sync": int(time.time()),
            "resolution_status": resolution.status,
            "verification": asdict(verification),
            "evidence": evidence,
        },
    )


def render_markdown(result: Dict[str, Any]) -> str:
    lines = ["# Agent MCP Sync", ""]
    lines.append(f"- Status: `{'ok' if result.get('ok') else 'error'}`")
    if result.get("state_path"):
        lines.append(f"- State path: `{result.get('state_path')}`")
        lines.append(f"- Recorded instances: `{result.get('state_count', 0)}`")
    if result.get("mcp"):
        lines.append(f"- MCP: `{result.get('mcp')}`")
    if result.get("agent"):
        lines.append(f"- Agent: `{result.get('agent')}`")
    if result.get("strategy"):
        lines.append(f"- Strategy: `{result.get('strategy')}`")
    if result.get("resolution_status"):
        lines.append(f"- Resolution: `{result.get('resolution_status')}`")
    if result.get("environment"):
        lines.append(f"- Environment ID: `{result['environment'].get('environment_id')}`")
        lines.append(f"- Platform: `{result['environment'].get('platform')}`")
    if result.get("notes"):
        lines.extend(["", "## Notes", ""])
        lines.extend(f"- {n}" for n in result["notes"])
    if result.get("command_text"):
        lines.extend(["", "## Command", "", "```bash", result["command_text"], "```"])
    if result.get("config_path"):
        lines.extend(["", "## JSON Target", "", f"- Config: `{result.get('config_path')}`"])
        lines.extend(["", "Entry:", "", "```json", json.dumps(result.get("entry"), ensure_ascii=False, indent=2), "```"])
    if result.get("verification"):
        lines.extend(["", "## Verification", ""])
        verification = result["verification"]
        lines.append(f"- Configured: `{verification.get('configured')}`")
        lines.append(f"- Registered: `{verification.get('registered')}`")
        lines.append(f"- Operational: `{verification.get('operational')}`")
        for item in verification.get("evidence", []):
            lines.append(f"- Evidence: {item}")
    if result.get("manual"):
        lines.extend(["", "## Manual Setup Required", "", f"- Reason: {result.get('reason')}", "", "```json", json.dumps(result.get("snippet"), ensure_ascii=False, indent=2), "```"])
    if result.get("errors"):
        lines.extend(["", "## Errors", ""])
        lines.extend(f"- {e}" for e in result["errors"])
    if not result.get("apply") and result.get("ok"):
        lines.extend(["", "Run again with `--apply --yes` after reviewing the plan."])
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mcp", default=None, help="MCP id from .agents/mcp/catalog.")
    parser.add_argument("--agent", default=None, help="Target agent id from .agents/mcp/targets/agents.json.")
    parser.add_argument("--name", default=None, help="Override server name in target agent config.")
    parser.add_argument("--daemon-url", default=None, help="Optional daemon URL, for example http://127.0.0.1:52971.")
    parser.add_argument("--start", default=None, help="Optional start path for root discovery.")
    parser.add_argument("--platform", dest="platform_name", default=None, choices=["macos", "windows", "linux", "wsl"])
    parser.add_argument("--machine", default=None)
    parser.add_argument("--user", default=None)
    parser.add_argument("--home", default=None)
    parser.add_argument("--wsl-distro", default=None)
    parser.add_argument("--migrate-state-only", action="store_true", help="Normalize .agents/mcp/state/mcp_instances.json to v2 only.")
    parser.add_argument("--apply", action="store_true", help="Write to the target agent config.")
    parser.add_argument("--yes", action="store_true", help="Required with --apply for non-interactive confirmation.")
    parser.add_argument("--format", choices=["json", "markdown"], default="json")
    args = parser.parse_args()

    if not args.migrate_state_only and (not args.mcp or not args.agent):
        parser.error("--mcp and --agent are required unless --migrate-state-only is used")

    result = sync(args)
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.format == "json" else render_markdown(result))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
