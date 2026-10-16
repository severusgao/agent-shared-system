#!/usr/bin/env python3
"""Generate the dynamic sections of the shared-source shared-system README."""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from pathlib import Path


BEGIN = "<!-- BEGIN GENERATED: {name} -->"
END = "<!-- END GENERATED: {name} -->"
CONTROL_SKILLS = {
    "agent-shared-skills",
    "agent-shared-memories",
    "agent-shared-mcps",
    "agent-shared-evolution",
    "obsidian-vault",
}


def discover_root() -> Path:
    return Path(__file__).resolve().parents[2]


def frontmatter_value(text: str, key: str) -> str:
    if not text.startswith("---"):
        return ""
    match = re.search(r"^---\s*$\n(.*?)^---\s*$", text, re.MULTILINE | re.DOTALL)
    if not match:
        return ""
    for line in match.group(1).splitlines():
        if not line.startswith(f"{key}:"):
            continue
        value = line.split(":", 1)[1].strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        return value
    return ""


def clean_cell(value: str) -> str:
    value = re.sub(r"[\r\n]+", " ", value).strip()
    return value.replace("|", "\\|")


def discover_skills(root: Path) -> list[tuple[str, str, str]]:
    result: list[tuple[str, str, str]] = []
    skills_root = root / ".agents" / "skills"
    if not skills_root.is_dir():
        return result
    for skill_dir in sorted(skills_root.iterdir(), key=lambda item: item.name.lower()):
        skill_file = skill_dir / "SKILL.md"
        if not skill_dir.is_dir() or not skill_file.is_file():
            continue
        try:
            text = skill_file.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        name = frontmatter_value(text, "name") or skill_dir.name
        description = frontmatter_value(text, "description") or "未提供 description"
        category = "控制技能" if name in CONTROL_SKILLS else "共享技能"
        result.append((name, description, category))
    return result


def discover_mcps(root: Path) -> list[tuple[str, str, str]]:
    result: list[tuple[str, str, str]] = []
    catalog = root / ".agents" / "mcp" / "catalog"
    if not catalog.is_dir():
        return result
    for path in sorted(catalog.glob("*.json"), key=lambda item: item.name.lower()):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        identifier = str(data.get("id") or path.stem)
        label = str(data.get("label") or data.get("server_name") or identifier)
        description = str(data.get("description") or "未提供 description")
        result.append((identifier, label, description))
    return result


def discover_scripts(root: Path) -> list[str]:
    scripts_root = root / ".agents" / "scripts"
    if not scripts_root.is_dir():
        return []
    return sorted(
        path.name
        for path in scripts_root.iterdir()
        if path.is_file() and not path.name.startswith(".")
    )


def render_skills(root: Path) -> str:
    lines = [
        BEGIN.format(name="shared-skills"),
        "### 当前共享 Skills",
        "",
        "以下内容由 `.agents/skills/*/SKILL.md` 扫描生成，不是固定清单。",
        "",
        "| Skill | 类型 | 用途 |",
        "|---|---|---|",
    ]
    for name, description, category in discover_skills(root):
        lines.append(f"| `{clean_cell(name)}` | {category} | {clean_cell(description)} |")
    if len(lines) == 7:
        lines.append("| （暂无有效 Skill） | - | 未发现包含有效 `SKILL.md` 的目录 |")
    lines.extend(["", END.format(name="shared-skills")])
    return "\n".join(lines)


def render_mcps(root: Path) -> str:
    lines = [
        BEGIN.format(name="shared-mcps"),
        "### 当前共享 MCP",
        "",
        "以下内容由 `.agents/mcp/catalog/*.json` 扫描生成；它不是 Agent 的实时 MCP 配置。",
        "",
        "| ID | 名称 | 用途 |",
        "|---|---|---|",
    ]
    for identifier, label, description in discover_mcps(root):
        lines.append(f"| `{clean_cell(identifier)}` | {clean_cell(label)} | {clean_cell(description)} |")
    if len(lines) == 7:
        lines.append("| （暂无 MCP） | - | 未发现 registry catalog 条目 |")
    lines.extend(["", END.format(name="shared-mcps")])
    return "\n".join(lines)


def render_scripts(root: Path) -> str:
    lines = [
        BEGIN.format(name="scripts"),
        "### 当前共享系统脚本",
        "",
        "脚本真实副本位于 `.agents/scripts/`；首次接入和写入操作应先预览。",
        "",
    ]
    scripts = discover_scripts(root)
    lines.extend((f"- `{name}`" for name in scripts))
    if not scripts:
        lines.append("- （暂无脚本）")
    lines.extend(["", END.format(name="scripts")])
    return "\n".join(lines)


def replace_generated_block(document: str, name: str, replacement: str) -> str:
    pattern = re.compile(
        re.escape(BEGIN.format(name=name)) + r".*?" + re.escape(END.format(name=name)),
        re.DOTALL,
    )
    if not pattern.search(document):
        raise ValueError(f"README missing generated block: {name}")
    return pattern.sub(lambda _match: replacement, document, count=1)


def render_document(root: Path, document: str) -> str:
    result = document
    for name, renderer in (
        ("shared-skills", render_skills),
        ("shared-mcps", render_mcps),
        ("scripts", render_scripts),
    ):
        result = replace_generated_block(result, name, renderer(root))
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=discover_root(), help="shared-system parent directory")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="check whether README is current")
    mode.add_argument("--preview", action="store_true", help="show generated README diff")
    mode.add_argument("--write", action="store_true", help="write generated sections")
    args = parser.parse_args(argv)

    root = args.root.expanduser().resolve()
    readme = root / ".agents" / "README.md"
    if not readme.is_file():
        print(f"README not found: {readme}", file=sys.stderr)
        return 2
    try:
        current = readme.read_text(encoding="utf-8")
        updated = render_document(root, current)
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"README generation failed: {exc}", file=sys.stderr)
        return 2

    if args.check:
        if current == updated:
            print("Shared-system README is up to date.")
            return 0
        print("Shared-system README is out of date.")
        return 1
    if args.preview:
        if current == updated:
            print("No README changes.")
            return 0
        print("".join(difflib.unified_diff(
            current.splitlines(keepends=True),
            updated.splitlines(keepends=True),
            fromfile="current",
            tofile="generated",
        )))
        return 0
    if current == updated:
        print("No README changes.")
        return 0
    readme.write_text(updated, encoding="utf-8")
    print(f"Updated {readme}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
