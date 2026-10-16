#!/usr/bin/env python3
"""Validate a clean source/release without printing potential secret values."""
from pathlib import Path
import ast
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
IGNORED = {".git", "__pycache__", "dist", "build", ".venv"}

def source_files(root=ROOT):
    return sorted(p for p in root.rglob("*") if p.is_file() and not any(s in IGNORED for s in p.relative_to(root).parts))

def main():
    errors = []
    files = source_files()
    for p in files:
        rel = str(p.relative_to(ROOT))
        if p.is_symlink(): errors.append(f"Source must not contain symlinks: {rel}")
        if p.name in {".env", ".DS_Store"} or p.suffix in {".key", ".pem", ".sqlite", ".db", ".log"}:
            errors.append(f"Forbidden release file: {rel}")
        if p.suffix in {".png", ".jpg", ".zip"}: continue
        try: content = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            errors.append(f"Unexpected binary: {rel}"); continue
        if any(ord(c) < 32 and c not in "\t\n\r" for c in content):
            errors.append(f"Unexpected control character: {rel}")
        if p.suffix == ".py":
            try: ast.parse(content)
            except SyntaxError: errors.append(f"Python syntax error: {rel}")
        if p.suffix == ".json":
            try: json.loads(content)
            except ValueError: errors.append(f"JSON parse error: {rel}")
        if p.name != "check.py" and re.search(r"(?:/Users/|/home/)(?:severusgao|Administrator)(?:/|\b)|com~apple~CloudDocs|ObsidianSeverusgao", content):
            errors.append(f"Private path marker: {rel}")
        scan = content
        if rel in {".agents/skills/agent-shared-evolution/tests/test_evidence.py", "scripts/check.py"}:
            scan = scan.replace("-----BEGIN PRIVATE KEY-----", "SYNTHETIC_KEY_HEADER")
        if rel in {".agents/skills/agent-shared-memories/tests/test_lint_memories.py", "scripts/check.py"}:
            scan = scan.replace("sk-abcdefghijklmnopqrstuvwxyz1234567890", "SYNTHETIC_KEY")
        if re.search(r"(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|sk-(?:proj-)?[A-Za-z0-9_-]{32,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)", scan):
            errors.append(f"Potential secret; inspect locally: {rel}")
        if p.suffix == ".md":
            for link in re.findall(r"\[[^\]]*\]\(([^)]+)\)", re.sub(r"(?ms)^(`{3,}|~{3,}).*?^\1[^\n]*$", "", content)):
                link = link.strip("<>").split("#", 1)[0]
                if not link or re.match(r"[a-z]+:", link) or "<" in link or " " in link: continue
                target = p.parent / link
                alt = target.with_name(target.stem + ".example" + target.suffix)
                if not target.exists() and not alt.exists(): errors.append(f"Broken Markdown link: {rel} -> {link}")
    for p in ROOT.rglob("AGENTS.md"):
        if any(s in IGNORED for s in p.relative_to(ROOT).parts): continue
        twin = p.with_name("CLAUDE.md")
        if not twin.is_file() or twin.read_bytes() != p.read_bytes(): errors.append(f"Instruction pair mismatch: {p.relative_to(ROOT)}")
    with tempfile.TemporaryDirectory(prefix="agent-shared-lint-") as tmp:
        copy = Path(tmp) / "source"
        shutil.copytree(ROOT, copy, ignore=shutil.ignore_patterns(*IGNORED))
        spec = importlib.util.spec_from_file_location("lint_setup", copy / "scripts/setup.py")
        setup = importlib.util.module_from_spec(spec); spec.loader.exec_module(setup); setup.initialize_missing()
        for cmd in [
            [sys.executable, "-B", str(copy / ".agents/skills/agent-shared-memories/scripts/lint_memories.py"), "--root", str(copy / ".agents/memories")],
            [sys.executable, "-B", str(copy / ".agents/scripts/generate-shared-system-readme.py"), "--root", str(copy), "--check"],
        ]:
            result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
            if result.returncode: errors.append(result.stdout + result.stderr)
    if errors:
        print("\n".join(errors)); return 1
    print(f"Source checks passed ({len(files)} files): syntax, templates, links, instruction pairs, generated docs and bounded secret/path scan.")
    return 0

if __name__ == "__main__": raise SystemExit(main())
