from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Set


def load_relation_vocab(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def normalize_relation(raw: str, vocab: dict) -> str | None:
    """Map free-text / variant relation strings to the closed relation set."""
    if raw is None:
        return None
    key = raw.strip()
    allowed: Set[str] = set(vocab.get("allowed_relations", []))
    mapping: Dict[str, str] = vocab.get("normalize", {})
    if key in allowed:
        return mapping.get(key, key)
    lowered = key.lower()
    if lowered in mapping:
        return mapping[lowered]
    # camelCase / snake variants
    compact = lowered.replace(" ", "").replace("_", "")
    for a in allowed:
        if a.lower() == compact or a.lower().replace("_", "") == compact:
            return mapping.get(a, a)
    return None
