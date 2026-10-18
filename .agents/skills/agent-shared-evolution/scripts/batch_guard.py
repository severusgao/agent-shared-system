"""Snapshot and recover an authorized batch; never applies proposed updates."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

sys.dont_write_bytecode = True

from evidence import relative_target, safe_local, redact


def sha(path: Path) -> str | None:
    if path.is_dir():
        raise ValueError("batch targets must be files")
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def target(root: Path, name: str) -> Path:
    relative_target(name)
    path = root / name
    if not path.resolve().is_relative_to(root.resolve()) or path.is_symlink():
        raise ValueError("batch target must stay in canonical root, without file symlinks")
    if path.name in {"token.txt", ".env", "auth.json"}:
        raise ValueError("credential files are not batch targets")
    if path.parent.exists():
        for sibling in path.parent.iterdir():
            label = sibling.name.casefold()
            if sibling != path and path.stem.casefold() in label and any(marker in label for marker in ("conflicted copy", "sync-conflict", "icloud conflict")):
                raise ValueError("possible sync conflict beside " + name)
    return path


def save(manifest: Path, data: dict) -> None:
    manifest = safe_local(manifest)
    tmp = manifest.with_name(manifest.name + ".writing")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(manifest)


def snapshot(root: Path, names: list[str], output: Path, approval: str) -> Path:
    if not approval.strip() or not isinstance(names, list) or not names or len(set(names)) != len(names):
        raise ValueError("actual approval reference and unique targets required")
    root, output = root.resolve(), safe_local(output)
    if output.is_relative_to(root):
        raise ValueError("backup must be outside shared root")
    previous = resume_cleanup(output.parent)
    if previous["pending"]:
        raise ValueError("unfinished temporary batches require review before another snapshot: " + ", ".join(previous["pending"]))
    contents = {}
    for name in names:
        path = target(root, name)
        data = path.read_bytes() if path.is_file() else None
        contents[name] = (data, stat.S_IMODE(path.stat().st_mode) if data is not None else None)
    output.mkdir(parents=True, exist_ok=False)
    files = {name: {"before": hashlib.sha256(data).hexdigest() if data is not None else None,
                    "after": None, "mode": mode, "owned": False}
             for name, (data, mode) in contents.items()}
    manifest = output / "manifest.json"
    batch = {"schema_version": 1, "kind": "agent-shared-evolution-temporary-batch",
             "root": str(root), "approval_reference": approval, "status": "preparing", "files": files}
    save(manifest, batch)  # Register ownership before storing any old contents.
    for name, (data, mode) in contents.items():
        if data is not None:
            backup = output / "originals" / name
            backup.parent.mkdir(parents=True, exist_ok=True)
            backup.write_bytes(data)
    batch["status"] = "snapshotted"
    save(manifest, batch)
    check(manifest)
    return manifest


def load(manifest: Path) -> tuple[dict, Path]:
    manifest = safe_local(manifest)
    data = json.loads(manifest.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or not data.get("approval_reference") or not isinstance(data.get("files"), dict):
        raise ValueError("invalid batch manifest")
    root = Path(data["root"]).resolve()
    for name in data["files"]:
        target(root, name)
    return data, root


def check(manifest: Path) -> list[str]:
    data, root = load(manifest)
    errors = [name for name, info in data["files"].items() if sha(target(root, name)) != info["before"]]
    if errors:
        raise ValueError("proposal baseline changed: " + ", ".join(errors))
    return list(data["files"])


def seal(manifest: Path, expected: dict[str, str | None]) -> None:
    data, root = load(manifest)
    if data["status"] not in {"snapshotted", "sealed"} or set(expected) != set(data["files"]):
        raise ValueError("expected digests must cover the complete active batch")
    for name, value in expected.items():
        if value is not None and (not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value)):
            raise ValueError("expected digest must be SHA-256 or null")
        if sha(target(root, name)) != value:
            raise ValueError("written content differs from author's expected digest: " + name)
    for name, value in expected.items():
        data["files"][name]["after"] = value
        data["files"][name]["owned"] = value != data["files"][name]["before"]
    data["status"] = "sealed"
    save(manifest, data)


def rollback(manifest: Path) -> list[str]:
    data, root = load(manifest)
    if data["status"] != "sealed":
        raise ValueError("register author's expected post-write digests before recovery")
    restore = []
    for name, info in data["files"].items():
        if not info["owned"]:
            continue
        path = target(root, name)
        if sha(path) != info["after"]:
            raise ValueError("later edit detected; automatic recovery stopped: " + name)
        original = manifest.parent / "originals" / name
        content = original.read_bytes() if info["before"] is not None else None
        if content is not None and hashlib.sha256(content).hexdigest() != info["before"]:
            raise ValueError("backup integrity failure: " + name)
        restore.append((name, path, info, content))
    for name, path, info, content in restore:
        # Recheck just before writing. This is local conflict detection, not a distributed lock.
        if sha(path) != info["after"]:
            raise ValueError("concurrent edit during recovery: " + name)
        if content is None:
            if path.exists():
                path.unlink()
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            temp = path.with_name("." + path.name + ".evolution-restore")
            temp.write_bytes(content)
            if sha(path) != info["after"]:
                temp.unlink()
                raise ValueError("concurrent edit during recovery: " + name)
            os.chmod(temp, info["mode"])
            temp.replace(path)
    data["status"] = "rolled_back"
    save(manifest, data)
    return [name for name, _, _, _ in restore]


def inventory(manifest: Path, data: dict, require_originals: bool = False) -> list[Path]:
    """Remove only files this snapshot created; foreign entries stop all cleanup."""
    directory = manifest.parent
    if directory.is_symlink() or manifest.is_symlink() or data.get("kind") != "agent-shared-evolution-temporary-batch":
        raise ValueError("cleanup requires an owned temporary batch without links")
    allowed_files = {"manifest.json"}
    allowed_dirs = set()
    for name, info in data["files"].items():
        if info["before"] is None:
            continue
        original = Path("originals") / name
        allowed_files.add(original.as_posix())
        allowed_dirs.update(p.as_posix() for p in original.parents if p != Path("."))
        path = directory / original
        if require_originals and (not path.is_file() or sha(path) != info["before"]):
            raise ValueError("backup integrity failure before cleanup: " + name)
    entries = list(directory.rglob("*"))
    for path in entries:
        relative = path.relative_to(directory).as_posix()
        if path.is_symlink() or (relative not in (allowed_dirs if path.is_dir() else allowed_files)):
            raise ValueError("foreign entry in temporary batch; cleanup stopped: " + relative)
    return entries


def terminal_check(data: dict, root: Path) -> None:
    expected = "after" if data["status"] == "verified" else "before"
    for name, info in data["files"].items():
        if sha(target(root, name)) != info[expected]:
            raise ValueError("source changed after batch completion; cleanup stopped: " + name)


def cleanup_completed(manifest: Path) -> dict:
    data, root = load(manifest)
    if data["status"] not in {"verified", "rolled_back_verified"}:
        raise ValueError("cleanup requires verified application or verified recovery")
    receipt = safe_local(Path(data["completion_receipt"]))
    if not receipt.is_file() or receipt.resolve().is_relative_to(manifest.parent.resolve()) or sha(receipt) != data["completion_receipt_sha256"]:
        raise ValueError("completion receipt missing or changed; cleanup stopped")
    terminal_check(data, root)
    entries = inventory(manifest, data)
    # Keep the manifest until last so an interrupted deletion can resume next time.
    for path in sorted(entries, key=lambda p: len(p.parts), reverse=True):
        if path == manifest:
            continue
        if path.is_dir():
            path.rmdir()
        else:
            path.unlink()
    manifest.unlink()
    manifest.parent.rmdir()
    return {"status": "completed_and_cleaned", "receipt": str(receipt)}


def finish(manifest: Path, verification: Path, receipt: Path) -> dict:
    manifest, verification, receipt = map(safe_local, (manifest, verification, receipt))
    data, root = load(manifest)
    if data["status"] not in {"sealed", "rolled_back", "verified", "rolled_back_verified"}:
        raise ValueError("seal or recover the batch before completing it")
    for path in (verification, receipt):
        if path.resolve().is_relative_to(manifest.parent.resolve()):
            raise ValueError("verification and completion receipts must survive outside the temporary batch")
    proof = json.loads(verification.read_text(encoding="utf-8"))
    checks = proof.get("checks")
    if proof.get("status") != "passed" or not isinstance(checks, list) or not checks:
        raise ValueError("actual successful verification checks required")
    for item in checks:
        if not isinstance(item, dict) or not item.get("name") or type(item.get("exit_code")) is not int or item["exit_code"] != 0:
            raise ValueError("all required checks must have exit code zero")
        evidence = safe_local(Path(item["evidence_file"]))
        if not evidence.is_file() or evidence.resolve().is_relative_to(manifest.parent.resolve()) or sha(evidence) != item.get("sha256"):
            raise ValueError("verification artifact missing, changed, or inside cleanup target")
    recovered = data["status"] in {"rolled_back", "rolled_back_verified"}
    terminal = dict(data, status="rolled_back_verified" if recovered else "verified")
    terminal_check(terminal, root)
    inventory(manifest, data, require_originals=data["status"] in {"sealed", "rolled_back"})
    summary = {"schema_version": 1, "batch_id": manifest.parent.name,
               "approval_reference": data["approval_reference"], "outcome": terminal["status"],
               "files": data["files"], "verification_sha256": sha(verification),
               "verified_checks": len(checks)}
    if receipt.exists():
        previous = json.loads(receipt.read_text(encoding="utf-8"))
        if any(previous.get(k) != v for k, v in summary.items()):
            raise ValueError("different completion receipt already exists")
        summary = previous
    else:
        summary["completed_utc"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        receipt.parent.mkdir(parents=True, exist_ok=True)
        save(receipt, summary)
    terminal.update(completion_receipt=str(receipt), completion_receipt_sha256=sha(receipt))
    save(manifest, terminal)
    return cleanup_completed(manifest)


def resume_preparation(manifest: Path) -> None:
    data, root = load(manifest)
    check(manifest)
    inventory(manifest, data)
    contents = {}
    for name, info in data["files"].items():
        if info["before"] is None:
            continue
        original = manifest.parent / "originals" / name
        if original.exists():
            if sha(original) != info["before"]:
                raise ValueError("partial backup changed: " + name)
        else:
            content = target(root, name).read_bytes()
            if hashlib.sha256(content).hexdigest() != info["before"]:
                raise ValueError("source changed during preparation: " + name)
            contents[name] = content
    for name, content in contents.items():
        if sha(target(root, name)) != data["files"][name]["before"]:
            raise ValueError("concurrent source change during preparation: " + name)
        original = manifest.parent / "originals" / name
        original.parent.mkdir(parents=True, exist_ok=True)
        original.write_bytes(content)
    data["status"] = "snapshotted"
    save(manifest, data)


def resume_cleanup(directory: Path) -> dict:
    directory = safe_local(directory)
    result = {"cleaned": [], "pending": []}
    if not directory.exists():
        return result
    for child in sorted(directory.iterdir()):
        if child.is_symlink() or not child.is_dir():
            continue
        manifest = child / "manifest.json"
        if not manifest.is_file() or manifest.is_symlink():
            continue
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            if data.get("kind") != "agent-shared-evolution-temporary-batch":
                continue  # Legacy batches need their own approved, verified cleanup.
            if data.get("status") in {"verified", "rolled_back_verified"}:
                cleanup_completed(manifest)
                result["cleaned"].append(child.name)
            else:
                if data["status"] == "preparing":
                    resume_preparation(manifest)
                result["pending"].append(child.name)
        except (OSError, ValueError, KeyError, TypeError):
            result["pending"].append(child.name)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    cmd = sub.add_parser("snapshot")
    cmd.add_argument("--root", type=Path, required=True)
    cmd.add_argument("--targets", type=Path, required=True)
    cmd.add_argument("--output", type=Path, required=True)
    cmd.add_argument("--approval-ref", required=True)
    for name in ("check", "seal", "rollback"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--manifest", type=Path, required=True)
        if name == "seal":
            cmd.add_argument("--expected", type=Path, required=True)
    cmd = sub.add_parser("finish")
    cmd.add_argument("--manifest", type=Path, required=True)
    cmd.add_argument("--verification", type=Path, required=True)
    cmd.add_argument("--receipt", type=Path, required=True)
    cmd = sub.add_parser("resume-cleanup")
    cmd.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "snapshot":
            result = {"manifest": str(snapshot(args.root, json.loads(args.targets.read_text(encoding="utf-8")), args.output, args.approval_ref))}
        elif args.command == "check":
            result = {"baseline_valid": True, "targets": check(args.manifest)}
        elif args.command == "seal":
            seal(args.manifest, json.loads(args.expected.read_text(encoding="utf-8")))
            result = {"status": "sealed"}
        elif args.command == "rollback":
            result = {"status": "rolled_back", "restored": rollback(args.manifest)}
        elif args.command == "finish":
            result = finish(args.manifest, args.verification, args.receipt)
        else:
            result = resume_cleanup(args.directory)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"error": redact(str(exc))}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
