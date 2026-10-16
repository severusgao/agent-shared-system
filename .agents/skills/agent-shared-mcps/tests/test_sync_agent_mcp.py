from __future__ import annotations

import argparse
import json
import os
import stat
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from socketserver import TCPServer


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
SHARED_SCRIPT_DIR = Path(__file__).resolve().parents[3] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SHARED_SCRIPT_DIR))

from shared_environment import StateConflict, build_environment_identity  # noqa: E402
from audit_shared_mcps import audit as audit_shared_mcps  # noqa: E402
from sync_agent_mcp import (  # noqa: E402
    ResolutionResult,
    VerificationResult,
    current_environment,
    deep_set_server,
    migrate_mcp_state,
    mcp_instance_key,
    record_instance,
    resolve_catalog_spec,
    sync,
    validate_native_spec,
    validate_wsl_bridge_spec,
)


class InstallInfoHandler(BaseHTTPRequestHandler):
    helper_command = "/tmp/open-design-helper"

    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/api/mcp/install-info":
            self.send_response(404)
            self.end_headers()
            return
        payload = {
            "command": self.helper_command,
            "args": ["mcp"],
            "env": {},
            "daemonUrl": "http://127.0.0.1:9999",
        }
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


class LocalInstallInfoServer(ThreadingHTTPServer):
    """Avoid reverse-DNS stalls from HTTPServer.server_bind during local tests."""

    def server_bind(self) -> None:
        TCPServer.server_bind(self)
        host, port = self.server_address[:2]
        self.server_name = str(host)
        self.server_port = int(port)


