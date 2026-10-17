#!/usr/bin/env python3
"""Preview-first local onboarding. Never installs an Agent or changes its global prompt."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import venv

ROOT = Path(__file__).resolve().parents[1]
SHARED = ROOT / ".agents"
TARGETS = {"codex": ".codex/skills", "claude": ".claude/skills", "gemini": ".gemini/skills",
           "opencode": ".opencode/skills", "hermes": ".hermes/skills", "workbuddy": ".workbuddy/skills",
           "cursor": ".cursor/skills-cursor"}


def exists(path: Path) -> bool:
    return os.path.lexists(path)


def is_link(path: Path) -> bool:
    return path.is_symlink() or bool(getattr(os.path, "isjunction", lambda _: False)(path))


def same_link(path: Path, source: Path) -> bool:
    try:
        return is_link(path) and path.resolve() == source.resolve()
    except (OSError, RuntimeError):
        return False


def build_plan(home: Path, target: Path) -> list[dict]:
    source = SHARED / "skills"
    names = sorted(p.name for p in source.iterdir() if p.is_dir() and (p / "SKILL.md").is_file())
    unified = home / ".agents" / "skills"
    pairs = [(source / n, unified / n) for n in names]
    if target != unified:
        pairs += [(unified / n, target / n) for n in names]
    pairs += [(SHARED / n, home / ".agents" / n) for n in ("memories", "mcp")]
    plan = []
    for src, dst in pairs:
        # Every ancestor must remain a real local directory; do not follow an existing
        # ~/.agents link into an unrelated shared system or a private skill checkout.
        unsafe_parent = any(is_link(p) for p in dst.parents if p != home and p.is_relative_to(home))
        status = "conflict" if unsafe_parent else "skip" if same_link(dst, src) else "conflict" if exists(dst) else "create"
        plan.append({"source": str(src), "path": str(dst), "action": status})
    return plan


def make_directory_link(dst: Path, src: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        env = dict(os.environ, ASS_LINK_PATH=str(dst), ASS_LINK_TARGET=str(src))
        subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                        "$ErrorActionPreference='Stop'; New-Item -ItemType Junction -Path $env:ASS_LINK_PATH -Target $env:ASS_LINK_TARGET | Out-Null"],
                       env=env, check=True)
    else:
        dst.symlink_to(src, target_is_directory=True)


def remove_link(path: Path) -> None:
    if not is_link(path):
        raise RuntimeError(f"Refusing to remove a real file/directory: {path}")
    if os.name == "nt" and not path.is_symlink():
        path.rmdir()
    else:
        path.unlink()


def initialize_missing() -> list[Path]:
    created = []
    pairs = [(p, p.with_name(p.name.replace(".example.md", ".md")))
             for p in (SHARED / "memories").glob("*.example.md")]
    pairs += [(p, p.with_name(p.name.replace(".example.json", ".json")))
              for p in SHARED.rglob("*.example.json")]
    for src, dst in pairs:
        if exists(dst):
            continue
        # Exclusive creation prevents concurrent bootstrap from overwriting data.
        try:
            with dst.open("x", encoding="utf-8") as f:
                f.write(src.read_text(encoding="utf-8"))
            created.append(dst)
        except FileExistsError:
            continue
    return created


def runtime_python(home: Path) -> Path:
    base = home / ".local" / "share" / "agent-shared-system" / "venv"
    return base / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def prepare_dependencies(home: Path) -> None:
    python = runtime_python(home)
    if not python.exists():
        venv.EnvBuilder(with_pip=True).create(python.parent.parent)
    subprocess.run([str(python), "-m", "pip", "install", "--disable-pip-version-check", "-r", str(ROOT / "requirements.txt")], check=True)
    print(f"Local runtime ready: {python}")


def helper(target: Path, local_root: Path, *, unified: bool = False) -> None:
    cmd = [sys.executable, "-X", "utf8", "-B", str(SHARED / "skills/agent-shared-skills/scripts/sync_agent_skill_links.py"),
           "--shared-root", str(SHARED / "skills"), "--local-root", str(local_root),
           "--target-dir", str(target), "--target-id", "unified" if unified else "selected-agent",
           "--create-roots", "--no-record", "--apply", "--yes", "--format", "json"]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "Skill link operation failed")


def apply_plan(plan: list[dict], home: Path, target: Path) -> None:
    if any(p["action"] == "conflict" for p in plan):
        raise RuntimeError("Existing files/directories or links conflict. Nothing was replaced; choose another target or review conflicts explicitly.")
    initial = {p["path"] for p in plan if p["action"] == "create"}
    try:
        # Use the existing tested skill installer rather than replace its lifecycle logic.
        unified = home / ".agents/skills"
        helper(unified, SHARED / "skills", unified=True)
        if target != unified:
            helper(target, unified)
        for row in plan:
            dst, src = Path(row["path"]), Path(row["source"])
            if dst.name in {"memories", "mcp"} and row["action"] == "create":
                if exists(dst):
                    raise RuntimeError(f"Target changed after preview: {dst}")
                make_directory_link(dst, src)
        if not all(same_link(Path(p["path"]), Path(p["source"])) for p in plan):
            raise RuntimeError("Post-apply link verification failed")
        initialize_missing()
    except Exception:
        # Also find links made by a helper before it reported a later failure.
        for row in reversed(plan):
            dst, src = Path(row["path"]), Path(row["source"])
            if str(dst) in initial and same_link(dst, src):
                remove_link(dst)
        raise
    print("Links verified. Reopen/reload the selected Agent, ask it to read agent-shared-skills, then query the Atlas sample.")
    print("File/link checks do not prove Agent discovery, CLI/MCP readiness, or model behavior.")


def main(argv: list[str] | None = None) -> int:
    if sys.version_info < (3, 12):
        print("Python 3.12+ is required.", file=sys.stderr)
        return 2
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent", choices=sorted(TARGETS))
    parser.add_argument("--target-dir", type=Path, help="Actual Agent skills directory; verify it in the current client")
    parser.add_argument("--local-home", type=Path, default=Path.home(), help="Local user home; tests can use an isolated directory")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--interactive", action="store_true")
    parser.add_argument("--install-deps", action="store_true")
    parser.add_argument("--uninstall", action="store_true", help="Only unlink matching project-owned entries; keep shared/user files")
    args = parser.parse_args(argv)
    home = args.local_home.expanduser().absolute()
    if args.install_deps:
        prepare_dependencies(home)
        return 0
    if args.interactive and not args.uninstall and importlib.util.find_spec("yaml") is None:
        python = runtime_python(home)
        if not python.exists():
            answer = input("需要联网准备本机 Python 依赖；只写入本机专用环境。继续？[y/N]: ").strip().casefold()
            if answer != "y":
                print("Cancelled; dependencies were not installed.")
                return 0
            prepare_dependencies(home)
        if python.resolve() != Path(sys.executable).resolve():
            return subprocess.run([str(python), "-B", str(Path(__file__).resolve()), *sys.argv[1:]]).returncode
    if args.interactive:
        print("Agent Shared System / 本机接入（不会安装 Agent 或修改全局提示词）")
        print("Agent ids: " + ", ".join(TARGETS))
        name = input("Agent id [codex]: ").strip() or "codex"
        if name not in TARGETS:
            parser.error("Unknown Agent; use --target-dir for another client")
        default = home / TARGETS[name]
        args.target_dir = Path(input(f"实际 Agent skills 目录 [{default}]: ").strip() or str(default)).expanduser()
        args.agent = name
    if not args.target_dir and not args.agent:
        parser.error("Choose --agent or --target-dir, or run --interactive")
    target = (args.target_dir or (home / TARGETS[args.agent])).expanduser().absolute()
    if not target.is_absolute() or target.resolve().is_relative_to(ROOT.resolve()):
        parser.error("Agent target must be outside this shared source")
    plan = build_plan(home, target)
    print(json.dumps({"shared_root": str(SHARED), "selected_agent_directory": str(target), "read_only": not args.apply,
                      "links": plan, "uninstall": args.uninstall}, ensure_ascii=False, indent=2))
    apply = args.apply
    if args.interactive:
        apply = input("应用以上接入计划？输入 Y / Apply? [y/N]: ").strip().casefold() == "y"
    if not apply:
        return 0 if not any(p["action"] == "conflict" for p in plan) else 1
    if not args.yes and not args.interactive:
        if input("Apply only the displayed paths? [y/N]: ").strip().casefold() != "y":
            print("Cancelled; nothing changed.")
            return 0
    if args.uninstall:
        for row in reversed(plan):
            dst, src = Path(row["path"]), Path(row["source"])
            if same_link(dst, src):
                remove_link(dst)
        print("Matching links removed. Shared files, user data, configs and runtime retained.")
        return 0
    if importlib.util.find_spec("yaml") is None:
        python = runtime_python(home)
        if python.exists() and python.resolve() != Path(sys.executable).resolve():
            command = [str(python), "-B", str(Path(__file__).resolve()), *sys.argv[1:]]
            return subprocess.run(command).returncode
        print("PyYAML missing. Run this script with --install-deps, then repeat the preview/apply.", file=sys.stderr)
        return 2
    apply_plan(plan, home, target)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, subprocess.CalledProcessError, KeyboardInterrupt) as exc:
        print(f"Setup stopped: {exc}", file=sys.stderr)
        raise SystemExit(1)
