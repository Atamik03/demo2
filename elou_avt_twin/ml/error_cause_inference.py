"""Inference for the five error causes using the model's exact 34 features."""

from __future__ import annotations

import json
import os
import time
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List, Sequence

import numpy as np

FEATURE_SCHEMA_VERSION = "error-cause-34-v1"
FEATURE_NAMES = (
    "session_duration_sim_s", "session_duration_wall_s", "time_to_first_action_s",
    "action_max_idle_s", "action_count", "action_unique_equipment_count",
    "action_correct_ratio", "action_extra_count", "action_repeated_count",
    "expected_action_count", "expected_completed_count", "expected_completion_ratio",
    "error_count", "error_unique_type_count", "error_first_at_s", "error_last_at_s",
    "alarm_count", "alarm_active_at_end_count", "alarm_mean_relevant_action_delay_s",
    "alarm_max_relevant_action_delay_s", "action_mean_interval_s", "action_max_interval_s",
    "error_mean_interval_s", "error_max_interval_s", "equipment_state_observed_action_ratio",
    "equipment_state_changed_action_ratio", "error_wrong_sequence_count",
    "error_delayed_action_count", "error_wrong_equipment_count",
    "error_wrong_action_type_count", "error_wrong_parameter_value_count",
    "error_missed_action_count", "alarm_severity_high_count",
    "alarm_severity_critical_count",
)
assert len(FEATURE_NAMES) == 34

CAUSE_LABELS = {
    "target_1": "Потеря ориентации в установке",
    "target_2": "Долгое время реакции",
    "target_3": "Непонимание физических процессов",
    "target_4": "Незнание алгоритма или регламента",
    "target_5": "Случайная ошибка",
}


def _intervals(times: Sequence[float]) -> tuple[float, float]:
    gaps = [b - a for a, b in zip(times, times[1:]) if b >= a]
    return (mean(gaps) if gaps else 0.0, max(gaps, default=0.0))


def _action_changed(action: Dict[str, Any]) -> bool:
    old, new = action.get("old_value"), action.get("new_value")
    if old is None or new is None:
        return False
    try:
        return float(old) != float(new)
    except (TypeError, ValueError):
        return old != new


def build_features(store: Any, session_id: str) -> Dict[str, float]:
    """Build the stable numeric row expected by metadata.json, in exact order."""
    session = store.get_session(session_id)
    if session is None:
        raise KeyError(session_id)
    actions = store.get_actions(session_id)
    alarms = store.get_alarms(session_id)
    errors = [e for e in store.get_errors(session_id)
              if e.get("rule_error_type") != "PRACTICE_FEEDBACK"]
    delayed_expected = [str(e.get("expected_action") or "").strip() for e in errors
                        if e.get("rule_error_type") == "DELAYED_ACTION"]
    errors = [e for e in errors if not (
        e.get("rule_error_type") == "MISSED_ACTION"
        and any(str(e.get("expected_action") or "").strip().startswith(delayed)
                for delayed in delayed_expected if delayed)
    )]
    expected = store.get_expected_actions(str(session.get("scenario_id", "")))
    sim_start = float(session.get("sim_start") or 0.0)
    sim_end = float(session.get("sim_end") or sim_start)
    wall_start = float(session.get("wall_start") or 0.0)
    wall_end = float(session.get("wall_end") or time.time())
    action_times = [float(a["sim_time"]) for a in actions if a.get("sim_time") is not None]
    error_times = [float(e["sim_time"]) for e in errors if e.get("sim_time") is not None]
    action_mean, action_max = _intervals(action_times)
    error_mean, error_max = _intervals(error_times)
    error_counts = Counter(str(e.get("rule_error_type") or "") for e in errors)
    alarm_severity = Counter(str(a.get("severity") or "").upper() for a in alarms)
    expected_pairs = [(e.get("equipment_id"), e.get("action_type")) for e in expected]
    expected_set = set(expected_pairs)
    actual_pairs = [(a.get("equipment_id"), a.get("action_type")) for a in actions]
    completed = sum(1 for pair in expected_pairs if pair in actual_pairs)
    error_action_ids = {e.get("action_id") for e in errors if e.get("action_id") is not None}
    correct = sum(1 for a in actions if a.get("accepted", 1) and a.get("id") not in error_action_ids)
    extra = sum(1 for pair in actual_pairs if pair not in expected_set)
    repeated = sum(1 for left, right in zip(actual_pairs, actual_pairs[1:]) if left == right)
    observed = sum(a.get("old_value") is not None and a.get("new_value") is not None for a in actions)
    changed = sum(_action_changed(a) for a in actions)
    # Relevant response = first subsequent accepted operator action. This is
    # reproducible even when an alarm has no equipment_id mapping.
    response_delays: List[float] = []
    for alarm in alarms:
        raised = alarm.get("raised_at")
        if raised is None:
            continue
        subsequent = [t for a, t in zip(actions, action_times)
                      if a.get("accepted", 1) and t >= float(raised)]
        if subsequent:
            response_delays.append(subsequent[0] - float(raised))
    values: Dict[str, float] = {
        "session_duration_sim_s": max(0.0, sim_end - sim_start),
        "session_duration_wall_s": max(0.0, wall_end - wall_start),
        "time_to_first_action_s": max(0.0, action_times[0] - sim_start) if action_times else 0.0,
        "action_max_idle_s": action_max, "action_count": float(len(actions)),
        "action_unique_equipment_count": float(len({a.get("equipment_id") for a in actions if a.get("equipment_id")})),
        "action_correct_ratio": correct / len(actions) if actions else 0.0,
        "action_extra_count": float(extra), "action_repeated_count": float(repeated),
        "expected_action_count": float(len(expected)), "expected_completed_count": float(completed),
        "expected_completion_ratio": completed / len(expected) if expected else 0.0,
        "error_count": float(len(errors)), "error_unique_type_count": float(len(error_counts)),
        "error_first_at_s": max(0.0, error_times[0] - sim_start) if error_times else 0.0,
        "error_last_at_s": max(0.0, error_times[-1] - sim_start) if error_times else 0.0,
        "alarm_count": float(len(alarms)),
        "alarm_active_at_end_count": float(sum(a.get("cleared_at") is None for a in alarms)),
        "alarm_mean_relevant_action_delay_s": mean(response_delays) if response_delays else 0.0,
        "alarm_max_relevant_action_delay_s": max(response_delays, default=0.0),
        "action_mean_interval_s": action_mean, "action_max_interval_s": action_max,
        "error_mean_interval_s": error_mean, "error_max_interval_s": error_max,
        "equipment_state_observed_action_ratio": observed / len(actions) if actions else 0.0,
        "equipment_state_changed_action_ratio": changed / len(actions) if actions else 0.0,
        "alarm_severity_high_count": float(alarm_severity["HIGH"]),
        "alarm_severity_critical_count": float(alarm_severity["CRITICAL"]),
    }
    for name in ("WRONG_SEQUENCE", "DELAYED_ACTION", "WRONG_EQUIPMENT", "WRONG_ACTION_TYPE",
                 "WRONG_PARAMETER_VALUE", "MISSED_ACTION"):
        values[f"error_{name.lower()}_count"] = float(error_counts[name])
    return {name: float(values[name]) for name in FEATURE_NAMES}