class SyncAgentMcpTests(unittest.TestCase):
    def make_audit_root(
        self,
        root: Path,
        *,
        catalog: dict[str, object] | None = None,
        targets: dict[str, object] | None = None,
        state: dict[str, object] | None = None,
    ) -> Path:
        mcp_root = root / ".agents" / "mcp"
        (mcp_root / "catalog").mkdir(parents=True)
        (mcp_root / "targets").mkdir()
        (mcp_root / "state").mkdir()
        (mcp_root / "catalog" / "example.json").write_text(
            json.dumps(
                catalog
                or {
                    "id": "example",
                    "server_name": "example",
                    "label": "Example",
                    "description": "Example MCP",
                    "resolution": {"kind": "catalog_platforms"},
                    "platforms": {
                        "macos": {
                            "status": "unsupported",
                            "resolvers": [],
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        (mcp_root / "targets" / "agents.json").write_text(
            json.dumps(targets or {"agents": {}}),
            encoding="utf-8",
        )
        (mcp_root / "state" / "mcp_instances.json").write_text(
            json.dumps(
                state
                or {
                    "version": 2,
                    "instances": [],
                }
            ),
            encoding="utf-8",
        )
        return mcp_root

    def test_current_environment_uses_canonical_platform_names(self) -> None:
        current = current_environment()
        self.assertIn(current.platform, {"macos", "windows", "linux", "wsl"})
        self.assertNotEqual(current.platform, "darwin")

    def test_wsl_keeps_wsl_environment_id_while_resolving_linux_template(self) -> None:
        wsl_environment = build_environment_identity(
            platform_name="wsl",
            machine="Host",
            user="User",
            home="/home/user",
            wsl_distro="Ubuntu",
        )
        result = resolve_catalog_spec(
            {
                "id": "example",
                "resolution": {"kind": "catalog_platforms"},
                "platforms": {
                    "linux": {
                        "status": "unsupported",
                        "resolvers": [],
                    }
                },
            },
            wsl_environment,
            daemon_url=None,
        )
        self.assertEqual(wsl_environment.environment_id, "wsl:host:ubuntu:user")
        self.assertEqual(result.status, "unsupported")

    def test_catalog_without_usable_wsl_resolver_is_unverified(self) -> None:
        wsl_environment = build_environment_identity(
            platform_name="wsl",
            machine="Host",
            user="User",
            home="/home/user",
            wsl_distro="Ubuntu",
        )
        result = resolve_catalog_spec(
            {
                "id": "open-design",
                "resolution": {"kind": "catalog_platforms"},
                "platforms": {
                    "wsl": {
                        "preferred": "native",
                        "fallback": "bridge",
                        "resolvers": [
                            {
                                "name": "verified-linux-command",
                                "command": "/missing/open-design",
                                "args": ["mcp"],
                            },
                            {
                                "name": "verified-windows-bridge",
                                "command": r"C:\Program Files\Open Design\helper.exe",
                                "args": ["mcp"],
                                "env": {"OD_SIDECAR_IPC_PATH": r"\\.\pipe\open-design"},
                            },
                        ],
                    }
                },
            },
            wsl_environment,
            daemon_url=None,
        )
        self.assertEqual(result.status, "unverified")
        self.assertIsNone(result.spec)

    def test_validate_wsl_bridge_rejects_windows_paths_and_named_pipes(self) -> None:
        bridge_errors = validate_wsl_bridge_spec(
            {
                "command": r"C:\Program Files\Open Design\helper.exe",
                "args": ["mcp"],
                "env": {"OD_SIDECAR_IPC_PATH": r"\\.\pipe\open-design"},
            }
        )
        self.assertTrue(bridge_errors)

    def test_validate_wsl_bridge_rejects_missing_relative_command(self) -> None:
        bridge_errors = validate_wsl_bridge_spec(
            {
                "command": "definitely-missing-open-design-helper",
                "args": ["mcp"],
                "env": {},
            }
        )
        self.assertIn("bridge command not found on PATH", " ".join(bridge_errors))

    def test_windows_install_info_uses_injected_dynamic_port_discovery(self) -> None:
        environment = build_environment_identity(
            platform_name="windows",
            machine="Win",
            user="User",
            home=r"C:\Users\User",
        )
        with tempfile.TemporaryDirectory() as tmp:
            helper = Path(tmp) / "open-design-helper.exe"
            helper.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            helper.chmod(helper.stat().st_mode | stat.S_IXUSR)
            InstallInfoHandler.helper_command = str(helper)
            server = LocalInstallInfoServer(("127.0.0.1", 0), InstallInfoHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                port = int(server.server_address[1])
                result = resolve_catalog_spec(
                    {
                        "resolution": {"kind": "open_design_install_info"},
                        "platforms": {
                            "windows": {
                                "preferred": "native",
                                "resolvers": ["local-install-info"],
                            }
                        },
                    },
                    environment,
                    daemon_url=None,
                    port_discovery=lambda discovered_environment: [port]
                    if discovered_environment.platform == "windows"
                    else [],
                )
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)
        self.assertEqual(result.status, "native")
        self.assertEqual(result.spec["command"], str(helper))

    @unittest.skipIf(os.name == "nt", "Requires POSIX executable and path semantics; run in WSL.")
    def test_unsupported_bridge_unverified_and_native_results(self) -> None:
        linux_environment = build_environment_identity(
            platform_name="linux",
            machine="Host",
            user="User",
            home="/home/user",
        )
        with tempfile.TemporaryDirectory() as tmp:
            helper = Path(tmp) / "helper"
            helper.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            helper.chmod(helper.stat().st_mode | stat.S_IXUSR)
            native_errors = validate_native_spec({"command": str(helper), "args": [], "env": {}}, linux_environment)
            self.assertEqual(native_errors, [])

            native = resolve_catalog_spec(
                {
                    "resolution": {"kind": "catalog_platforms"},
                    "platforms": {
                        "linux": {
                            "resolvers": [
                                {
                                    "name": "verified-linux-command",
                                    "command": str(helper),
                                    "args": ["mcp"],
                                }
                            ]
                        }
                    },
                },
                linux_environment,
                daemon_url=None,
            )
            unsupported = resolve_catalog_spec(
                {
                    "resolution": {"kind": "catalog_platforms"},
                    "platforms": {"linux": {"status": "unsupported", "resolvers": []}},
                },
                linux_environment,
                daemon_url=None,
            )
            bridge = resolve_catalog_spec(
                {
                    "resolution": {"kind": "catalog_platforms"},
                    "platforms": {
                        "linux": {
                            "resolvers": [
                                {
                                    "name": "verified-windows-bridge",
                                    "command": str(helper),
                                    "args": ["mcp"],
                                    "env": {},
                                }
                            ]
                        }
                    },
                },
                linux_environment,
                daemon_url=None,
            )
        self.assertEqual(native.status, "native")
        self.assertEqual(unsupported.status, "unsupported")
        self.assertEqual(bridge.status, "bridge")

    @unittest.skipIf(os.name == "nt", "Requires POSIX executable and path semantics; run in WSL.")
    def test_install_info_resolves_to_native_spec(self) -> None:
        environment = build_environment_identity(
            platform_name="macos",
            machine="Mac",
            user="User",
            home="/Users/user",
        )
        with tempfile.TemporaryDirectory() as tmp:
            helper = Path(tmp) / "open-design-helper"
            helper.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            helper.chmod(helper.stat().st_mode | stat.S_IXUSR)
            InstallInfoHandler.helper_command = str(helper)
            server = LocalInstallInfoServer(("127.0.0.1", 0), InstallInfoHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base_url = f"http://127.0.0.1:{server.server_address[1]}"
                result = resolve_catalog_spec(
                    {
                        "resolution": {"kind": "open_design_install_info"},
                        "platforms": {
                            "macos": {
                                "preferred": "native",
                                "resolvers": ["local-install-info"],
                            }
                        },
                    },
                    environment,
                    daemon_url=base_url,
                )
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)
        self.assertEqual(result.status, "native")
        self.assertEqual(result.spec["command"], str(helper))
        self.assertEqual(result.spec["daemonUrl"], "http://127.0.0.1:9999")

    def test_open_design_catalog_declares_platform_variants(self) -> None:
        catalog_path = Path(__file__).resolve().parent / "fixtures" / "open-design.json"
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        platforms = catalog.get("platforms")
        self.assertIsInstance(platforms, dict)
        for platform_name in ("macos", "windows", "linux", "wsl"):
            self.assertIn(platform_name, platforms)
            self.assertIsInstance(platforms[platform_name].get("resolvers"), list)
        self.assertEqual(platforms["macos"].get("status"), "native")
        self.assertEqual(platforms["windows"].get("status"), "native")
        self.assertIn(platforms["linux"].get("status"), {"unsupported", "bridge"})
        self.assertEqual(platforms["wsl"].get("status"), "unverified")

    def test_open_design_wsl_explicit_daemon_url_without_endpoint_is_unverified(self) -> None:
        catalog_path = Path(__file__).resolve().parent / "fixtures" / "open-design.json"
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        wsl_environment = build_environment_identity(
            platform_name="wsl",
            machine="Host",
            user="User",
            home="/home/user",
            wsl_distro="Ubuntu",
        )
        result = resolve_catalog_spec(
            catalog,
            wsl_environment,
            daemon_url="http://127.0.0.1:9",
            port_discovery=lambda _environment: [],
        )
        self.assertEqual(result.status, "unverified")
        self.assertIsNone(result.spec)

    @unittest.skipIf(os.name == "nt", "Requires POSIX executable and path semantics; run in WSL.")
    def test_open_design_wsl_explicit_daemon_url_with_endpoint_can_resolve_native(self) -> None:
        catalog_path = Path(__file__).resolve().parent / "fixtures" / "open-design.json"
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        wsl_environment = build_environment_identity(
            platform_name="wsl",
            machine="Host",
            user="User",
            home="/home/user",
            wsl_distro="Ubuntu",
        )
        with tempfile.TemporaryDirectory() as tmp:
            helper = Path(tmp) / "open-design-helper"
            helper.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            helper.chmod(helper.stat().st_mode | stat.S_IXUSR)
            InstallInfoHandler.helper_command = str(helper)
            server = LocalInstallInfoServer(("127.0.0.1", 0), InstallInfoHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base_url = f"http://127.0.0.1:{server.server_address[1]}"
                result = resolve_catalog_spec(
                    catalog,
                    wsl_environment,
                    daemon_url=base_url,
                    port_discovery=lambda _environment: [],
                )
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)
        self.assertEqual(result.status, "native")
        self.assertEqual(result.spec["command"], str(helper))

    @unittest.skipIf(os.name == "nt", "Requires POSIX executable and path semantics; run in WSL.")
    def test_wsl_verified_bridge_resolver_can_return_bridge(self) -> None:
        wsl_environment = build_environment_identity(
            platform_name="wsl",
            machine="Host",
            user="User",
            home="/home/user",
            wsl_distro="Ubuntu",
        )
        with tempfile.TemporaryDirectory() as tmp:
            helper = Path(tmp) / "bridge-helper"
            helper.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            helper.chmod(helper.stat().st_mode | stat.S_IXUSR)
            result = resolve_catalog_spec(
                {
                    "id": "open-design",
                    "resolution": {"kind": "catalog_platforms"},
                    "platforms": {
                        "wsl": {
                            "status": "unverified",
                            "resolvers": [
                                {
                                    "name": "verified-windows-bridge",
                                    "command": str(helper),
                                    "args": ["mcp"],
                                    "env": {},
                                }
                            ],
                        }
                    },
                },
                wsl_environment,
                daemon_url=None,
            )
        self.assertEqual(result.status, "bridge")
        self.assertEqual(result.spec["command"], str(helper))

    def test_instance_key_includes_environment_id(self) -> None:
        first_key = mcp_instance_key(
            {
                "environment_id": "wsl:host:ubuntu:user",
                "agent": "codex",
                "mcp": "open-design",
                "server_name": "open-design",
            }
        )
        second_key = mcp_instance_key(
            {
                "environment_id": "wsl:host:debian:user",
                "agent": "codex",
                "mcp": "open-design",
                "server_name": "open-design",
            }
        )
        self.assertNotEqual(first_key, second_key)

    def test_deep_set_server_preserves_unrelated_entries(self) -> None:
        merged = deep_set_server(
            {"mcpServers": {"keep-me": {"command": "existing"}}},
            ["mcpServers"],
            "open-design",
            {"command": "helper", "args": ["mcp"]},
        )
        self.assertIn("keep-me", merged["mcpServers"])
        self.assertIn("open-design", merged["mcpServers"])

    def test_verification_result_supports_unknown_operational_status(self) -> None:
        verification = VerificationResult(configured=True, registered=True, operational=None, evidence=[])
        self.assertIsNone(verification.operational)

    def test_state_writer_rejects_invalid_json_without_rewrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            mcp_root = Path(tmp)
            state_file = mcp_root / "state" / "mcp_instances.json"
            state_file.parent.mkdir(parents=True)
            original = b"{not json"
            state_file.write_bytes(original)
            with self.assertRaises((json.JSONDecodeError, StateConflict)):
                record_instance(
                    mcp_root,
                    {
                        "environment_id": "linux:host:user",
                        "mcp": "open-design",
                        "agent": "codex",
                        "server_name": "open-design",
                    },
                )
            self.assertEqual(state_file.read_bytes(), original)

    def test_state_writer_migrates_legacy_state_to_version_2(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            mcp_root = Path(tmp)
            state_file = mcp_root / "state" / "mcp_instances.json"
            state_file.parent.mkdir(parents=True)
            state_file.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "instances": [
                            {
                                "mcp": "open-design",
                                "agent": "codex",
                                "server_name": "open-design",
                                "machine": "old-host",
                                "platform": "darwin",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            record_instance(
                mcp_root,
                {
                    "environment_id": "macos:new-host:user",
                    "mcp": "open-design",
                    "agent": "codex",
                    "server_name": "open-design",
                    "verification": {"configured": True, "registered": True, "operational": None},
                },
            )
            state = json.loads(state_file.read_text(encoding="utf-8"))
        self.assertEqual(state["version"], 2)
        self.assertEqual(len(state["instances"]), 2)
        self.assertIn("environment_id", state["instances"][0])

    def test_migrate_state_only_preview_does_not_write_and_apply_normalizes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            mcp_root = Path(tmp)
            state_file = mcp_root / "state" / "mcp_instances.json"
            state_file.parent.mkdir(parents=True)
            legacy_state = {
                "version": 1,
                "instances": [
                    {
                        "mcp": "open-design",
                        "agent": "codex",
                        "strategy": "cli",
                        "server_name": "open-design",
                        "machine": "old-host",
                        "platform": "darwin",
                        "last_sync": 123,
                        "daemonUrl": "http://127.0.0.1:54947",
                    }
                ],
            }
            state_file.write_text(json.dumps(legacy_state), encoding="utf-8")

            preview = migrate_mcp_state(mcp_root, apply=False)
            self.assertTrue(preview["ok"])
            self.assertEqual(preview["state"]["version"], 2)
            self.assertEqual(json.loads(state_file.read_text(encoding="utf-8"))["version"], 1)

            applied = migrate_mcp_state(mcp_root, apply=True)
            self.assertTrue(applied["ok"])
            state = json.loads(state_file.read_text(encoding="utf-8"))

        instance = state["instances"][0]
        self.assertEqual(state["version"], 2)
        self.assertEqual(instance["platform"], "macos")
        self.assertEqual(instance["resolution_status"], "native")
        self.assertEqual(
            instance["verification"],
            {"configured": True, "registered": False, "operational": None},
        )
        self.assertEqual(instance["evidence"]["daemonUrl"], "http://127.0.0.1:54947")

    def test_audit_rejects_legacy_state_and_accepts_migrated_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            mcp_root = Path(tmp)
            (mcp_root / "catalog").mkdir(parents=True)
            (mcp_root / "targets").mkdir()
            (mcp_root / "state").mkdir()
            (mcp_root / "catalog" / "example.json").write_text(
                json.dumps(
                    {
                        "id": "example",
                        "server_name": "example",
                        "label": "Example",
                        "description": "Example MCP",
                        "resolution": {"kind": "catalog_platforms"},
                    }
                ),
                encoding="utf-8",
            )
            (mcp_root / "targets" / "agents.json").write_text(json.dumps({"agents": {}}), encoding="utf-8")
            state_file = mcp_root / "state" / "mcp_instances.json"
            state_file.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "instances": [
                            {
                                "mcp": "example",
                                "agent": "codex",
                                "server_name": "example",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            legacy = audit_shared_mcps(mcp_root)
            self.assertFalse(legacy["ok"])
            self.assertIn("version must be 2", " ".join(legacy["errors"]))

            migrate_mcp_state(mcp_root, apply=True)
            migrated = audit_shared_mcps(mcp_root)

        self.assertTrue(migrated["ok"])

    def test_audit_rejects_state_instances_with_missing_identity_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            mcp_root = self.make_audit_root(
                Path(tmp),
                state={
                    "version": 2,
                    "instances": [
                        {
                            "environment_id": "macos:host:user",
                            "mcp": "example",
                            "agent": "",
                            "server_name": "example",
                            "resolution_status": "native",
                            "verification": {"configured": True, "registered": False, "operational": None},
                        }
                    ],
                },
            )
            result = audit_shared_mcps(mcp_root)

        self.assertFalse(result["ok"])
        self.assertIn("agent must be a non-empty string", " ".join(result["errors"]))

    def test_audit_rejects_duplicate_state_instance_keys(self) -> None:
        instance = {
            "environment_id": "macos:host:user",
            "mcp": "example",
            "agent": "codex",
            "server_name": "example",
            "resolution_status": "native",
            "verification": {"configured": True, "registered": False, "operational": None},
        }
        with tempfile.TemporaryDirectory() as tmp:
            mcp_root = self.make_audit_root(
                Path(tmp),
                state={
                    "version": 2,
                    "instances": [dict(instance), dict(instance)],
                },
            )
            result = audit_shared_mcps(mcp_root)

        self.assertFalse(result["ok"])
        self.assertIn("duplicate instance key", " ".join(result["errors"]))

    def test_audit_rejects_invalid_catalog_platform_and_resolver(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            mcp_root = self.make_audit_root(
                Path(tmp),
                catalog={
                    "id": "example",
                    "server_name": "example",
                    "label": "Example",
                    "description": "Example MCP",
                    "resolution": {"kind": "catalog_platforms"},
                    "platforms": {
                        "darwin": {
                            "status": "native",
                            "resolvers": ["unknown-resolver"],
                        }
                    },
                },
            )
            result = audit_shared_mcps(mcp_root)

        self.assertFalse(result["ok"])
        errors = " ".join(result["errors"])
        self.assertIn("unsupported platform `darwin`", errors)
        self.assertIn("unsupported resolver `unknown-resolver`", errors)

    def test_audit_rejects_invalid_target_shape_and_live_shared_config_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            live_config = Path(tmp) / ".agents" / "mcp" / "targets" / "codex-config.toml"
            mcp_root = self.make_audit_root(
                Path(tmp),
                targets={
                    "agents": {
                        "bad-json": {
                            "strategy": "json",
                            "config_path": str(live_config),
                            "key_path": "mcpServers",
                        },
                        "bad-cli": {
                            "strategy": "cli",
                            "bin": "codex",
                            "add_prefix": "mcp add",
                        },
                    }
                },
            )
            result = audit_shared_mcps(mcp_root)

        self.assertFalse(result["ok"])
        errors = " ".join(result["errors"])
        self.assertIn("key_path must be a list", errors)
        self.assertIn("add_prefix must be a list", errors)
        self.assertIn("must not point inside shared MCP root", errors)

    @unittest.skipIf(os.name == "nt", "Requires POSIX executable and path semantics; run in WSL.")
    def test_sync_preview_and_apply_gate_without_live_config_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / ".agents" / "mcp"
            (root / "catalog").mkdir(parents=True)
            (root / "targets").mkdir()
            (root / "state").mkdir()
            (root / "README.md").write_text("test\n", encoding="utf-8")
            helper = Path(tmp) / "helper"
            helper.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            helper.chmod(helper.stat().st_mode | stat.S_IXUSR)
            config = Path(tmp) / "agent.json"
            (root / "catalog" / "example.json").write_text(
                json.dumps(
                    {
                        "id": "example",
                        "server_name": "example",
                        "resolution": {"kind": "catalog_platforms"},
                        "platforms": {
                            "macos": {
                                "resolvers": [
                                    {
                                        "name": "verified-command",
                                        "command": str(helper),
                                        "args": ["mcp"],
                                    }
                                ]
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            (root / "targets" / "agents.json").write_text(
                json.dumps(
                    {
                        "agents": {
                            "json-agent": {
                                "strategy": "json",
                                "config_path": str(config),
                                "key_path": ["mcpServers"],
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            args = argparse.Namespace(
                mcp="example",
                agent="json-agent",
                name=None,
                daemon_url=None,
                start=str(root),
                apply=False,
                yes=False,
                platform_name="macos",
                machine="Mac",
                user="User",
                home="/Users/user",
                wsl_distro=None,
            )
            preview = sync(args)
            self.assertTrue(preview["ok"])
            self.assertFalse(config.exists())
            args.apply = True
            args.yes = False
            gated = sync(args)
            self.assertFalse(gated["ok"])
            self.assertIn("Refusing to apply", " ".join(gated["errors"]))
            args.yes = True
            applied = sync(args)
            self.assertTrue(applied["ok"])
            self.assertTrue(config.exists())


if __name__ == "__main__":
    unittest.main()
