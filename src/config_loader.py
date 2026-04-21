from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_config_file(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        return json.loads(text)
    if path.suffix.lower() in {".yaml", ".yml"}:
        try:
            import yaml
        except ImportError as exc:
            raise ImportError("PyYAML is required to read YAML config files.") from exc
        loaded = yaml.safe_load(text)
        return loaded or {}
    raise ValueError("config file must be .json, .yaml, or .yml.")

