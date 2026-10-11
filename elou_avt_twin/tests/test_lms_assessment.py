from lms.assessment import practice_criteria, practice_feedback
from lms.content_service import ContentService


def _task():
    return {
        "duration_min": 10,
        "expected_actions": [
            {"seq": 1, "object_id": "pump_H20", "action_type": "TURN_ON"},
            {"seq": 2, "object_id": "pump_H1", "action_type": "TURN_OFF"},
        ],
        "target_state": [],
        "restrictions": [],
    }


def test_missing_all_required_actions_cannot_pass():
    result = practice_criteria(_task(), [], {}, duration_s=10.0)

    assert result["criteria"]["sequence"]["score"] == 0.0
    assert result["score"] == 0.0
    assert result["completed_expected"] == 0
    good, bad = practice_feedback(result)
    assert any("0 из 2" in message for message in bad)
    assert not any("без нарушений" in message for message in good)


def test_partial_required_actions_cap_total_score():
    actions = [{
        "source": "operator_panel",
        "accepted": 1,
        "equipment_id": "pump_H20",
        "action_type": "TURN_ON",
    }]

    result = practice_criteria(_task(), actions, {}, duration_s=10.0)

    assert result["criteria"]["sequence"]["score"] == 50.0
    assert result["score"] <= 50.0


def test_joint_sequence_requires_field_confirmation_in_order():
    task = {
        "duration_min": 10,
        "expected_actions": [
            {"seq": 1, "actor": "field_operator", "object_id": "Н-20", "action_type": "FIELD_INSPECT"},
            {"seq": 2, "actor": "operator", "object_id": "pump_H20", "action_type": "TURN_ON"},
            {"seq": 3, "actor": "field_operator", "object_id": "Н-20", "action_type": "FIELD_CONFIRM_RESULT"},
        ],
        "target_state": [],
        "restrictions": [],
    }
    complete = [
        {"source": "field_operator", "accepted": 1, "equipment_id": "Н-20", "action_type": "FIELD_INSPECT"},
        {"source": "operator_panel", "accepted": 1, "equipment_id": "pump_H20", "action_type": "TURN_ON"},
        {"source": "field_operator", "accepted": 1, "equipment_id": "Н-20", "action_type": "FIELD_CONFIRM_RESULT"},
    ]
    result = practice_criteria(task, complete, {}, duration_s=10.0)
    assert result["criteria"]["sequence"]["score"] == 100.0

    incomplete = practice_criteria(task, complete[1:], {}, duration_s=10.0)
    assert incomplete["criteria"]["sequence"]["score"] < 100.0


def test_required_roles_cover_arm_only_field_only_and_joint_practice():
    roles = ContentService._required_roles_for_actions
    assert roles([{"actor": "operator"}]) == ("operator",)
    assert roles([{"actor": "field_operator"}]) == ("field_operator",)
    assert roles([{"actor": "field_operator"}, {"actor": "operator"}]) == (
        "operator", "field_operator",
    )


def test_every_tracked_error_reduces_score_and_is_explained():
    actions = [
        {"source": "operator_panel", "accepted": 1, "equipment_id": "pump_H20", "action_type": "TURN_ON"},
        {"source": "operator_panel", "accepted": 1, "equipment_id": "pump_H1", "action_type": "TURN_OFF"},
    ]
    errors = [
        {"rule_error_type": "WRONG_SEQUENCE", "severity": "HIGH", "cause": "Нарушена последовательность."},
        {"rule_error_type": "MISSED_ACTION", "severity": "CRITICAL", "cause": "Пропущено обязательное действие."},
    ]

    result = practice_criteria(_task(), actions, {}, duration_s=10.0, tracked_errors=errors)
    _, bad = practice_feedback(result)

    assert result["error_count"] == 2
    assert result["error_penalty"] == 45.0
    assert result["criteria"]["errors"]["score"] == 55.0
    assert result["criteria"]["safety"]["score"] == 50.0
    assert result["score"] < 100.0
    assert not any("Нарушена последовательность" in message for message in bad)
    assert not any("Ошибочные действия" in message or "штраф" in message for message in bad)


