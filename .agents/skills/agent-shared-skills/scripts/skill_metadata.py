"""Read skill YAML safely; never install dependencies or execute YAML objects."""
from pathlib import Path
import re


class MetadataError(ValueError):
    pass


def read_yaml(text: str) -> dict:
    try:
        import yaml
    except ImportError as exc:
        raise MetadataError("PyYAML is required. Install locally with: python -m pip install PyYAML") from exc
    try:
        value = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise MetadataError("invalid YAML (check syntax and scalar types)") from exc
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise MetadataError("YAML metadata must be a mapping")
    return value


def read_frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8-sig")
    match = re.match(r"\A---\s*\r?\n(.*?)\r?\n---\s*(?:\r?\n|$)", text, re.S)
    if not match:
        raise MetadataError("missing or unclosed YAML frontmatter")
    value = read_yaml(match.group(1))
    for field in ("name", "description"):
        if field in value and not isinstance(value[field], str):
            raise MetadataError(f"{field} must be a string")
    if "disable-model-invocation" in value and not isinstance(value["disable-model-invocation"], bool):
        raise MetadataError("disable-model-invocation must be a boolean")
    return value
