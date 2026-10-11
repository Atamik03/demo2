"""Write alarm limits for every placed field instrument in the default P&ID.

Numbers explicitly stated in the технологический регламент are marked with
their page.  Where the document specifies only the kind of signalling, the
four engineering thresholds are conservative simulator operating bounds; they
are marked as such in ``alarm_source`` instead of being presented as a
documented plant trip.
"""
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCHEME = ROOT / "schemes" / "default.json"
REGULATION = "3. Описание технологического процесса.pdf"
MODEL_SOURCE = "Эксплуатационные границы модели; техрегламент задаёт тип сигнализации без численных порогов"


def limits(low_low: float, low: float, high: float, high_high: float) -> dict[str, float]:
    return {"low_low": low_low, "low": low, "high": high, "high_high": high_high}


# Baselines give every instrument a complete LL/L/H/HH table.  They are
# replaced below whenever the regulation gives an operating maximum, a flow
# limit or a specific protective action.
BASELINES = {
    "temperature_c": limits(-20.0, 0.0, 400.0, 450.0),
    "top_temp_c": limits(0.0, 50.0, 140.0, 150.0),
    "t_out_c": limits(0.0, 50.0, 360.0, 365.0),
    "t_out2_c": limits(0.0, 50.0, 360.0, 365.0),
    "t_out3_c": limits(0.0, 50.0, 360.0, 365.0),
    "t_out4_c": limits(0.0, 50.0, 360.0, 365.0),
    "flow_t_h": limits(0.0, 1.0, 5000.0, 5500.0),
    "pressure_gauge_kgf_cm2": limits(-0.5, -0.1, 1.5, 2.0),
    "level_m": limits(0.5, 0.8, 5.0, 5.5),
    "level_pct": limits(15.0, 20.0, 85.0, 95.0),
    # Deviation is an absolute value, so only its high side is meaningful.
    "level_deviation_pct": limits(-1.0, -0.5, 3.0, 5.0),
}


# Position tags with a numeric value taken directly from the regulation.
DOCUMENTED: dict[str, tuple[dict[str, float], str]] = {
    # K-1: outlet P-3 no more than 340 °C, p. 9.
    # The 0.5 °C guard band prevents a stable controller at exactly 340 °C
    # from constantly raising an alarm at the documented operating maximum.
    **{tag: (limits(0.0, 50.0, 340.5, 345.0), f"{REGULATION}, стр. 9")
       for tag in ("TR 55-9", "TR 55-10", "TR 55-11")},
    # P-1/P-2 outlet no more than 365 °C, pp. 9–10.  The regulation does not
    # prescribe a 360 °C warning, so place the pre-alarm close to the actual
    # limit instead of alarming during a normal 360–363 °C regime.
    **{tag: (limits(0.0, 50.0, 364.0, 365.0), f"{REGULATION}, стр. 9–10")
       for tag in ("TR 55-1", "TR 55-2", "TR 55-3", "TR 55-4", "TR 55-6", "TRC 21")},
    # K-1 top no more than 150 °C, p. 7.
    "TRC 2": (limits(0.0, 50.0, 140.0, 150.0), f"{REGULATION}, стр. 7"),
    # Steam into K-1: no more than 1200 kg/h = 4.32 t/h, p. 7.
    "FR 803": (limits(0.0, 0.05, 4.0, 4.32), f"{REGULATION}, стр. 7"),
    # E-1 double level: the joint protective action is below 15 %, p. 7.
    "LRCSA 603": (limits(15.0, 20.0, 85.0, 95.0), f"{REGULATION}, стр. 7"),
    "LRSA 603B": (limits(15.0, 20.0, 85.0, 95.0), f"{REGULATION}, стр. 7"),
    "LDA 603V": (limits(-1.0, -0.5, 3.0, 5.0), f"{REGULATION}, стр. 7; модель: контроль рассогласования"),
    # K-2 circulating reflux: 20 m³/h at the model density of 850 kg/m³
    # equals 17 t/h.  The protective action additionally requires P<4 kgf/cm².
    "FRSA 472": (limits(0.0, 17.0, 250.0, 300.0), f"{REGULATION}, стр. 13"),
    "FRSA 419": (limits(0.0, 17.0, 250.0, 300.0), f"{REGULATION}, стр. 13"),
}


