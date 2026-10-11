"""Keep overview mnemoscheme scales and engineering units consistent."""

from __future__ import annotations

import json
from pathlib import Path


PATH = Path(__file__).resolve().parents[1] / "src" / "mnemo" / "mnemoData.json"


def visit(value):
    if isinstance(value, dict):
        # Fcrude is now supplied by sources.ts in t/h. The old overview tag
        # also multiplied it by 3.6, yielding a second conversion.
        if value.get("src") == "Fcrude" and value.get("sc") == 3.6:
            value.pop("sc")
        # All live column-pressure sources are gauge kgf/cm². The overview's
        # sole legacy label still said bar although it used the same source.
        if value.get("src") == "P204" and value.get("u") == " бар":
            value["u"] = " кгс/см²"
        for child in value.values():
            visit(child)
    elif isinstance(value, list):
        for child in value:
            visit(child)


def main() -> None:
    document = json.loads(PATH.read_text(encoding="utf-8"))
    visit(document)
    PATH.write_text(json.dumps(document, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
