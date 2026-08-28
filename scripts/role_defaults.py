"""Read the simple top-level YAML used by this project's role defaults."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any


def _scalar(value: str) -> Any:
    value = value.strip()
    if value[:1] in ("'", '"'):
        return ast.literal_eval(value)
    if value in ("true", "false"):
        return value == "true"
    try:
        return int(value)
    except ValueError:
        try:
            return float(value)
        except ValueError:
            return value


def read_defaults(path: Path) -> dict[str, Any]:
    lines = path.read_text().splitlines()
    result: dict[str, Any] = {}
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line or line.startswith((" ", "#", "---")) or ":" not in line:
            index += 1
            continue
        key, raw = line.split(":", 1)
        raw = raw.strip()
        if raw in (">", ">-"):
            index += 1
            parts = []
            while index < len(lines) and (not lines[index] or lines[index].startswith(" ")):
                if lines[index].strip():
                    parts.append(lines[index].strip())
                index += 1
            result[key] = " ".join(parts)
            continue
        if not raw:
            index += 1
            items = []
            while index < len(lines) and lines[index].startswith("  - "):
                items.append(_scalar(lines[index][4:]))
                index += 1
            result[key] = items
            continue
        result[key] = _scalar(raw)
        index += 1
    return result


def load_role_defaults(root: Path, roles: tuple[str, ...]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for role in roles:
        path = root / "roles" / role / "defaults" / "main.yml"
        if path.exists():
            values.update(read_defaults(path))
    return values