# Flow loops whose nominal flow is represented by the active P&ID.  The
# regulation confirms low-flow signalling but does not give a number; use a
# low alarm below the normal model flow and keep it explicitly labelled as a
# simulator operating bound.
FLOW_GROUPS: dict[tuple[str, ...], dict[str, float]] = {
    ("FQR 117/1", "FQR 117/2", "FYQR 117"): limits(0.0, 100.0, 2200.0, 2600.0),
    ("FRC 404", "FRC 405", "FRC 406", "FRC 458", "FRC 459", "FRC 460"): limits(0.0, 30.0, 300.0, 360.0),
    ("FR 490", "FR 491", "FR 492"): limits(0.0, 20.0, 180.0, 220.0),
    ("FRC 408", "FR 415"): limits(0.0, 5.0, 60.0, 75.0),
    ("FRCA 416", "FRCA 417", "FRCA 810"): limits(0.0, 10.0, 150.0, 180.0),
    ("FRCA 428", "FRCA 425", "FRCA 426", "FRCA 427"): limits(0.0, 15.0, 240.0, 290.0),
    ("FRCA 411", "FRCA 412", "FRCA 413", "FRCA 414"): limits(0.0, 10.0, 200.0, 240.0),
    ("FRC 421",): limits(0.0, 0.1, 4.0, 5.0),
    ("FR 420",): limits(0.0, 2.0, 80.0, 100.0),
}


TEMP_GROUPS: dict[tuple[str, ...], dict[str, float]] = {
    ("TR 41-1", "TR 5-К3Т"): limits(-20.0, 0.0, 180.0, 220.0),
    ("TR 41-2", "TR 41-3", "TR 41-4"): limits(-20.0, 0.0, 280.0, 320.0),
    ("TR 41-6", "TR 41-7", "TR 41-8"): limits(-20.0, 0.0, 280.0, 320.0),
    ("TR 43-2",): limits(-20.0, 0.0, 150.0, 170.0),
    ("TR 101-48", "TR 42-3", "TR 102-28", "TR 42-2", "TR 42-5"): limits(-20.0, 0.0, 300.0, 340.0),
}


def expand(groups: dict[tuple[str, ...], dict[str, float]]) -> dict[str, dict[str, float]]:
    return {tag: value for tags, value in groups.items() for tag in tags}


OVERRIDES = {**expand(FLOW_GROUPS), **expand(TEMP_GROUPS), **{tag: value[0] for tag, value in DOCUMENTED.items()}}


# Instruments placed later on the detailed K-1/K-2/K-3 sheets keep their
# graphical coordinates, but need an explicit process source to become live.
# Node ids are deliberately used here: tags may contain Cyrillic A/B suffixes
# and can be renamed in the editor without breaking the physical binding.
INSTRUMENT_BINDINGS = {
    # The three TRs observe the *flowing* outlet of their final exchanger.
    # Pipe telemetry intentionally becomes unavailable after FRC closure;
    # showing a retained exchanger-metal temperature as a live measurement
    # would be misleading.
    "fie_52": {"source_edge_id": "hea_40-sink_201-1790715876947-branch-1790715894226", "parameter": "temperature_c"},  # TR 41-7: train 1
    "fie_51": {"source_edge_id": "hea_40-sink_201-1790715876947", "parameter": "temperature_c"},  # TR 41-8: train 2
    "fie_53": {"source_edge_id": "hea_43-jun_40-1790715901405", "parameter": "temperature_c"},  # TR 41-6: train 3
    # K-2: top temperature, pressure and sump level.
    "fie_238": {"source_node_id": "col_64", "parameter": "top_temp_c"},
    "fie_239": {"source_node_id": "col_64", "parameter": "pressure_gauge_kgf_cm2"},
    "fie_240": {"source_node_id": "col_64", "parameter": "level_m"},
    "fie_241": {"source_node_id": "col_64", "parameter": "level_m"},
    "fie_242": {"source_node_id": "col_64", "parameter": "level_m"},
    "fie_248": {"source_node_id": "col_64", "parameter": "bottom_temp_c"},
    # E-2: main/duplicate level and phase-interface indication.
    "fie_244": {"source_node_id": "tan_3", "parameter": "level_m"},
    "fie_245": {"source_node_id": "tan_3", "parameter": "level_m"},
    "fie_246": {"source_node_id": "tan_3", "parameter": "level_m"},
    # K-1: pressure and the three level instruments.
    "fie_259": {"source_node_id": "col_32", "parameter": "pressure_gauge_kgf_cm2"},
    "fie_260": {"source_node_id": "col_32", "parameter": "level_m"},
    "fie_261": {"source_node_id": "col_32", "parameter": "level_m"},
    "fie_262": {"source_node_id": "col_32", "parameter": "level_m"},
    # K-3/1…3: the model has individual live K-2-to-stripper streams.
    "fie_249": {"source_edge_id": "col_64-col_63-1786309824755", "parameter": "temperature_c"},
    "fie_250": {"source_edge_id": "col_64-col_63-1786309844278", "parameter": "temperature_c"},
    "fie_251": {"source_edge_id": "col_64-col_63-1786309854875", "parameter": "temperature_c"},
}

