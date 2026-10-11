"""Restore the documented field instruments that were lost from the HMI draft.

The script is idempotent: it preserves any existing instrument and adds only
the missing documented tags to ``schemes/default.json``.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCHEME_PATH = ROOT / "schemes" / "default.json"
DOCUMENT_INSTRUMENTS = ROOT.parent / "elou_avt_web" / "src" / "arm" / "documentInstruments.json"


K1_TAGS = ("TRC 2", "TRC 4", "PRSA 204", "LRCA 602")


def parameter_for(tag: str) -> str:
    if tag == "TRC 2":
        return "top_temp_c"
    if tag == "TRC 4":
        return "bottom_temp_c"
    code = tag.split()[0].replace("Р", "P").replace("Т", "T")
    return {
        "F": "flow_kg_s", "T": "temperature_c", "P": "pressure_bar",
        "L": "level_m", "Q": "concentration_pct",
    }.get(code[:1], "")


def slug(tag: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", tag.lower().replace("а", "a").replace("в", "b").replace("к", "k")).strip("-")
    return f"{base}-{hashlib.sha1(tag.encode('utf-8')).hexdigest()[:8]}"


def positions(origin: tuple[float, float], count: int) -> list[tuple[float, float]]:
    x, y = origin
    return [(x + (index % 4) * 128, y + (index // 4) * 62) for index in range(count)]


def main() -> None:
    scheme = json.loads(SCHEME_PATH.read_text(encoding="utf-8"))
    reference = {item["tag"]: item for item in json.loads(DOCUMENT_INSTRUMENTS.read_text(encoding="utf-8"))}
    # Remove the recovery batch and the former K-1 flow instruments. The
    # operator requested just top/bottom temperature, pressure and level.
    scheme["nodes"] = [
        node for node in scheme["nodes"]
        if not str(node.get("id", "")).startswith("fie_restore_")
        and not (
            node.get("type") == "field_instrument"
            and (
                node.get("params", {}).get("source_node_id") == "col_32"
                or "col_32" in str(node.get("params", {}).get("source_edge_id", ""))
            )
        )
    ]
    # E-1 has two independent level meters and a mismatch alarm.  Its actual
    # measurement is in metres; the alarm value is supplied by the API.
    for node in scheme["nodes"]:
        if node.get("type") != "field_instrument":
            continue
        tag = str(node.get("params", {}).get("position_tag") or node.get("name", ""))
        if tag in {"LRCSA 603", "LRSA 603B"}:
            node["params"]["parameter"] = "level_m"
        elif tag == "LDA 603V":
            node["params"]["parameter"] = "level_deviation_pct"
    existing = {
        str(node.get("params", {}).get("position_tag") or node.get("name", ""))
        for node in scheme["nodes"] if node.get("type") == "field_instrument"
    }

    groups = (
        ("col_32", K1_TAGS, (430.0, -185.0)),
    )
    added: list[str] = []
    for source_node_id, tags, origin in groups:
        for tag, (x, y) in zip(tags, positions(origin, len(tags))):
            if tag in existing:
                continue
            document = reference.get(tag, {})
            code = tag.split()[0]
            scheme["nodes"].append({
                "id": f"fie_restore_{slug(tag)}",
                "type": "field_instrument",
                "name": tag,
                "x": x,
                "y": y,
                "params": {
                    "arm_area": "atm",
                    "instrument_code": code,
                    "position_tag": tag,
                    "parameter": parameter_for(tag),
                    "measurement_link": True,
                    "source_node_id": source_node_id,
                    "source_edge_id": "",
                    "source_document": "3. Описание технологического процесса.pdf",
                    "source_pages": document.get("pages", ""),
                    "source_context": document.get("context", ""),
                },
            })
            added.append(tag)

    SCHEME_PATH.write_text(json.dumps(scheme, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Added {len(added)} instrument(s): {', '.join(added)}")


if __name__ == "__main__":
    main()