class ErrorCauseModel:
    """Load the joblib artifact once and return its two highest probabilities."""

    def __init__(self, path: str | Path | None = None):
        root = Path(__file__).resolve().parent / "model_output"
        self.path = Path(path or os.getenv("ERROR_CAUSE_MODEL_PATH") or root / "one_vs_rest_logistic.joblib")
        self.metadata_path = self.path.with_name("metadata.json")
        self._model: Any = None
        self._metadata: Dict[str, Any] = {}
        self._load_error = ""

    @property
    def name(self) -> str:
        return self.path.name

    def _load(self) -> Any:
        if self._model is not None:
            return self._model
        if self._load_error:
            raise RuntimeError(self._load_error)
        try:
            import joblib
            artifact = joblib.load(self.path)
            self._metadata = json.loads(self.metadata_path.read_text(encoding="utf-8"))
            if self._metadata.get("feature_names") != list(FEATURE_NAMES):
                raise ValueError("metadata.json не соответствует контракту 34 признаков")
            if isinstance(artifact, dict):
                if artifact.get("feature_names") != list(FEATURE_NAMES):
                    raise ValueError("joblib-бандл не соответствует контракту 34 признаков")
                self._model = artifact.get("model")
            else:
                self._model = artifact
            if not hasattr(self._model, "predict_proba"):
                raise TypeError("В joblib-бандле отсутствует модель predict_proba")
            return self._model
        except Exception as exc:
            self._load_error = f"Модель не загружена: {exc}"
            raise RuntimeError(self._load_error) from exc

    def predict(self, features: Dict[str, float]) -> tuple[List[Dict[str, Any]], str, float]:
        started = time.perf_counter()
        try:
            model = self._load()
            x = np.asarray([[features[name] for name in FEATURE_NAMES]], dtype=float)
            probs = np.asarray(model.predict_proba(x), dtype=float)[0]
            targets = self._metadata["target_columns"]
            names = self._metadata["class_names"]
            ranked = sorted(zip(targets, probs), key=lambda item: float(item[1]), reverse=True)[:2]
            predictions = [{"cause_id": target, "cause": names[target],
                            "confidence": round(float(probability), 6)}
                           for target, probability in ranked]
            return predictions, "ready", (time.perf_counter() - started) * 1000
        except Exception as exc:
            return [], f"unavailable: {exc}", (time.perf_counter() - started) * 1000


MODEL = ErrorCauseModel()
