"""
model.py
========
Pydantic models for the P&ID scheme graph plus JSON persistence.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Any, Union

from pydantic import BaseModel, Field

logger = logging.getLogger("elou_avt.scheme")

SCHEMES_DIR = Path(__file__).resolve().parent.parent / "schemes"
DEFAULT_SCHEME_PATH = SCHEMES_DIR / "process_elou_avt.json"
LEGACY_DEFAULT_SCHEME_PATH = SCHEMES_DIR / "default.json"


class SchemeNode(BaseModel):
    """A single object on the scheme canvas."""

    id: str
    type: str = "pump"
    name: str = ""
    x: float = 0.0
    y: float = 0.0
    params: Dict[str, Any] = Field(default_factory=dict)


class SchemePoint(BaseModel):
    x: float = Field(..., allow_inf_nan=False)
    y: float = Field(..., allow_inf_nan=False)


class SchemeEdge(BaseModel):
    """A connection between two nodes, routed through explicit ports."""

    id: str
    source: str
    target: str
    source_port: str = "out"
    target_port: str = "in"
    kind: str = "process"
    waypoints: Optional[List[SchemePoint]] = None


SCHEMA_VERSION = "1.2"


class ProcessScheme(BaseModel):
    """The full scheme graph (configuration and topology only — no runtime state)."""

    id: str = "default"
    name: str = "ЭЛОУ-АВТ / default"
    schema_version: str = SCHEMA_VERSION
    nodes: List[SchemeNode] = Field(default_factory=list)
    edges: List[SchemeEdge] = Field(default_factory=list)

    def node(self, node_id: str) -> Optional[SchemeNode]:
        return next((n for n in self.nodes if n.id == node_id), None)

    def node_map(self) -> Dict[str, SchemeNode]:
        return {n.id: n for n in self.nodes}

    def edges_from(self, node_id: str) -> List[SchemeEdge]:
        return [e for e in self.edges if e.source == node_id]

    def edges_to(self, node_id: str) -> List[SchemeEdge]:
        return [e for e in self.edges if e.target == node_id]

    def add_node(self, node: SchemeNode) -> None:
        if self.node(node.id) is not None:
            raise ValueError(f"Node '{node.id}' already exists")
        self.nodes.append(node)

    def remove_node(self, node_id: str) -> None:
        self.nodes = [n for n in self.nodes if n.id != node_id]
        self.edges = [e for e in self.edges if e.source != node_id and e.target != node_id]

    def add_edge(self, edge: SchemeEdge) -> None:
        self.edges.append(edge)


def _unique_id(base: str, used: set[str], occurrence: int) -> str:
    """Return a deterministic ID without discarding a duplicated object."""
    suffix = max(2, occurrence)
    candidate = f"{base}__dup{suffix}"
    while candidate in used:
        suffix += 1
        candidate = f"{base}__dup{suffix}"
    return candidate


def normalize_duplicate_ids(data: Dict[str, Any]) -> Dict[str, Any]:
    """Make node and edge IDs unique while preserving every graph object.

    Legacy editor versions could write several objects with the same ID.
    React Flow and the simulation engine both use IDs as dictionary keys, so
    the later objects became inaccessible.  The migration keeps the first ID
    (and therefore all existing edge references) and deterministically renames
    subsequent occurrences to ``<id>__dupN``.  We deliberately do not guess
    which ambiguous legacy edge belonged to which duplicate: guessing could
    silently rewire a process.  The preserved duplicate stays available for an
    instructor to reconnect explicitly in the scheme editor.
    """
    result = dict(data)
    nodes = [dict(node) for node in (data.get("nodes") or [])]
    edges = [dict(edge) for edge in (data.get("edges") or [])]

    node_counts: defaultdict[str, int] = defaultdict(int)
    used_node_ids = {str(node.get("id", "")) for node in nodes}
    renamed_nodes: list[tuple[str, str]] = []
    for node in nodes:
        original = str(node.get("id", "")).strip()
        node_counts[original] += 1
        if node_counts[original] == 1:
            node["id"] = original
            continue
        replacement = _unique_id(original or "node", used_node_ids, node_counts[original])
        used_node_ids.add(replacement)
        node["id"] = replacement
        renamed_nodes.append((original, replacement))

    edge_counts: defaultdict[str, int] = defaultdict(int)
    used_edge_ids = {str(edge.get("id", "")) for edge in edges}
    renamed_edges: list[tuple[str, str]] = []
    for edge in edges:
        original = str(edge.get("id", "")).strip()
        edge_counts[original] += 1
        if edge_counts[original] == 1:
            edge["id"] = original
            continue
        replacement = _unique_id(original or "edge", used_edge_ids, edge_counts[original])
        used_edge_ids.add(replacement)
        edge["id"] = replacement
        renamed_edges.append((original, replacement))

    if renamed_nodes:
        logger.warning(
            "Preserved %d node(s) with duplicate IDs by assigning deterministic suffixes: %s",
            len(renamed_nodes),
            ", ".join(f"{old!r}->{new!r}" for old, new in renamed_nodes),
        )
    if renamed_edges:
        logger.warning(
            "Preserved %d edge(s) with duplicate IDs by assigning deterministic suffixes: %s",
            len(renamed_edges),
            ", ".join(f"{old!r}->{new!r}" for old, new in renamed_edges),
        )

    result["nodes"] = nodes
    result["edges"] = edges
    return result


def migrate_scheme_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """Migrate legacy scheme JSON to the current schema (ТЗ section 6).

    Upgrades ambiguous legacy parameter names to their canonical SI names:
      pump   nominal_flow     -> nominal_volumetric_flow_m3_s
      pump   delta_p          -> nominal_head_pa
      valve  cv               -> flow_coefficient_si
    Legacy keys are preserved alongside (harmless) so old consumers keep
    working, but the canonical names take precedence in the physics core.
    """
    version = data.get("schema_version", "1.0")
    data = normalize_duplicate_ids(data)
    nodes = data.get("nodes", [])
    new_nodes = []
    for node in nodes:
        node = dict(node)
        params = dict(node.get("params") or {})
        ntype = node.get("type", "")
        if ntype == "pump":
            if "nominal_flow" in params and "nominal_volumetric_flow_m3_s" not in params:
                params["nominal_volumetric_flow_m3_s"] = params["nominal_flow"]
            if "delta_p" in params and "nominal_head_pa" not in params:
                params["nominal_head_pa"] = params["delta_p"]
        elif ntype == "valve":
            if "cv" in params and "flow_coefficient_si" not in params:
                params["flow_coefficient_si"] = params["cv"]
        node["params"] = params
        new_nodes.append(node)
    data["nodes"] = new_nodes
    if version != SCHEMA_VERSION:
        data["schema_version"] = SCHEMA_VERSION
    return data


def load_scheme(path: Optional[Union[Path, str]] = None) -> ProcessScheme:
    """Load a scheme from a JSON file (falls back to the default scheme).

    Applies ``migrate_scheme_data`` so legacy schemes load cleanly.
    """
    path = Path(path) if path else DEFAULT_SCHEME_PATH
    if not path.exists() and path == DEFAULT_SCHEME_PATH and LEGACY_DEFAULT_SCHEME_PATH.exists():
        logger.warning("Canonical scheme %s not found; loading fallback %s.", path, LEGACY_DEFAULT_SCHEME_PATH)
        path = LEGACY_DEFAULT_SCHEME_PATH
    if not path.exists():
        logger.warning("Scheme file %s not found; using empty scheme.", path)
        return ProcessScheme()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        data = migrate_scheme_data(data)
        return ProcessScheme.model_validate(data)
    except Exception:
        logger.exception("Failed to load scheme from %s; using empty scheme.", path)
        return ProcessScheme()


def save_scheme(scheme: ProcessScheme, path: Optional[Union[Path, str]] = None) -> Path:
    """Persist a scheme to a JSON file (atomic, deterministic, UTF-8).

    The file is written to a temporary sibling and atomically replaced, so a
    crash mid-save never leaves a corrupt scheme behind.
    """
    path = Path(path) if path else DEFAULT_SCHEME_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        scheme.model_dump(mode="json"),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(payload)
        f.write("\n")
    tmp.replace(path)
    logger.info("Scheme saved to %s (%d nodes, %d edges).", path, len(scheme.nodes), len(scheme.edges))
    return path