INSTRUMENT_LIMITS = {
    "fie_238": limits(50.0, 80.0, 140.0, 148.0),
    # K-2 runs below atmospheric pressure in the model; its documented
    # 1.0/1.5 kgf/cm² signals remain on the high side.
    "fie_239": limits(-1.0, -0.8, 1.0, 1.5),
    **{node_id: limits(0.6, 1.0, 4.5, 5.0) for node_id in ("fie_240", "fie_241", "fie_242")},
    **{node_id: limits(0.9, 1.2, 5.1, 5.7) for node_id in ("fie_244", "fie_245", "fie_246")},
    "fie_248": limits(0.0, 80.0, 340.0, 350.0),
    "fie_259": limits(-0.5, -0.1, 4.5, 4.8),
    **{node_id: limits(0.6, 1.0, 4.0, 4.5) for node_id in ("fie_260", "fie_261", "fie_262")},
    **{node_id: limits(-20.0, 0.0, 400.0, 450.0) for node_id in ("fie_249", "fie_250", "fie_251")},
    # K-3 product paths are drawn but their downstream circuit is optional in
    # the current simulator.  A zero indication is therefore valid at start.
    **{node_id: limits(-0.1, -0.01, 500.0, 600.0) for node_id in ("fie_252", "fie_253", "fie_254")},
}


