from ml.error_cause_inference import FEATURE_NAMES, FEATURE_SCHEMA_VERSION, build_features
from persistence.session_store import SessionStore


def test_empty_completed_session_has_exact_model_contract(tmp_path):
    store = SessionStore(tmp_path / "sessions.db")
    sid = store.begin_session("scenario-1", "operator", sim_start=10.0, wall_time=100.0)
    store.start_session(sid, sim_start=10.0, wall_time=100.0)
    store.finish_session(sid, sim_end=25.0, wall_time=120.0)

    features = build_features(store, sid)

    assert tuple(features) == FEATURE_NAMES
    assert len(features) == 34
    assert features["session_duration_sim_s"] == 15.0
    assert features["session_duration_wall_s"] == 20.0
    store.close()


def test_prediction_and_both_human_reviews_are_persisted(tmp_path):
    store = SessionStore(tmp_path / "sessions.db")
    sid = store.begin_session("scenario-1", "operator")
    features = {name: 0.0 for name in FEATURE_NAMES}
    predictions = [
        {"cause_id": "target_1", "cause": "Причина 1", "confidence": 0.8},
        {"cause_id": "target_2", "cause": "Причина 2", "confidence": 0.2},
    ]
    store.save_cause_prediction(
        sid, features, predictions, "model.joblib", "ready", 1.5,
        FEATURE_SCHEMA_VERSION,
    )
    store.save_operator_cause_review(
        sid, {"target_1": False, "target_2": False}, "Случайная ошибка",
    )
    store.save_instructor_cause_review(
        sid, "instructor", False, ["Незнание алгоритма или регламента"],
    )

    review = store.get_cause_review(sid)
    assert review["features_json"] == features
    assert review["predictions_json"] == predictions
    assert review["operator_selected_cause"] == "Случайная ошибка"
    assert review["instructor_causes_json"] == ["Незнание алгоритма или регламента"]
    store.close()
