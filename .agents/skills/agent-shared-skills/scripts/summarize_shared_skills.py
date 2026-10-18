#!/usr/bin/env python3
"""Summarize shared-source shared skills from their SKILL.md metadata."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.dont_write_bytecode = True

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from resolve_skills_root import resolve_skills_root  # noqa: E402


from skill_metadata import MetadataError, read_frontmatter


def parse_skill_md(path: Path) -> Dict[str, Optional[str]]:
    metadata = read_frontmatter(path)
    return {key: metadata.get(key) for key in ("name", "description")}


def nested_entries(skill_dir: Path) -> list[dict]:
    # Do not traverse links into other stores or generated/vendor directories.
    import os
    entries = []
    for directory, dirs, files in os.walk(skill_dir, followlinks=False):
        dirs[:] = [d for d in dirs if d not in {".git", "__pycache__", "node_modules", ".venv"}
                   and not (Path(directory) / d).is_symlink()]
        path = Path(directory) / "SKILL.md"
        if Path(directory) != skill_dir and "SKILL.md" in files:
            item = {"path": path.relative_to(skill_dir).as_posix(), "parent_skill": skill_dir.name}
            try:
                item.update(parse_skill_md(path))
            except (MetadataError, OSError) as exc:
                item["metadata_error"] = str(exc)
            entries.append(item)
    return sorted(entries, key=lambda item: item["path"])


def summarize(root: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for skill_dir in sorted(child for child in root.iterdir() if child.is_dir()):
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.is_file():
            continue
        try:
            meta = parse_skill_md(skill_md)
        except (MetadataError, OSError) as exc:
            meta = {"name": None, "description": None, "metadata_error": str(exc)}
        rows.append(
            {
                "folder": skill_dir.name,
                "metadata_error": meta.get("metadata_error"),
                "nested_skills": nested_entries(skill_dir),
                "name": meta.get("name"),
                "description": meta.get("description"),
                "has_references": (skill_dir / "references").is_dir(),
                "has_scripts": (skill_dir / "scripts").is_dir(),
                "has_openai_yaml": (skill_dir / "agents" / "openai.yaml").is_file(),
            }
        )
    return rows


def render_markdown(rows: List[Dict[str, Any]], root: Path) -> str:
    lines = [
        "# Shared Skills Summary",
        "",
        f"Root: `{root.resolve()}`",
        "",
        "| Folder | Name | References | Scripts | OpenAI metadata | Description |",
        "|---|---|---:|---:|---:|---|",
    ]
    for row in rows:
        description = (row.get("description") or "").replace("|", "\\|")
        lines.append(
            "| `{folder}` | `{name}` | {refs} | {scripts} | {openai} | {desc} |".format(
                folder=row.get("folder"),
                name=row.get("name"),
                refs="yes" if row.get("has_references") else "no",
                scripts="yes" if row.get("has_scripts") else "no",
                openai="yes" if row.get("has_openai_yaml") else "no",
                desc=description,
            )
        )
    for row in rows:
        if row.get("metadata_error"):
            lines.append(f"- Metadata error in {row['folder']}: {row['metadata_error']}")
        for nested in row.get("nested_skills", []):
            lines.append(f"- Nested entry: `{row['folder']}/{nested['path']}` (deployment unit: `{row['folder']}`)")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=None, help="Shared skills root. Defaults to discovery.")
    parser.add_argument("--format", choices=["json", "markdown"], default="markdown")
    args = parser.parse_args()

    if args.root:
        root = Path(args.root).expanduser()
    else:
        resolved = resolve_skills_root()
        if not resolved.get("ok"):
            print(json.dumps(resolved, ensure_ascii=False, indent=2), file=sys.stderr)
            return 1
        root = Path(str(resolved["skills_root"]))

    rows = summarize(root)
    if args.format == "json":
        print(json.dumps({"root": str(root.resolve()), "skills": rows}, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(rows, root))
    return 1 if any(row.get("metadata_error") or any(n.get("metadata_error") for n in row.get("nested_skills", [])) for row in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