def main() -> None:
    data = json.loads(SCHEME.read_text(encoding="utf-8"))
    changed = 0
    missing: list[str] = []
    for node in data["nodes"]:
        if node.get("type") != "field_instrument":
            continue
        params = node.setdefault("params", {})
        binding = INSTRUMENT_BINDINGS.get(node.get("id"))
        if binding is not None:
            # A node source and a pipe source are alternatives.  Clear the
            # unused one so a stale editor reference cannot take precedence.
            params["source_edge_id"] = ""
            params["source_node_id"] = ""
            params.pop("source_parameter", None)
            params.update(binding)
            params["measurement_link"] = True
        tag = str(params.get("position_tag", node.get("name", "")))
        selected = INSTRUMENT_LIMITS.get(node.get("id"), OVERRIDES.get(
            tag, BASELINES.get(str(params.get("parameter")))
        ))
        if selected is None:
            missing.append(tag)
            continue
        params["alarm_limits"] = selected
        params["alarm_source"] = DOCUMENTED.get(tag, ({}, MODEL_SOURCE))[1]
        changed += 1
    # The three K-2 circulating-reflux control valves must carry at least
    # 20 m³/h in normal operation.  Their former Cv=0.01 restricted the
    # physical model to roughly 9 m³/h and therefore kept the documented
    # low-flow signal active permanently.
    for node in data["nodes"]:
        if node.get("id") in {"val_173", "val_174", "val_175"}:
            params = node.setdefault("params", {})
            params["cv"] = 0.025
            params["flow_coefficient_si"] = 0.025
        if node.get("id") == "col_64":
            # 5 kg/s is 21.2 m³/h at the model density: above the documented
            # 20 m³/h protective condition for a normal circulation loop.
            node.setdefault("params", {})["circulation_flow_kg_s"] = 5.0
        if node.get("id") == "col_63":
            # K-3 is drawn as three stripping sections.  Their liquid feeds
            # arrive through named ports, which were omitted from the generic
            # column feed list.  Include them so K-3 produces real bottoms
            # streams for N-14/N-35/N-16 and FQR 606A/607A/608A.
            params = node.setdefault("params", {})
            params["process_feed_ports"] = [
                "k31_liq", "k32_liq", "k33_liq"
            ]
            # The graphical K-3 node combines K-3/1…K-3/3.  Its product
            # temperature is therefore the heavy third-section stream, but
            # the generic K-3/1 340 °C limit was applied to that aggregate.
            # It produced a false column alarm after an unrelated FRC fault.
            # Temperature limits belong to the individual flow instruments;
            # retain only the meaningful common pressure and level limits.
            params["limits"] = {
                "pressure_low": 147099.75,
                "pressure_high": 441299.25,
                "pressure_high_high": 490332.5,
                "level_low": 0.8,
                "level_low_low": 0.5,
            }
        if node.get("id") == "hea_66":
            # П-1: the former high controller gain integrated fuel through the
            # 60 s furnace lag and drove all four coils past 365 °C on a normal
            # startup.  A 350 °C operating target stays below the documented
            # limit; the actual 365 °C PАЗ remains an independent protection.
            params = node.setdefault("params", {})
            params["auto_temperature_setpoint"] = 350.0
            params["auto_temperature_gain"] = 0.001
            params["auto_temperature_fuel_bias"] = 0.70
            params["initial_fuel_flow"] = 0.20
            params["auto_temperature_limit_c"] = 363.0
            params["paz_temperature_high_high"] = 365.0
            params["pp_flow_limit_kg_s"] = 1.0 / 3.0
        if node.get("id") == "hea_53":
            # П-3 heats the K-1 bottoms and one superheater circuit.  Keep
            # automatic control below the documented 340 °C limit and avoid
            # fuel-controller wind-up through the furnace time constant.
            params = node.setdefault("params", {})
            params["initial_fuel_flow"] = 0.20
            params["auto_temperature_setpoint"] = 328.0
            params["auto_temperature_gain"] = 0.001
            params["auto_temperature_fuel_bias"] = 0.20
            params["duty_split"] = "mass"
            params["max_outlet_temp"] = 613.15
            params["paz_temperature_high_high"] = 340.0
            params["pp_flow_limit_kg_s"] = 1.0 / 3.0
        if node.get("id") == "hea_54":
            # П-2 has four coils with different flow rates.  Distribute its
            # duty by mass so a low-flow coil cannot absorb a full quarter of
            # the burner duty and trip on temperature.
            params = node.setdefault("params", {})
            params["initial_fuel_flow"] = 0.10
            params["auto_temperature_setpoint"] = 350.0
            params["auto_temperature_gain"] = 0.001
            params["auto_temperature_fuel_bias"] = 0.73
            params["duty_split"] = "mass"
            params["auto_temperature_limit_c"] = 363.0
            params["paz_temperature_high_high"] = 365.0
            params["pp_flow_limit_kg_s"] = 1.0 / 3.0
        if node.get("id") == "val_171":
            # Total superheated-steam injection to K-2 is 2.4 t/h.
            node.setdefault("params", {})["max_flow_kg_s"] = 2.4 / 3.6
        if node.get("id") in {"source_56", "source_208"}:
            # Superheated steam is a small auxiliary flow (t/h scale), not a
            # 100–500 kg/s liquid feed.  The old placeholders immediately
            # drove FR 803 and the furnace superheater into false авария.
            node.setdefault("params", {})["flow_kg_s"] = 1.2 / 3.6
        if node.get("id") == "val_5":
            # The K-1 bottoms level valve must have enough authority to match
            # normal column production and then reduce the sump level when a
            # feed branch closes.
            params = node.setdefault("params", {})
            # Its former Cv capped the real bottoms draw at about 313 kg/s,
            # below the three-pump header capacity.  The level controller
            # therefore could not increase draw when K-1 feed was isolated.
            params["cv"] = 0.20
            params["flow_coefficient_si"] = 0.20
        if node.get("id") in {"pum_164", "pum_165", "pum_166"}:
            # Three parallel K-1 bottoms pumps.  With the current scheme the
            # normal K-1 bottoms rate is about 348 kg/s.  At 0.13 m³/s per
            # pump the header could withdraw only 331.5 kg/s, so the excess
            # slowly accumulated in the column even with LV-204 fully open.
            # Three parallel K-1 bottoms pumps.  Their joint capacity must
            # exceed normal production so LRCA-602 can stabilize the level by
            # throttling the bottoms draw after a feed regulator is lost.
            node.setdefault("params", {})["nominal_volumetric_flow_m3_s"] = 0.15
        if node.get("id") == "col_32":
            # LRCA-602 keeps the K-1 bottoms level in automatic.  When a
            # FRC-458/459/460 feed branch is lost, the level first falls;
            # then the controller closes the bottoms draw as far as its valve
            # authority permits and restores the level to its setpoint.
            node.setdefault("params", {})["level_control_auto"] = True
            # The K-1 bottom-level controller has a deliberately slower
            # feed-forward response than the process flow.  When the tray-16
            # feed is closed, the outlet therefore continues briefly at its
            # former rate and the operator sees a clear decrease in level.
            node.setdefault("params", {})["level_control_response_s"] = 60.0
            # Trainer-time scaling for a visibly responsive inventory.  This
            # affects only the transient level indication, not flow or the
            # normal material balance.
            node["params"]["level_dynamics_multiplier"] = 1.8
    if missing:
        raise RuntimeError(f"No alarm baseline for: {', '.join(missing)}")
    SCHEME.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Configured {changed} field instruments in {SCHEME.name}")


if __name__ == "__main__":
    main()
