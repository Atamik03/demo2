"""Organise only the K-4 and K-9/K-10 ARM tabs without touching process physics."""
from __future__ import annotations

import json
from pathlib import Path

SCHEME = Path(__file__).resolve().parents[1] / "schemes" / "default.json"
DOC = "3. Описание технологического процесса.pdf"
NO_LIMIT_ACTION = (
    "Техрегламент указывает вид сигнализации без численных уставок; "
    "прибор добавлен только для индикации и не изменяет модель."
)

# Existing process equipment, grouped exactly by the two requested ARM screens.
AREAS = {
    "stab": {
        "col_51", "val_122", "val_123", "sep_124", "hea_125", "source_126",
        "sink_127", "pum_128", "pum_131",
    },
    "secondary": {
        "val_89", "col_140", "col_141", "hea_142", "pum_143", "hea_144",
        "source_145", "sink_146", "sep_147", "pum_148", "val_149", "pum_150",
        "hea_151", "source_151w", "sink_151w", "sep_152", "pum_153", "val_154",
        "val_155", "hea_156", "hea_159", "pum_160", "source_161", "sink_162",
        "spl_8",
    },
}

# (id, area, tag, code, display_parameter, source_node, source_edge, x, y, page, description)
INSTRUMENTS = [
    # Stabilisation — K-4, E-3, reflux and reboil loop.
    ("fie_stab_trc44_4", "stab", "TRC 44-4", "TRC", "top_temp_c", "col_51", "", 1940, -405, "24", "Температура верха К-4; коррекция расхода орошения FRC 440."),
    ("fie_stab_tr44_12", "stab", "TR 44-12", "TR", "bottom_temp_c", "col_51", "", 1940, -355, "24", "Температура низа К-4."),
    ("fie_stab_lrca617", "stab", "LRCA 617", "LRCA", "level_m", "col_51", "", 1940, -225, "25", "Основной уровнемер низа К-4."),
    ("fie_stab_lr617b", "stab", "LR 617B", "LR", "level_m", "col_51", "", 1940, -175, "25", "Дублирующий уровнемер низа К-4."),
    ("fie_stab_frc444", "stab", "FRC 444", "FRC", "flow_t_h", "", "val_122-col_51-1786354698652", 1845, -72, "23", "Расход загрузки на 23-ю тарелку К-4."),
    ("fie_stab_frc440", "stab", "FRC 440", "FRC", "flow_t_h", "", "val_123-col_51-1786354714302", 1845, -190, "23", "Расход острого орошения К-4."),
    ("fie_stab_frca441", "stab", "FRCA 441", "FRCA", "flow_t_h", "", "pum_131-col_51-1786361538986", 2028, 280, "24", "Расход циркулирующего кубового продукта через П-3."),
    ("fie_stab_lrcsa616", "stab", "LRCSA 616", "LRCSA", "level_m", "sep_124", "", 2080, -410, "23", "Основной уровнемер ёмкости Е-3."),
    ("fie_stab_lrsa616b", "stab", "LRSA 616B", "LRSA", "level_m", "sep_124", "", 2160, -410, "23", "Дублирующий уровнемер ёмкости Е-3."),

    # Secondary fractionation — K-9, K-10, reflux receivers and reboilers.
    ("fie_sec_prca318", "secondary", "PRCA 318", "PRCA", "pressure_gauge_kgf_cm2", "col_140", "", 2370, -390, "26", "Давление в колонне К-9."),
    ("fie_sec_trc17_57", "secondary", "TRC 17-57", "TRC", "top_temp_c", "col_140", "", 2370, -340, "26", "Температура верха К-9; коррекция орошения FRC 457."),
    ("fie_sec_trc30", "secondary", "TRC 30", "TRC", "bottom_temp_c", "col_140", "", 2370, -240, "27", "Температура низа К-9."),
    ("fie_sec_lrca632", "secondary", "LRCA 632", "LRCA", "level_m", "col_140", "", 2370, -190, "27", "Основной уровнемер низа К-9."),
    ("fie_sec_lr632a", "secondary", "LR 632A", "LR", "level_m", "col_140", "", 2370, -140, "27", "Дублирующий уровнемер низа К-9."),
    ("fie_sec_frc457", "secondary", "FRC 457", "FRC", "flow_t_h", "", "val_154-col_140-1786366435837", 3055, -270, "26", "Расход острого орошения К-9."),
    ("fie_sec_frc453", "secondary", "FRC 453", "FRC", "flow_t_h", "", "col_140-spl_8-1786391658689", 2535, -210, "27", "Расход перетока из К-9 в К-10; коррекция по уровню К-9."),
    ("fie_sec_lrcsa633", "secondary", "LRCSA 633", "LRCSA", "level_m", "sep_152", "", 2635, -410, "26", "Основной уровнемер ёмкости Е-18."),
    ("fie_sec_lrsa633b", "secondary", "LRSA 633B", "LRSA", "level_m", "sep_152", "", 2715, -410, "26", "Дублирующий уровнемер ёмкости Е-18."),

    ("fie_sec_pr293", "secondary", "PR 293", "PR", "pressure_gauge_kgf_cm2", "col_141", "", 2970, -355, "29", "Давление в колонне К-10."),
    ("fie_sec_trc31", "secondary", "TRC 31", "TRC", "top_temp_c", "col_141", "", 2970, -305, "28", "Температура верха К-10; коррекция орошения FRC 454."),
    ("fie_sec_trc36", "secondary", "TRC 36", "TRC", "bottom_temp_c", "col_141", "", 2970, -200, "28", "Температура низа К-10."),
    ("fie_sec_lrca634", "secondary", "LRCA 634", "LRCA", "level_m", "col_141", "", 2970, -150, "29", "Основной уровнемер низа К-10."),
    ("fie_sec_lrsa634b", "secondary", "LRSA 634B", "LRSA", "level_m", "col_141", "", 2970, -100, "29", "Дублирующий уровнемер низа К-10."),
    ("fie_sec_frc454", "secondary", "FRC 454", "FRC", "flow_t_h", "", "val_149-col_141-1786371013339", 3060, -500, "28", "Расход острого орошения К-10."),
    ("fie_sec_frca449", "secondary", "FRCA 449", "FRCA", "flow_t_h", "", "col_141-pum_143-1786362981600", 2810, 80, "28", "Расход циркулирующего кубового продукта К-10 через П-4."),
    ("fie_sec_lrca635", "secondary", "LRCA 635", "LRCA", "level_m", "sep_147", "", 2650, -570, "28", "Основной уровнемер ёмкости Е-17."),
    ("fie_sec_lrsa635b", "secondary", "LRSA 635B", "LRSA", "level_m", "sep_147", "", 2730, -570, "28", "Дублирующий уровнемер ёмкости Е-17."),
]


