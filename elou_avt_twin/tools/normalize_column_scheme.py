"""Apply only verified operating corrections to the saved P&ID scheme."""

from __future__ import annotations

import json
from pathlib import Path


SCHEME_PATH = Path(__file__).resolve().parents[1] / "schemes" / "default.json"


def main() -> None:
    scheme = json.loads(SCHEME_PATH.read_text(encoding="utf-8"))
    nodes = {node["id"]: node for node in scheme["nodes"]}

    # K-1 currently produces about 339 kg/s at the documented operating
    # condition.  N-2A, N-2B and N-3A together had only 255 kg/s of nominal
    # capacity, so an open level-control valve could not hold the cube level.
    # Each branch is rated for 0.16 m³/s, giving 408 kg/s total at 850 kg/m³.
    for node_id in ("pum_164", "pum_165", "pum_166"):
        nodes[node_id]["params"]["nominal_volumetric_flow_m3_s"] = 0.16

    # N-32 and N-32A are parallel bottom pumps of K-2.  The common FRC 449
    # valve must pass their normal combined draw; its old 0.007 coefficient
    # capped the column at 63.9 kg/s while it produced about 87 kg/s.
    nodes["val_73"]["params"]["cv"] = 0.012
    nodes["val_73"]["params"]["flow_coefficient_si"] = 0.012
    # Their combined 0.111 m³/s design rate was still below the converged
    # K-2 bottoms production.  Set each duty pump to 0.06 m³/s so the pair
    # can hold the regulated 97.7 kg/s mode without defeating the valve.
    for node_id in ("pum_68", "pum_71"):
        nodes[node_id]["params"]["nominal_volumetric_flow_m3_s"] = 0.06

    # The regulation identifies TRC 2 as the top-temperature controller of
    # K-1.  Its earlier link measured the cold reflux pipe instead.
    trc2 = nodes.get("fie_60")
    if trc2 is not None:
        params = trc2["params"]
        params["source_edge_id"] = ""
        params["source_node_id"] = "col_32"
        params["parameter"] = "top_temp_c"

    # Furnace metallurgy and operating limits from the process regulation.
    nodes["hea_66"]["params"]["max_outlet_temp"] = 673.15  # P-1: 400 °C
    nodes["hea_54"]["params"]["max_outlet_temp"] = 638.15  # P-2: 365 °C
    nodes["hea_53"]["params"]["max_outlet_temp"] = 613.15  # P-3: 340 °C
    # Fuel-gas temperature control and the independent PАЗ trip thresholds.
    # The lower start values avoid an artificial trip while the controller
    # reaches its operating point after a cold start.
    for node_id, sp, fuel, paz in (
        ("hea_66", 352.0, 0.60, 400.0),  # P-1, TRC 9/11
        ("hea_54", 356.0, 0.75, 365.0),  # P-2, TRC 18/21
        ("hea_53", 328.0, 0.22, 340.0),  # P-3, TRC 3
    ):
        params = nodes[node_id]["params"]
        params["initial_fuel_flow"] = fuel
        params["auto_temperature_setpoint"] = sp
        params["auto_temperature_gain"] = 0.0025
        params["max_fuel_flow"] = 1.5
        params["paz_temperature_high_high"] = paz
    nodes["hea_66"]["params"]["duty_split"] = "mass"
    # Main P-1 tag: expose the actual process outlet temperature next to the
    # furnace; individual outlet passes remain available as TR 55-1…TR 55-4.
    nodes["hea_66"]["disp"] = ["outlet_temp_c"]
    # FR 803: max 1200 kg/h of superheated steam into K-1.  FRC 421: 2.4 t/h
    # into K-2, supplied equally by P-1 and P-2 superheaters.
    nodes["hea_53"]["params"]["pp_flow_limit_kg_s"] = 1200.0 / 3600.0
    nodes["hea_54"]["params"]["pp_flow_limit_kg_s"] = 1200.0 / 3600.0
    nodes["hea_66"]["params"]["pp_flow_limit_kg_s"] = 1200.0 / 3600.0
    nodes["val_171"]["params"]["max_flow_kg_s"] = 2400.0 / 3600.0

    # TR 55-1…4 register the four P-1 outlet streams.  They were placed on
    # the mnemonic without a measurement source, so their display was blank.
    p1_outlets = {
        "fie_220": "t_out_c",   # stream 1
        "fie_221": "t_out2_c",  # stream 2
        "fie_222": "t_out3_c",  # stream 3
        "fie_223": "t_out4_c",  # stream 4
    }
    for node_id, parameter in p1_outlets.items():
        instrument = nodes.get(node_id)
        if instrument is not None:
            params = instrument["params"]
            params["source_edge_id"] = ""
            params["source_node_id"] = "hea_66"
            params["parameter"] = parameter

    # The process model uses kg/s internally.  The technological regulation
    # and its controller catalogue show all measured process flows in t/h;
    # convert only the field-instrument engineering value, never the model.
    # The one installed pressure gauge is likewise an excess-pressure reading
    # in kgf/cm², matching the documented pressure controllers and alarms.
    for node in scheme["nodes"]:
        if node.get("type") != "field_instrument":
            continue
        params = node["params"]
        if params.get("parameter") == "flow_kg_s":
            params["parameter"] = "flow_t_h"
        elif params.get("parameter") == "pressure_bar":
            params["parameter"] = "pressure_gauge_kgf_cm2"

    SCHEME_PATH.write_text(
        json.dumps(scheme, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