def test_missed_then_delayed_same_action_counts_once():
    actions = [
        {"source": "operator_panel", "accepted": 1, "equipment_id": "pump_H20", "action_type": "TURN_ON"},
        {"source": "operator_panel", "accepted": 1, "equipment_id": "pump_H1", "action_type": "TURN_OFF"},
    ]
    errors = [
        {"rule_error_type": "MISSED_ACTION", "severity": "CRITICAL",
         "expected_action": "TURN_ON для pump_H20 до 30.0 с",
         "cause": "Действие не выполнено до срока."},
        {"rule_error_type": "DELAYED_ACTION", "severity": "HIGH",
         "expected_action": "TURN_ON для pump_H20",
         "cause": "Действие выполнено с задержкой 13.0 с."},
    ]

    result = practice_criteria(_task(), actions, {}, duration_s=40.0, tracked_errors=errors)
    _, bad = practice_feedback(result)

    assert result["error_count"] == 1
    assert result["error_penalty"] == 15.0
    assert result["criteria"]["safety"]["score"] == 100.0
    assert not any("не выполнено до срока" in message for message in bad)
    assert not any("задержкой" in message for message in bad)
    assert len(result["tracked_errors"]) == 1
    assert "задержкой" in result["tracked_errors"][0]["cause"]


def test_goal_criterion_reflects_target_state_reached():
    task = _task()
    task["target_state"] = [
        {"object_id": "pump_H20", "attribute": "running", "relation": "==", "value": True},
        {"object_id": "pump_H1", "attribute": "running", "relation": "==", "value": False},
    ]
    telemetry = {"pump_H20": {"running": True}, "pump_H1": {"running": False}}

    result = practice_criteria(task, [], telemetry, duration_s=10.0)
    assert result["criteria"]["goal"]["score"] == 100.0

    telemetry["pump_H20"]["running"] = False
    result = practice_criteria(task, [], telemetry, duration_s=10.0)
    assert result["criteria"]["goal"]["score"] == 50.0


def test_expected_criterion_checks_final_vs_initial_direction():
    task = _task()
    task["expected_actions"] = [
        {"seq": 1, "object_id": "valve_FV1", "attribute": "position", "action_type": "INCREASE_PARAM"},
    ]
    telemetry = {"valve_FV1": {"params": {"position": 70.0}}}
    initial_state = {"valve_FV1_position": 0.2}

    ok = practice_criteria(task, [], telemetry, duration_s=10.0, initial_state=initial_state)
    assert ok["criteria"]["expected"]["score"] == 100.0

    telemetry["valve_FV1"]["params"]["position"] = 10.0
    bad = practice_criteria(task, [], telemetry, duration_s=10.0, initial_state=initial_state)
    assert bad["criteria"]["expected"]["score"] == 0.0


def test_expected_criterion_decrease_direction():
    task = _task()
    task["expected_actions"] = [
        {"seq": 1, "object_id": "valve_FV1", "attribute": "position", "action_type": "DECREASE_PARAM"},
    ]
    telemetry = {"valve_FV1": {"params": {"position": 10.0}}}
    initial_state = {"valve_FV1_position": 0.8}

    ok = practice_criteria(task, [], telemetry, duration_s=10.0, initial_state=initial_state)
    assert ok["criteria"]["expected"]["score"] == 100.0

    telemetry["valve_FV1"]["params"]["position"] = 90.0
    bad = practice_criteria(task, [], telemetry, duration_s=10.0, initial_state=initial_state)
    assert bad["criteria"]["expected"]["score"] == 0.0


def test_expected_criterion_is_skipped_when_not_verifiable():
    task = _task()
    result = practice_criteria(task, [], {}, duration_s=10.0)
    assert result["criteria"]["expected"]["score"] == 100.0

    task["expected_actions"] = [
        {"seq": 1, "object_id": "valve_FV1", "attribute": "position", "action_type": "INCREASE_PARAM"},
    ]
    result = practice_criteria(task, [], {"valve_FV1": {"params": {"position": 50.0}}}, duration_s=10.0)
    assert result["criteria"]["expected"]["score"] == 100.0


def test_legacy_parameters_criterion_still_available():
    task = _task()
    task["target_state"] = [{"object_id": "pump_H20", "attribute": "running", "relation": "==", "value": True}]
    task["criteria"] = [{"key": "parameters", "title": "Контроль параметров", "weight": 1.0}]
    result = practice_criteria(task, [], {"pump_H20": {"running": True}}, duration_s=10.0)
    assert result["criteria"]["parameters"]["score"] == 100.0


def test_expected_failure_appears_in_feedback():
    task = _task()
    task["expected_actions"] = [
        {"seq": 1, "object_id": "valve_FV1", "attribute": "position", "action_type": "INCREASE_PARAM"},
    ]
    telemetry = {"valve_FV1": {"params": {"position": 5.0}}}
    result = practice_criteria(task, [], telemetry, duration_s=10.0,
                               initial_state={"valve_FV1_position": 0.8})
    _, bad = practice_feedback(result)
    assert any("Соблюдение ожидаемых действий" in message for message in bad)
