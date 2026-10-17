#!/usr/bin/env python3
"""Run tests against an initialized temporary source, never the user's installation."""
from pathlib import Path
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]

def main():
    with tempfile.TemporaryDirectory(prefix="agent-shared-tests-") as tmp:
        root = Path(tmp) / "framework"
        shutil.copytree(ROOT, root, ignore=shutil.ignore_patterns(".git", "__pycache__", "dist", "build", ".venv"))
        spec = importlib.util.spec_from_file_location("bootstrap", root / "scripts/setup.py")
        setup = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(setup)
        setup.initialize_missing()
        dirs = [root / "tests", root / ".agents/tests", *sorted((root / ".agents/skills").glob("*/tests"))]
        for directory in dirs:
            print(f"Testing {directory.relative_to(root)}", flush=True)
            result = subprocess.run([sys.executable, "-B", "-m", "unittest", "discover", "-s", str(directory)], cwd=root, env={**os.environ, "PYTHONUTF8": "1"})
            if result.returncode:
                return result.returncode
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