def limits_for(parameter: str) -> dict[str, float]:
    # Explicitly broad display-only ranges keep newly drawn indicators from
    # creating artificial alarms where the regulation gives no numeric value.
    return {
        "top_temp_c": {"low_low": -100, "low": -50, "high": 500, "high_high": 550},
        "bottom_temp_c": {"low_low": -100, "low": -50, "high": 500, "high_high": 550},
        "flow_t_h": {"low_low": -1, "low": -0.1, "high": 100000, "high_high": 110000},
        "pressure_gauge_kgf_cm2": {"low_low": -2, "low": -1.5, "high": 100, "high_high": 110},
        "level_m": {"low_low": -2, "low": -1, "high": 100, "high_high": 110},
    }[parameter]


def main() -> None:
    scheme = json.loads(SCHEME.read_text(encoding="utf-8"))
    node_map = {node["id"]: node for node in scheme["nodes"]}
    edge_ids = {edge["id"] for edge in scheme["edges"]}

    for area, ids in AREAS.items():
        missing = ids - node_map.keys()
        if missing:
            raise RuntimeError(f"Missing {area} equipment: {sorted(missing)}")
        for node_id in ids:
            node_map[node_id].setdefault("params", {})["arm_area"] = area

    added = []
    for item in INSTRUMENTS:
        node_id, area, tag, code, parameter, source_node, source_edge, x, y, page, description = item
        if source_node and source_node not in node_map:
            raise RuntimeError(f"Missing instrument source node {source_node} for {tag}")
        if source_edge and source_edge not in edge_ids:
            raise RuntimeError(f"Missing instrument source edge {source_edge} for {tag}")
        params = {
            "alarm_limits": limits_for(parameter),
            "alarm_source": NO_LIMIT_ACTION,
            "arm_area": area,
            "instrument_code": code,
            "measurement_link": True,
            "parameter": parameter,
            "pipe_fraction": 0.5,
            "position_tag": tag,
            "source_context": description,
            "source_document": DOC,
            "source_edge_id": source_edge,
            "source_node_id": source_node,
            "source_pages": page,
        }
        node = node_map.get(node_id)
        if node is None:
            node = {"id": node_id, "name": tag, "params": params, "type": "field_instrument", "x": x, "y": y}
            scheme["nodes"].append(node)
            added.append(node_id)
        else:
            # Rerunning this tool changes only its own instrument nodes.
            node.update({"name": tag, "params": params, "type": "field_instrument", "x": x, "y": y})

    SCHEME.write_text(json.dumps(scheme, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Organised equipment: stab={len(AREAS['stab'])}, secondary={len(AREAS['secondary'])}")
    print(f"Added KIP: {len(added)}; total declared KIP: {len(INSTRUMENTS)}")


if __name__ == "__main__":
    main()
