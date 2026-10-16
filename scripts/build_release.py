#!/usr/bin/env python3
"""Build a ZIP from audited Git-tracked source only, never from a live installation."""
from pathlib import Path
import hashlib
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.1.0"

def main():
    subprocess.run([sys.executable, "-B", str(ROOT / "scripts/check.py")], check=True, cwd=ROOT)
    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
    files = [ROOT / p for p in tracked if p]
    if not files: raise RuntimeError("Stage and audit release sources first")
    for path in files:
        if path.is_symlink() or not path.is_file(): raise RuntimeError("Only regular tracked files may enter a release")
    dist = ROOT / "dist"; dist.mkdir(exist_ok=True)
    out = dist / f"agent-shared-system-v{VERSION}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            info = zipfile.ZipInfo("AgentShared/" + path.relative_to(ROOT).as_posix(), date_time=(2026,10,16,0,0,0))
            info.external_attr = (0o100755 if path.suffix in {".sh", ".command"} else 0o100644) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, path.read_bytes())
    checksum = hashlib.sha256(out.read_bytes()).hexdigest()
    (dist / "SHA256SUMS").write_text(f"{checksum}  {out.name}\n", encoding="utf-8")
    print(f"Built {out.name}: {len(files)} files; SHA256SUMS written")
    return 0

if __name__ == "__main__": raise SystemExit(main())
