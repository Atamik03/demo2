"""Join the preheat-block line reference to the real K-1 feed path.

The two arrow callouts live on different AРМ tabs.  They are a visual
continuation of the same desalted-oil line, while the process graph must carry
the outlet of the preheat train into tray 16 of K-1.
"""
from __future__ import annotations

import json
from pathlib import Path


SCHEME = Path(__file__).resolve().parents[1] / "schemes" / "default.json"
OLD_DIRECT_FEED = "source_206-col_32-1790881471705"
OLD_REFERENCE_END = "hea_40-sink_201-1790715876947-after-1790715894226"
FEED_EDGE = "preheat2-k1-feed16"
REFERENCE_EDGE = "preheat2-k1-feed16-reference"
PUMP_BLOCK_K1_FEED = "preheat2-n20-gate-k1-tray22"
# Superseded direct feeds duplicate the outlet of each preheat train.  Keeping
# them makes the graph fork after the final exchanger, so the merge node can
# receive a zero-flow branch instead of the physical combined feed.
REDUNDANT_PREHEAT_FEEDS = {
    "hea_36-col_32-tee",
    "hea_40-col_32-tee",
    "hea_43-col_32-tee",
}


def main() -> None:
    data = json.loads(SCHEME.read_text(encoding="utf-8"))
    nodes = {node["id"]: node for node in data["nodes"]}

    # ``source_206`` and ``sink_201`` remain on their respective tabs as a
    # paired graphical callout.  The actual process stream leaves jun_40.
    for node_id, peer_id in (("source_206", "sink_201"), ("sink_201", "source_206")):
        params = nodes[node_id].setdefault("params", {})
        params["line_reference"] = True
        params["line_reference_peer_id"] = peer_id
        params["line_reference_key"] = "desalted-oil-to-k1-tray-16"
    nodes["sink_201"]["params"]["process_target"] = "К-1, тарелка №16"

    # ``source_205`` is the graphical continuation of the actual N-20 branch
    # below.  It must not add a separate fixed 100 kg/s source to K-1.
    if "source_205" in nodes:
        nodes["source_205"].setdefault("params", {})["reference_only"] = True
    # ``source_206`` is the other half of the tab-to-tab callout.  It is not
    # an independent 100 kg/s source: keeping it live in the process graph
    # made K-1 receive fictitious crude after all FRC-458/459/460 were shut.
    if "source_206" in nodes:
        nodes["source_206"].setdefault("params", {})["reference_only"] = True
    # E-15 sends gas to K-1.  It remains visible and live as a gas line, but
    # the ``gas`` port is not a liquid process-feed port of the column.
    if "source_207" in nodes:
        nodes["source_207"].setdefault("params", {}).pop("reference_only", None)

    # The N-20 manual branch is normally isolated. ``sink_225`` is its
    # graphical callout; the actual process edge is added below.
    if "gat_65" in nodes:
        gate_params = nodes["gat_65"].setdefault("params", {})
        gate_params["initial_open"] = 0.0
        gate_params["hydraulic_resistance_k"] = 10.0

    # N-20 header: the manual line to tray 22 is a bypass share, while the
    # normal crude feed reaches the three FRC branches through jun_82.
    if "jun_83" in nodes:
        nodes["jun_83"].setdefault("params", {})["outlet_flow_split"] = {
            "jun_82": 0.85,
            "gat_65": 0.15,
        }

    # Normal operating position of FRC-458/459/460.  The operator can still
    # move each valve; these defaults only prevent a fresh simulator run from
    # starting with every crude branch unintentionally isolated.
    for valve_id in ("val_44", "val_45", "val_46"):
        if valve_id in nodes:
            nodes[valve_id].setdefault("params", {})["initial_position"] = 0.75

    # LRCA-602 has enough authority to smooth normal variations and the loss
    # of one branch.  A loss of all three crude-feed regulators is a depletion
    # scenario: the bottoms line remains in its normal operating position and
    # the K-1 sump drains instead of being artificially held at 2.2 m.
    if "col_32" in nodes:
        column_params = nodes["col_32"].setdefault("params", {})
        column_params["loss_of_feed_valves"] = ["val_44", "val_45", "val_46"]
        column_params["loss_of_feed_behavior"] = "drain"
        column_params["loss_of_feed_min_closed"] = 2
        # At 5% manual opening, the remaining fully opened FRC-460 has enough
        # authority to compensate the bottoms withdrawal after two FRCs fail.
        column_params["bottoms_valve_reference_position"] = 0.32
        column_params["bottoms_valve_nominal_draw_kg_s"] = 382.5

    # FRC-458/459/460 are the documented process regulators.  An earlier
    # revision added a fictional fourth valve in front of tray 16; remove it
    # and every legacy edge attached to it.
    data["nodes"] = [node for node in data["nodes"] if node["id"] != "val_k1_feed16"]
    data["edges"] = [
        edge for edge in data["edges"]
        if edge["id"] not in {
            OLD_DIRECT_FEED, OLD_REFERENCE_END, FEED_EDGE, REFERENCE_EDGE, PUMP_BLOCK_K1_FEED,
        } | REDUNDANT_PREHEAT_FEEDS
        and edge.get("source") != "val_k1_feed16"
        and edge.get("target") != "val_k1_feed16"
    ]
    data["edges"].extend(({
        "id": FEED_EDGE,
        "kind": "oil",
        "source": "jun_40",
        "source_port": "out",
        "target": "col_32",
        "target_port": "feed2",
        "waypoints": [],
    }, {
        # Graphical continuation to the callout.  The runtime deliberately
        # ignores edges into a ``line_reference`` node, so it cannot split the
        # real feed headed to K-1.
        "id": REFERENCE_EDGE,
        "kind": "oil",
        "source": "jun_40",
        "source_port": "out",
        "target": "sink_201",
        "target_port": "in",
        "waypoints": [],
    }, {
        "id": PUMP_BLOCK_K1_FEED,
        "kind": "oil",
        "source": "gat_65",
        "source_port": "out",
        "target": "col_32",
        "target_port": "in",
        "waypoints": [],
    }))
    for edge in data["edges"]:
        if edge["id"] == "source_207-col_32-1790881820403":
            edge["target_port"] = "gas"
    SCHEME.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("Connected preheat outlet to K-1 tray 16 feed")


if __name__ == "__main__":
    main()
