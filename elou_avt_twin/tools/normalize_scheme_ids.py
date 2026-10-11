"""Normalize legacy scheme IDs without deleting nodes, edges, or files.

Run from ``elou_avt_twin``::

    python tools/normalize_scheme_ids.py

The rewrite is deterministic and atomic. Existing edge endpoints remain bound
to the first occurrence of a legacy ID because automatically guessing a target
for an ambiguous edge could silently change the process topology.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scheme.model import migrate_scheme_data  # noqa: E402


def normalize_file(path: Path) -> tuple[int, int]:
    original = json.loads(path.read_text(encoding="utf-8-sig"))
    migrated = migrate_scheme_data(original)
    # File stem is the persistent scheme identity. Legacy copies often kept
    # id="default", which made a later save overwrite the real default file.
    migrated["id"] = path.stem
    node_count = len(migrated.get("nodes") or [])
    edge_count = len(migrated.get("edges") or [])
    payload = json.dumps(migrated, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if payload != path.read_text(encoding="utf-8-sig"):
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(payload, encoding="utf-8")
        temporary.replace(path)
    return node_count, edge_count


def main() -> int:
    for path in sorted((ROOT / "schemes").glob("*.json")):
        nodes, edges = normalize_file(path)
        print(f"{path.name}: {nodes} nodes, {edges} edges")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
