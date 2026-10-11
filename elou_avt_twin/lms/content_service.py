"""
lms/content_service.py
======================
Business logic of the authoring & study system («Обуч.txt»).

Covers the full loop:
    documentation -> material(Lesson) -> test -> task -> scenario
        -> SCADA run -> assessment -> competency
"""

from __future__ import annotations

import time as _time
import uuid
from typing import Any, Dict, List, Optional

from auth.store import AuthStore
from models.base import ActionType, OperatorAction
from . import assessment as assess
from . import runtime
from .content_models import (
    Assessment,
    AssessmentKind,
    Lesson,
    LessonWrite,
    ModuleStudy,
    QuestionWrite,
    ScadaLogWrite,
    ScenarioDefinition,
    ScenarioWrite,
    TaskWrite,
    TestConfig,
    TestWrite,
    TestSubmit,
    TrainingTask,
)
from .content_store import LmsContentStore
from .scenario_service import to_engine_scenario
from .store import LmsStore


def _effective_expected_actions(task: Dict[str, Any], scenario: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """One canonical plan: scenario steps enriched with task deadlines.

    The authoring UI stores the semantic plan in ``lms_scenarios`` and may
    keep timing constraints in ``lms_training_tasks``.  Comparing whole dicts
    used to duplicate the same three steps into six assessment steps.
    """
    task_actions = list(task.get("expected_actions") or [])
    scenario_actions = list((scenario or {}).get("expected_actions") or [])
    source = scenario_actions or task_actions

    def key(item: Dict[str, Any]) -> tuple:
        return (
            int(item.get("seq") or 0),
            str(item.get("actor") or "operator").lower(),
            item.get("object_id") or item.get("equipment_id") or item.get("equipment") or "",
            str(item.get("action_type") or item.get("action") or "").upper(),
        )

    task_by_key = {key(item): item for item in task_actions}
    result: List[Dict[str, Any]] = []
    for raw in source:
        item = dict(raw)
        timing = task_by_key.get(key(item), {})
        if item.get("deadline_t") is None and timing.get("deadline_t") is not None:
            item["deadline_t"] = timing["deadline_t"]
        # Directional actions are satisfied by the sign of the change. Their
        # optional editor value is not an exact final setpoint.
        if str(item.get("action_type", "")).upper() in ("INCREASE_PARAM", "DECREASE_PARAM"):
            item["value"] = None
        result.append(item)
    return sorted(result, key=lambda item: int(item.get("seq") or 0))


def _expected_actor(item: Dict[str, Any]) -> str:
    """Normalize the authoring role name used by a scenario step."""
    return "field_operator" if str(item.get("actor") or "operator").lower() == "field_operator" else "operator"


def _assess_context(task: Dict[str, Any], scenario: Optional[Dict[str, Any]],
                    start_snapshot: Optional[Dict[str, Any]] = None) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """Build the evaluation task + initial state for practice assessment.

    The scenario is the authoritative source of the exercise definition:
    expected actions, criteria and target states may live on the scenario,
    while the task record keeps a stale snapshot of them.
    """
    eval_task = dict(task)
    scn = scenario or {}
    expected_actions = _effective_expected_actions(task, scenario)
    if expected_actions:
        eval_task["expected_actions"] = expected_actions
    task_targets = list(task.get("target_state") or [])
    scenario_targets = list(scn.get("target_state") or [])
    if scenario_targets:
        eval_task["target_state"] = task_targets + scenario_targets
    scenario_criteria = [c for c in (scn.get("success_criteria") or []) if c.get("key")]
    if scenario_criteria:
        eval_task["criteria"] = [
            {
                "key": c.get("key"),
                "title": c.get("title") or _CRITERION_TITLES.get(c.get("key"), c.get("key")),
                "weight": c.get("weight", 1.0),
            }
            for c in scenario_criteria
        ]
    elif not task.get("criteria"):
        eval_task["criteria"] = [
            {"key": c["key"], "title": c["title"], "weight": c["weight"]}
            for c in assess.DEFAULT_CRITERIA
        ]
    # Начальное состояние используется критерием «Соблюдение ожидаемых
    # действий»: конечное значение направленного параметра сравнивается со
    # стартовым. Реальным стартом считается первый снапшот сессии; авторские
    # initial_state сценария/задания перекрывают его.
    initial_state: Dict[str, Any] = {}
    if start_snapshot:
        initial_state.update(_flat_snapshot_state(start_snapshot))
    for is_dict in (task.get("initial_state") or {}, scn.get("initial_state") or {}):
        if isinstance(is_dict, dict):
            initial_state.update(is_dict)
    return eval_task, initial_state


def _now() -> float:
    return _time.time()


_CRITERION_TITLES = {
    "sequence": "Правильная последовательность",
    "goal": "Выполнение цели",
    "expected": "Соблюдение ожидаемых действий",
    "parameters": "Контроль параметров",
    "time": "Время",
    "errors": "Ошибочные действия",
    "safety": "Безопасность",
}


def _flat_snapshot_state(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a start snapshot into the flat ``<id>_<attribute>`` dict the
    assessment uses as the initial state of a practice."""
    out: Dict[str, Any] = {}
    for node_id, val in (snapshot.get("valve_positions") or {}).items():
        out[f"{node_id}_position"] = val
    for node_id, val in (snapshot.get("pump_states") or {}).items():
        out[f"{node_id}_running"] = bool(val)
    for node_id, val in (snapshot.get("levels") or {}).items():
        out[f"{node_id}_level_m"] = val
    for node_id, st in (snapshot.get("equipment_states") or {}).items():
        if isinstance(st, dict):
            if "running" in st:
                out[f"{node_id}_running"] = bool(st["running"])
            if "failed" in st:
                out[f"{node_id}_failed"] = bool(st["failed"])
            if "fuel_flow" in st:
                out[f"{node_id}_fuel_flow"] = st["fuel_flow"]
    return out


class ContentService:
    #: Сколько секунд ждём подтверждения готовности обоих операторов
    #: (консольный + полевой) перед автоматическим стартом практики.
    CONFIRM_TIMEOUT = 120.0
    REQUIRED_CONFIRM_ROLES = ("operator", "field_operator")

    def __init__(self, content_store: LmsContentStore, lms_store: LmsStore,
                 auth_store: AuthStore):
        self.store = content_store
        self.lms = lms_store
        self.auth = auth_store
        self._ready_sessions: set[str] = set()
        # session_id -> gate: подтверждения операторов перед стартом таймера.
        self._pending_confirms: Dict[str, Dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _user_id(self, username: str) -> Optional[int]:
        u = self.auth.get_user_by_name(username)
        if u is None and username == "system":
            u = self.auth.get_user_by_name("operator")
        return int(u["id"]) if u else None

    def _full_name(self, username: str) -> str:
        u = self.auth.get_user_by_name(username)
        return u.get("full_name", "") if u else ""

    def invite_candidates(self, scenario_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Пользователи, которых инструктор может пригласить в практику.

        Полевой оператор доступен только для мультиоператорного сценария;
        консольного оператора можно пригласить в любом режиме."""
        multi = self._scenario_is_multi(scenario_id)
        out: List[Dict[str, Any]] = []
        for u in self.auth.list_users():
            roles = list(u.roles or [])
            if not u.is_active:
                continue
            if not any(r in ("field_operator", "operator") for r in roles):
                continue
            if "field_operator" in roles and not multi:
                continue
            out.append({
                "user_id": u.id,
                "username": u.username,
                "full_name": u.full_name,
                "roles": roles,
                "role": "field_operator" if "field_operator" in roles else "operator",
            })
        out.sort(key=lambda x: (x["role"], x["full_name"] or x["username"]))
        return out

    def _scenario_is_multi(self, scenario_id: Optional[str]) -> bool:
        """Является ли сценарий (по id вида 'LMS-<n>' или '<n>') мультиоператорным."""
        if not scenario_id:
            return False
        sid: Optional[int] = None
        if scenario_id.startswith("LMS-"):
            try:
                sid = int(scenario_id.split("-", 1)[1])
            except (TypeError, ValueError):
                sid = None
        else:
            try:
                sid = int(scenario_id)
            except (TypeError, ValueError):
                sid = None
        if sid is None:
            return False
        s = self.store.get_scenario(sid)
        return bool(s and s.get("multi_operator"))

    @staticmethod
    def _required_roles_for_actions(actions: List[Dict[str, Any]]) -> tuple[str, ...]:
        """Infer practice participants from authored steps.

        This supports all three formats: ARM-only, field-only and joint
        practice.  Old scenarios without an explicit actor remain ARM-only.
        """
        roles = {_expected_actor(action) for action in actions}
        if roles == {"field_operator"}:
            return ("field_operator",)
        if "field_operator" in roles:
            return ("operator", "field_operator")
        return ("operator",)

    def _resolve_invited(self, invited_usernames: Optional[List[str]]
                         ) -> List[Dict[str, Any]]:
        """Проверить и нормализовать список приглашённых операторов гейтки.

        Возвращает [{username, full_name, role}]. Полевой оператор — основная
        приглашаемая роль; консольного тоже можно пригласить (мультиоператорный
        режим), но он участвует и без приглашения."""
        if not invited_usernames:
            return []
        seen: set[str] = set()
        out: List[Dict[str, Any]] = []
        for name in invited_usernames:
            name = (name or "").strip()
            if not name or name in seen:
                continue
            u = self.auth.get_user_by_name(name)
            if u is None:
                raise ValueError(f"Пользователь '{name}' не найден")
            if not u.get("is_active", True):
                raise ValueError(f"Пользователь '{name}' отключён")
            roles = self.auth.roles_for_user(name)
            if not any(r in ("field_operator", "operator") for r in roles):
                raise ValueError(f"Пользователь '{name}' не является оператором")
            seen.add(name)
            out.append({
                "username": name,
                "full_name": u.get("full_name", "") or name,
                "role": "field_operator" if "field_operator" in roles else "operator",
            })
        return out

    def _module_title(self, module_id: int) -> str:
        m = self.store.module(module_id)
        return m.get("title", "") if m else ""

    def _scenario_title(self, scenario_id: Optional[str]) -> str:
        if not scenario_id:
            return ""
        parts = scenario_id.split("-")
        if len(parts) == 2 and parts[0] == "LMS":
            try:
                s = self.store.get_scenario(int(parts[1]))
                return s.get("title", "") if s else ""
            except (TypeError, ValueError):
                return ""
        return scenario_id

    def _task_title(self, task_id: Optional[int]) -> str:
        if not task_id:
            return ""
        t = self.store.get_task(int(task_id))
        return t.get("title", "") if t else ""

    def _module_ok(self, module_id: int) -> Dict[str, Any]:
        m = self.store.module(module_id)
        if m is None:
            raise KeyError(f"Модуль '{module_id}' не найден")
        return m

    # ------------------------------------------------------------------
    # Equipment / competencies catalog (для привязки в конструкторе)
    # ------------------------------------------------------------------

    def equipment_catalog(self) -> List[Dict[str, Any]]:
        scheme = runtime.get_scheme()
        if scheme is None:
            return []
        return [
            {"id": n.id, "type": n.type, "name": n.name,
             "params": {k: v for k, v in (n.params or {}).items() if isinstance(v, (int, float))}}
            for n in scheme.nodes
        ]

    def competency_catalog(self) -> List[Dict[str, Any]]:
        return self.lms.list_competencies()

    # ------------------------------------------------------------------
    # Authoring views
    # ------------------------------------------------------------------

    def module_authoring_view(self, module_id: int) -> Dict[str, Any]:
        m = self._module_ok(module_id)
        lessons = self.store.list_lessons(module_id)
        test = self.store.get_test_by_module(module_id, with_answers=True)
        task = self.store.get_task_by_module(module_id)
        scenario = self.store.get_scenario_by_module(module_id)
        return {
            "module": {
                **m,
                "published": bool(m.get("published")),
                "course_id": m.get("course_id"),
            },
            "lessons": lessons,
            "test": test,
            "task": task,
            "scenario": scenario,
        }

    def publish_module(self, module_id: int, published: bool) -> Dict[str, Any]:
        m = self._module_ok(module_id)
        self.store.set_module_published(module_id, published)
        self.lms.add_log(
            f"Модуль «{m['title']}» {'опубликован' if published else 'снят с публикации'}",
            category="authoring")
        return self.module_authoring_view(module_id)

    # ------------------------------------------------------------------
    # Lessons
    # ------------------------------------------------------------------

    def create_lesson(self, module_id: int, w: LessonWrite) -> Dict[str, Any]:
        self._module_ok(module_id)
        lid = self.store.create_lesson(module_id, w)
        return self.store.get_lesson(lid)

    def update_lesson(self, lesson_id: int, w: LessonWrite) -> Dict[str, Any]:
        self.store.update_lesson(lesson_id, w)
        return self.store.get_lesson(lesson_id)

    def delete_lesson(self, lesson_id: int) -> None:
        self.store.delete_lesson(lesson_id)

    # ------------------------------------------------------------------
    # Tests
    # ------------------------------------------------------------------

    def save_test(self, module_id: int, w: TestWrite) -> Dict[str, Any]:
        self._module_ok(module_id)
        tid = self.store.upsert_test(module_id, w)
        return self.store.get_test(tid)

    def delete_test(self, test_id: int) -> None:
        self.store.delete_test(test_id)

    def create_question(self, test_id: int, w: QuestionWrite) -> Dict[str, Any]:
        qid = self.store.create_question(test_id, w)
        return self.store.get_question(qid)

    def update_question(self, question_id: int, w: QuestionWrite) -> Dict[str, Any]:
        self.store.update_question(question_id, w)
        return self.store.get_question(question_id)

    def delete_question(self, question_id: int) -> None:
        self.store.delete_question(question_id)

    # ------------------------------------------------------------------
    # Tasks
    # ------------------------------------------------------------------

    def save_task(self, module_id: int, w: TaskWrite) -> Dict[str, Any]:
        self._module_ok(module_id)
        tid = self.store.upsert_task(module_id, w)
        return self.store.get_task(tid)

    def delete_task(self, task_id: int) -> None:
        self.store.delete_task(task_id)

    # ------------------------------------------------------------------
    # Scenarios
    # ------------------------------------------------------------------

    def save_scenario(self, module_id: int, w: ScenarioWrite) -> Dict[str, Any]:
        self._module_ok(module_id)
        sid = self.store.upsert_scenario(module_id, w)
        return self.store.get_scenario(sid)

    def delete_scenario(self, scenario_id: int) -> None:
        self.store.delete_scenario(scenario_id)

    def scenarios_catalog(self) -> List[Dict[str, Any]]:
        """Все сценарии всех модулей (для администратора)."""
        return self.store.list_scenarios()

    def set_scenario_status(self, scenario_id: int, status: str) -> Dict[str, Any]:
        s = self.store.get_scenario(scenario_id)
        if s is None:
            raise KeyError(f"Сценарий '{scenario_id}' не найден")
        allowed = {"DRAFT", "REVIEW", "PUBLISHED", "ARCHIVED"}
        status = status.upper()
        if status not in allowed:
            raise ValueError(f"Недопустимый статус: {status}")
        self.store.set_scenario_status(scenario_id, status)
        return self.store.get_scenario(scenario_id)

    def scenario_status_flow(self, scenario_id: int) -> List[Dict[str, Any]]:
        s = self.store.get_scenario(scenario_id)
        if s is None:
            raise KeyError(f"Сценарий '{scenario_id}' не найден")
        current = s.get("status", "DRAFT")
        next_map = {
            "DRAFT": "REVIEW",
            "REVIEW": "PUBLISHED",
            "PUBLISHED": "ARCHIVED",
        }
        return [{"status": st, "current": st == current,
                 "next": next_map.get(st)} for st in ("DRAFT", "REVIEW", "PUBLISHED", "ARCHIVED")]

    # ------------------------------------------------------------------
    # Operator study view (только опубликованный контент)
    # ------------------------------------------------------------------

    def study_view(self, module_id: int) -> ModuleStudy:
        m = self._module_ok(module_id)
        if not m.get("published"):
            raise PermissionError("Модуль не опубликован — оператору недоступен")
        lessons = self.store.list_lessons(module_id)
        test = self.store.get_test_by_module(module_id, with_answers=False)
        task = self.store.get_task_by_module(module_id)
        if task and not task.get("enabled"):
            task = None
        scenario = self.store.get_scenario_by_module(module_id)
        if scenario and scenario.get("status") != "PUBLISHED":
            scenario = None
        return ModuleStudy(
            module={"id": m["id"], "title": m["title"], "description": m.get("description", ""),
                    "kind": m.get("kind"), "content": m.get("content", "")},
            lessons=[Lesson(**l) for l in lessons],
            test=TestConfig(**test) if test else None,
            task=TrainingTask(**task) if task else None,
            scenario=ScenarioDefinition(**scenario) if scenario else None,
            equipment=self.equipment_catalog(),
            competencies=self.competency_catalog(),
        )

    # ------------------------------------------------------------------
    # Practice catalog (страница «Практика» = сценарии курсов)
    # ------------------------------------------------------------------

    def _practice_task_view(self, task: Dict[str, Any], module: Dict[str, Any],
                            scenario: Dict[str, Any], comp_levels: Dict[str, float]) -> Dict[str, Any]:
        req = task.get("competency_codes", []) or []
        avg_req = (sum(comp_levels.get(c, 0.0) for c in req) / len(req)) if req else 100.0
        is_exam = bool(scenario.get("is_exam"))
        return {
            "id": task["id"],
            "module_id": int(task["module_id"]),
            "module_title": module.get("title", ""),
            "title": task.get("title", ""),
            "description": scenario.get("goal", "") or task.get("goal", ""),
            "goal": scenario.get("goal", "") or task.get("goal", ""),
            "target_state": scenario.get("target_state", []) or task.get("target_state", []),
            "scenario_id": f"LMS-{scenario['id']}",
            "scenario_name": scenario.get("title", ""),
            "category": "exam" if is_exam else "practice",
            "difficulty": "HARD" if is_exam else "MIDDLE",
            "duration_min": int(task.get("duration_min", 10) or 10),
            "required_competencies": req,
            "enabled": True,
            "is_random": False,
            "is_ready": avg_req >= 50.0,
            "readiness_percent": round(avg_req, 1),
        }

    def practice_catalog(self, username: str) -> List[Dict[str, Any]]:
        """Опубликованные практические задания курсов.

        «Практика» = сценарии курсов: берутся только опубликованные модули
        с заданием и опубликованным сценарием (lms_training_tasks +
        lms_scenarios). Запуск идёт тем же движком, что и в курсах.
        """
        user_id = self._user_id(username) or 0
        comp_levels = {c["code"]: float(c["level_percent"])
                       for c in self.lms.get_user_competencies(user_id)}
        out = []
        for course in self.lms.list_courses():
            for module in self.lms.get_modules(int(course["id"])):
                mid = int(module["id"])
                m = self.store.module(mid)
                if m is None or not m.get("published"):
                    continue
                task = self.store.get_task_by_module(mid)
                if task is None or not task.get("enabled"):
                    continue
                scenario = self.store.get_scenario_by_module(mid)
                if scenario is None or scenario.get("status") != "PUBLISHED":
                    continue
                out.append(self._practice_task_view(task, m, scenario, comp_levels))
        out.sort(key=lambda t: (t["category"], t["module_title"], t["title"]))
        return out

    def practice_catalog_task(self, task_id: int,
                              username: Optional[str] = None) -> Optional[Dict[str, Any]]:
        task = self.store.get_task(task_id)
        if task is None:
            return None
        module_id = int(task["module_id"])
        m = self.store.module(module_id)
        scenario = self.store.get_scenario_by_module(module_id)
        if m is None or scenario is None:
            return None
        # Задание, запущенное инструктором, открывается оператором и до
        # публикации модуля/сценария (иначе «задание не найдено»).
        published = m.get("published") and scenario.get("status") == "PUBLISHED"
        if not published and not self._is_active_task(task_id):
            return None
        user_id = self._user_id(username) if username else 0
        comp_levels = {c["code"]: float(c["level_percent"])
                       for c in self.lms.get_user_competencies(user_id)}
        return self._practice_task_view(task, m, scenario, comp_levels)

    def _is_active_task(self, task_id: int) -> bool:
        """Задание относится к текущей активной практике (запущенной инструктором),
        даже если её модуль/сценарий ещё не опубликованы."""
        recorder = runtime.get_session_recorder()
        if recorder is None or not recorder.active:
            return False
        session_store = runtime.get_session_store()
        session = session_store.get_session(recorder.session_id) if session_store else None
        nav = self._practice_navigation(session.get("scenario_id") if session else None)
        return nav.get("task_id") == task_id

    # ------------------------------------------------------------------
    # Test submission
    # ------------------------------------------------------------------

    def submit_test(self, test_id: int, username: str, req: TestSubmit) -> Dict[str, Any]:
        test = self.store.get_test(test_id, with_answers=True)
        if test is None:
            raise KeyError(f"Тест '{test_id}' не найден")
        result = assess.assess_test(test, req.answers, duration_s=req.duration_s)
        module_id = int(test["module_id"])
        user_id = self._user_id(username) or 0

        # Blending competencies + module progress are applied on the best try.
        previous = self.store.latest_assessment(user_id, module_id, "test")
        if previous is None or result["score"] > float(previous.get("score", 0.0)):
            self._apply_competencies(user_id, test.get("competency_codes", []), result["score"])
            self.lms.mark_module_completed(user_id, module_id, result["score"])

        a = Assessment(
            user_id=user_id, module_id=module_id, kind=AssessmentKind.TEST,
            test_id=test_id, score=result["score"], max_score=100.0,
            passed=result["passed"], criteria_scores={
                "test": {"score": result["score"], "passed": result["passed"]},
                "detail": result["questions"]},
            errors_count=result.get("unanswered_required", 0),
            duration_s=req.duration_s,
            answers=req.answers,
            feedback_good=result["feedback_good"],
            feedback_bad=result["feedback_bad"],
            started_at=_now() - req.duration_s,
            finished_at=_now(),
        )
        aid = self.store.create_assessment(a)
        return self._assessment_view(aid)

    # ------------------------------------------------------------------
    # Practice: scenario run + finish
    # ------------------------------------------------------------------

    def start_practice(self, module_id: int, username: str, kind: str = "practice",
                       mode: str = "gated",
                       invited_usernames: Optional[List[str]] = None) -> Dict[str, Any]:
        m = self._module_ok(module_id)
        task = self.store.get_task_by_module(module_id)
        scenario = self.store.get_scenario_by_module(module_id)
        if task is None:
            raise KeyError("У модуля нет практического задания")
        scenario_id = task.get("scenario_id") or (f"LMS-{scenario['id']}" if scenario else "NORMAL_OPERATION")
        scenario_name = task.get("title", scenario_id)

        twin = runtime.get_twin()
        recorder = runtime.get_session_recorder()

        if recorder is not None and recorder.active:
            recorder.abort(reason="superseded by new practice session")
        self._ready_sessions.clear()
        self._pending_confirms.clear()
        session_store = runtime.get_session_store()
        session_id = f"PR-{uuid.uuid4().hex}"

        # DB-сценарий -> физическое ядро; иначе библиотечный сценарий.
        if scenario is not None:
            reference_actions = _effective_expected_actions(task, scenario)
            engine_scenario = to_engine_scenario(scenario, reference_actions=[
                {
                    "t": a.get("deadline_t"),
                    "action": a.get("action_type", ""),
                    "equipment": a.get("object_id", ""),
                    "attribute": a.get("attribute", ""),
                    "value": a.get("value"),
                    "description": a.get("description", ""),
                    "weight": a.get("weight", 1.0),
                }
                # Local confirmations must not be registered with the
                # physical engine's ErrorTracker: they arrive through the
                # field-operator API and are assessed from the session log.
                for a in reference_actions if _expected_actor(a) == "operator"
            ])
            twin.create_simulation()
            scheme = runtime.get_scheme()
            if scheme is not None:
                twin._engine.set_scheme(scheme)
            twin.load_scenario_object(engine_scenario)
        else:
            twin.create_simulation()
            scheme = runtime.get_scheme()
            if scheme is not None:
                twin._engine.set_scheme(scheme)
            twin.load_scenario(task.get("scenario_id") or "NORMAL_OPERATION")

        runtime.restore_alarm_setpoints()
        twin._engine.set_feed_override(runtime.get_inputs())

        if recorder is not None:
            recorder.begin(
                scenario_id=scenario_id,
                operator_id=username,
                scheme_version=scheme.id if scheme else "",
                reference_actions=_effective_expected_actions(task, scenario),
                sim_start=twin._simulation_time,
                session_id=session_id,
            )
            recorder.record_snapshot(twin.get_state(), reason="start")

        self.lms.mark_module_started(self._user_id(username) or 0, module_id)
        if mode == "gated":
            # Инструктор запустил: таймер стартует после подтверждения обоих
            # операторов (или по истечении CONFIRM_TIMEOUT).
            invited = self._resolve_invited(invited_usernames)
            is_multi = bool(scenario.get("multi_operator")) if scenario else False
            required_roles = self._required_roles_for_actions(
                _effective_expected_actions(task, scenario)
            )
            if not is_multi and any(i.get("role") == "field_operator" for i in invited):
                raise ValueError(
                    "Сценарий не мультиоператорный: полевой оператор недоступен для приглашения")
            self._pending_confirms[session_id] = {
                "confirmed": set(),
                "who": {},
                "invited": invited,
                "required_roles": required_roles,
                "started": False,
                "deadline": _time.time() + self.CONFIRM_TIMEOUT,
            }
            # Участники практики — для доступа к отчёту (debrief).
            if session_store is not None:
                session_store.set_participants(
                    session_id, [u.get("username", "") for u in invited]
                )
            self.lms.add_log(
                f"Инструктор {username} запустил практику «{task.get('title')}» — ожидание подтверждения операторов",
                category="practice",
            )
            return {
                "session_id": session_id,
                "scenario_id": scenario_id,
                "scenario_name": scenario_name,
                "module_id": module_id,
                "task_id": task["id"],
                "sim_time": twin._simulation_time,
                "status": "PENDING_CONFIRM",
                "required_roles": list(required_roles),
                "confirmed_roles": [],
                "invited_users": invited,
                "timeout_seconds": int(self.CONFIRM_TIMEOUT),
            }

        # Режим индивидуальной практики (курс): старт, как раньше, по /ready.
        self.lms.add_log(
            f"Оператор {username} начал практику «{task.get('title')}»", category="practice")
        return {
            "session_id": session_id,
            "scenario_id": scenario_id,
            "scenario_name": scenario_name,
            "module_id": module_id,
            "task_id": task["id"],
            "sim_time": twin._simulation_time,
            "status": "PENDING_CONFIRM",
            "required_roles": list(self._required_roles_for_actions(
                _effective_expected_actions(task, scenario)
            )),
            "confirmed_roles": [],
            "timeout_seconds": int(self.CONFIRM_TIMEOUT),
        }

    def ready_practice(self, session_id: str, username: str,
                       role: str = "operator") -> Dict[str, Any]:
        """SCADA оператора готова.

        При гейтке (инструктор запустил практику) — подтверждение роли и старт
        после подтверждения обоих. Без гейтки (индивидуальная практика курса) —
        немедленный старт таймера, как в исходном флоу.
        """
        recorder = runtime.get_session_recorder()
        if recorder is None or recorder.session_id != session_id:
            raise KeyError(f"Сессия '{session_id}' не является активной")
        if session_id not in self._pending_confirms:
            twin = runtime.get_twin()
            twin.start()
            store = runtime.get_session_store()
            if store is not None:
                store.start_session(session_id, sim_start=twin._simulation_time)
            self._ready_sessions.add(session_id)
            self.lms.add_log(
                f"SCADA оператора {username} готова, таймер практики запущен",
                category="practice",
            )
            return {
                "session_id": session_id,
                "status": "RUNNING",
                "sim_time": twin._simulation_time,
            }
        return self.confirm_practice(session_id, username, role)

    def _practice_status_dict(self, session_id: str,
                              gate: Dict[str, Any]) -> Dict[str, Any]:
        twin = runtime.get_twin()
        session_store = runtime.get_session_store()
        session = session_store.get_session(session_id) if session_store else None
        sim_start = session.get("sim_start") if session else None
        if sim_start is None and gate["started"]:
            sim_start = twin._simulation_time
        return {
            "session_id": session_id,
            "status": "RUNNING" if gate["started"] else "PENDING_CONFIRM",
            "confirmed_roles": sorted(gate["confirmed"]),
            "required_roles": list(gate.get("required_roles") or self.REQUIRED_CONFIRM_ROLES),
            "confirmed_names": list(
                v.get("full_name", v.get("username", ""))
                for v in gate.get("who", {}).values()
            ),
            "invited_users": list(gate.get("invited", [])),
            "invited_roles": sorted({i["role"] for i in gate.get("invited", [])}),
            "timeout_seconds": int(max(0.0, gate["deadline"] - _time.time()))
            if not gate["started"] else None,
            "sim_time": sim_start,
        }

    def _start_gated_practice(self, session_id: str, reason: str) -> None:
        """Общий старт таймера практики (подтверждение/таймаут)."""
        gate = self._pending_confirms.get(session_id)
        if gate is None or gate.get("started"):
            return
        twin = runtime.get_twin()
        twin.start()
        store = runtime.get_session_store()
        if store is not None:
            store.start_session(session_id, sim_start=twin._simulation_time)
            who = gate.get("who", {})
            op = who.get("operator") or who.get("field_operator")
            if op and op.get("username"):
                store.set_operator(session_id, op["username"])
        gate["started"] = True
        gate["started_by"] = reason
        self.lms.add_log(
            f"Практика {session_id[:8]}: {reason}, таймер запущен",
            category="practice",
        )

    def _expire_if_past_deadline(self, session_id: str,
                                 gate: Dict[str, Any]) -> None:
        if not gate.get("started") and _time.time() >= gate["deadline"]:
            self._start_gated_practice(
                session_id, reason="истёк таймаут ожидания подтверждения (2 мин)")

    def confirm_practice(self, session_id: str, username: str,
                         role: str) -> Dict[str, Any]:
        """Подтверждение готовности участником практики.

        Практика стартует после подтверждения всех ролей, указанных в плане
        сценария; фолбэк — автостарт по истечении таймаута."""
        recorder = runtime.get_session_recorder()
        if recorder is None or recorder.session_id != session_id:
            raise KeyError(f"Сессия '{session_id}' не является активной")
        gate = self._pending_confirms.get(session_id)
        if gate is None:
            status = self.practice_status(session_id)
            if status is None:
                raise KeyError(f"Сессия '{session_id}' не является активной")
            return status
        if gate["started"]:
            return self._practice_status_dict(session_id, gate)
        required_roles = tuple(gate.get("required_roles") or self.REQUIRED_CONFIRM_ROLES)
        if role not in required_roles:
            raise PermissionError(f"Роль '{role}' не участвует в подтверждении практики")
        if role == "field_operator":
            invited = gate.get("invited") or []
            invited_names = {i["username"] for i in invited}
            if not invited_names or username not in invited_names:
                raise PermissionError(
                    "Вы не приглашены в эту практику: полевой оператор выбирается инструктором при запуске")
        if role not in gate["confirmed"]:
            gate["confirmed"].add(role)
            gate["who"][role] = {
                "username": username,
                "full_name": self._full_name(username) or username,
            }
            self.lms.add_log(
                f"Оператор {username} ({role}) подтвердил готовность к практике",
                category="practice",
            )
        if gate["confirmed"] >= set(required_roles):
            self._start_gated_practice(session_id, reason="все участники подтвердили готовность")
        else:
            self._expire_if_past_deadline(session_id, gate)
        return self._practice_status_dict(session_id, gate)

    def decline_practice(self, session_id: str, username: str) -> Dict[str, Any]:
        """Отклонение поступившей практики оператором: ожидающая сессия отменяется."""
        recorder = runtime.get_session_recorder()
        if recorder is None or recorder.session_id != session_id:
            raise KeyError(f"Сессия '{session_id}' не является активной")
        gate = self._pending_confirms.get(session_id)
        if gate is None or gate.get("started"):
            raise PermissionError("Практика уже началась и не может быть отклонена")
        recorder.abort(reason="практика отклонена оператором")
        self._pending_confirms.pop(session_id, None)
        self._ready_sessions.discard(session_id)
        self.lms.add_log(
            f"Оператор {username} отклонил практику {session_id[:8]}",
            category="practice",
        )
        return {"session_id": session_id, "status": "DECLINED", "ok": True}

    def practice_status(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Текущее состояние гейтки сессии (None — сессия не активна)."""
        recorder = runtime.get_session_recorder()
        if recorder is None or recorder.session_id != session_id:
            return None
        gate = self._pending_confirms.get(session_id)
        if gate is None:
            # Активная сессия без гейтки (уже запущена/старая) — RUNNING.
            session_store = runtime.get_session_store()
            session = session_store.get_session(session_id) if session_store else None
            scenario, task = self._scenario_task_for_session(session_id)
            required_roles = self._required_roles_for_actions(
                _effective_expected_actions(task or {}, scenario)
            )
            return {
                "session_id": session_id,
                "status": "RUNNING",
                "confirmed_roles": sorted(required_roles),
                "required_roles": list(required_roles),
                "confirmed_names": [],
                "timeout_seconds": None,
                "sim_time": session.get("sim_start") if session else None,
            }
        self._expire_if_past_deadline(session_id, gate)
        return self._practice_status_dict(session_id, gate)

    def _task_title_for_scenario(self, scenario_id: Optional[str]) -> str:
        if not scenario_id:
            return ""
        if scenario_id.startswith("LMS-"):
            try:
                scenario = self.store.get_scenario(int(scenario_id.split("-", 1)[1]))
                if scenario:
                    task = self.store.get_task_by_module(int(scenario["module_id"])) if scenario.get("module_id") else None
                    if task:
                        return task.get("title", "")
                    return scenario.get("title", "") or ""
            except (TypeError, ValueError):
                pass
        for t in self.store.list_tasks_all():
            if t.get("scenario_id") == scenario_id:
                return t.get("title", "")
        return scenario_id

    def _practice_navigation(self, scenario_id: Optional[str]) -> Dict[str, Any]:
        """module_id и id задания (lms_training_tasks) для перехода оператора к
        активной практике. Сценарии курсов идентифицируются как LMS-<id>;
        библиотечные задания (lms_practice_tasks) — по scenario_id."""
        module_id = None
        task_id = None
        if scenario_id:
            if scenario_id.startswith("LMS-"):
                try:
                    s = self.store.get_scenario(int(scenario_id.split("-", 1)[1]))
                    if s and s.get("module_id"):
                        module_id = int(s["module_id"])
                except (TypeError, ValueError):
                    pass
                if module_id:
                    task = self.store.get_task_by_module(module_id)
                    if task:
                        task_id = int(task["id"])
            else:
                for t in self.lms.list_tasks():
                    if t.get("scenario_id") == scenario_id:
                        task_id = t.get("id")
                        break
        return {"module_id": module_id, "task_id": task_id}

    def current_practice(self) -> Optional[Dict[str, Any]]:
        """Текущая (ожидающая/идущая) практика с гейткой подтверждения."""
        recorder = runtime.get_session_recorder()
        if recorder is None or not recorder.active:
            return None
        session_id = recorder.session_id
        status = self.practice_status(session_id)
        if status is None:
            return None
        session_store = runtime.get_session_store()
        session = session_store.get_session(session_id) if session_store else None
        scenario_id = session.get("scenario_id") if session else None
        status["scenario_id"] = scenario_id
        status["task_title"] = self._task_title_for_scenario(scenario_id)
        status["scenario_name"] = self._scenario_title(scenario_id)
        status.update(self._practice_navigation(scenario_id))
        return status

    def _scenario_task_for_session(self, session_id: str) -> tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """Return the authored scenario and task bound to an active session."""
        session_store = runtime.get_session_store()
        session = session_store.get_session(session_id) if session_store else None
        scenario_id = str((session or {}).get("scenario_id") or "")
        if not scenario_id.startswith("LMS-"):
            return None, None
        try:
            scenario = self.store.get_scenario(int(scenario_id.split("-", 1)[1]))
        except (TypeError, ValueError):
            scenario = None
        task = self.store.get_task_by_module(int(scenario["module_id"])) if scenario else None
        return scenario, task

    @staticmethod
    def _step_matches_action(step: Dict[str, Any], action: Dict[str, Any]) -> bool:
        actor = _expected_actor(step)
        required_source = "field_operator" if actor == "field_operator" else "operator_panel"
        if action.get("source") != required_source or not action.get("accepted", 1):
            return False
        if step.get("object_id") and action.get("equipment_id") != step.get("object_id"):
            return False
        return str(action.get("action_type") or "").upper() == str(step.get("action_type") or "").upper()

    def field_action_progress(self, session_id: str) -> List[Dict[str, Any]]:
        """Return field steps with a server-derived state for the active plan.

        A field confirmation is available only when every preceding action in
        the common ARM/field sequence has been logged.  This makes joint
        exercises genuinely collaborative instead of two independent checklists.
        """
        scenario, task = self._scenario_task_for_session(session_id)
        if not scenario or not scenario.get("multi_operator"):
            return []
        expected = _effective_expected_actions(task or {}, scenario)
        expected = sorted(expected, key=lambda item: int(item.get("seq") or 0))
        session_store = runtime.get_session_store()
        actions = session_store.get_actions(session_id) if session_store else []
        cursor = 0
        first_pending = len(expected)
        for index, step in enumerate(expected):
            found = False
            while cursor < len(actions):
                if self._step_matches_action(step, actions[cursor]):
                    cursor += 1
                    found = True
                    break
                cursor += 1
            if not found:
                first_pending = index
                break

        out: List[Dict[str, Any]] = []
        for index, step in enumerate(expected):
            if _expected_actor(step) != "field_operator":
                continue
            state = "completed" if index < first_pending else (
                "available" if index == first_pending else "locked"
            )
            out.append({
                "seq": int(step.get("seq") or index + 1),
                "object_id": str(step.get("object_id") or ""),
                "action_type": str(step.get("action_type") or ""),
                "description": str(step.get("description") or ""),
                "deadline_t": step.get("deadline_t"),
                "status": state,
            })
        return out

    def complete_field_action(self, session_id: str, username: str,
                              object_id: str, action_type: str) -> List[Dict[str, Any]]:
        """Persist one verified local action and unlock the next scenario step."""
        recorder = runtime.get_session_recorder()
        status = self.practice_status(session_id)
        if recorder is None or not recorder.active or recorder.session_id != session_id or not status:
            raise KeyError("Нет активной практики для полевого действия")
        if status.get("status") != "RUNNING":
            raise ValueError("Практика ещё не запущена")
        gate = self._pending_confirms.get(session_id) or {}
        participant = (gate.get("who", {}).get("field_operator") or {}).get("username")
        if participant and participant != username:
            raise PermissionError("Полевое действие выполняет приглашённый полевой оператор")

        steps = self.field_action_progress(session_id)
        current = next((step for step in steps if step["status"] == "available"), None)
        if current is None:
            raise ValueError("Нет доступного полевого действия: выполните предыдущий шаг сценария")
        if current["object_id"] != object_id or current["action_type"].upper() != action_type.upper():
            raise ValueError("Нарушена последовательность полевых действий")
        try:
            kind = ActionType(action_type.upper())
        except ValueError as exc:
            raise ValueError("Недопустимый тип полевого действия") from exc
        if kind not in {
            ActionType.FIELD_INSPECT,
            ActionType.FIELD_CONFIRM_LOCAL,
            ActionType.FIELD_CONFIRM_RESULT,
        }:
            raise ValueError("Это действие доступно только на экране полевого оператора")

        twin = runtime.get_twin()
        recorder.record_action(OperatorAction(
            timestamp=float(twin._simulation_time),
            operator_id=username,
            equipment_id=object_id,
            action_type=kind,
            source="field_operator",
        ), node_type="field")
        self.lms.add_log(
            f"Полевой оператор {username}: {action_type} на {object_id}",
            category="practice",
        )
        return self.field_action_progress(session_id)

    def finish_practice(self, session_id: str, username: str) -> Dict[str, Any]:
        session_store = runtime.get_session_store()
        session = session_store.get_session(session_id) if session_store else None
        if session is None:
            raise KeyError(f"Сессия '{session_id}' не найдена")
        # Результат засчитывается оператору, исполнившему практику: если сессию
        # завершает инструктор (мониторинг), ищем подтверждённого консольного
        # оператора в гейтке; иначе — сам вызывающий.
        operator = username
        if not any(r in ("operator", "field_operator")
                   for r in self.auth.roles_for_user(username)):
            gate = self._pending_confirms.get(session_id) or {}
            who = gate.get("who", {})
            op = who.get("operator") or who.get("field_operator")
            if op and op.get("username"):
                operator = op["username"]
        actions = session_store.get_actions(session_id)
        tracked_errors = session_store.get_errors(session_id)
        task = None
        scenario = None
        # find task by scenario binding
        scenario_id = session.get("scenario_id", "")
        if scenario_id.startswith("LMS-"):
            try:
                sid = int(scenario_id.split("-", 1)[1])
                scenario = self.store.get_scenario(sid)
                task = self.store.get_task_by_module(int(scenario["module_id"])) if scenario else None
            except (TypeError, ValueError):
                task = None
        if task is None:
            # library scenario -> first task referencing it
            for t in self.store.list_tasks_all():
                if t.get("scenario_id") == scenario_id:
                    task = t
                    break

        telemetry = runtime.node_telemetry()
        dur = 0.0
        if session.get("sim_start") is not None and session.get("sim_end") is not None:
            dur = max(0.0, float(session["sim_end"]) - float(session["sim_start"]))
        else:
            # During assessment the recorder is still active, so sim_end has
            # not yet been committed. Use current simulation time; wall time
            # includes UI/network/loading delays and unfairly reduced score.
            dur = max(0.0, float(runtime.get_twin()._simulation_time) - float(session.get("sim_start") or 0.0))

        if task is None:
            result = {"score": 0.0, "criteria": {}, "violations": [],
                      "feedback_good": [], "feedback_bad": ["Задание не найдено для оценки"]}
            module_id = 0
        else:
            # Сценарий является авторитетным источником определения задания:
            # ожидаемые действия, критерии и целевые состояния могут жить в
            # сценарии, а запись задания хранит лишь старый срез. Собираем
            # полный контекст, не изменяя данные в БД.
            # Нужен один стартовый снимок, а не полная (иногда очень большая)
            # временная серия. Это существенно сокращает время завершения.
            start_snapshot = session_store.get_first_snapshot(session_id, "step") if session_store else None
            if start_snapshot is None and session_store:
                start_snapshot = session_store.get_first_snapshot(session_id)
            eval_task, initial_state = _assess_context(task, scenario, start_snapshot)

            result = assess.practice_criteria(
                eval_task, actions, telemetry, dur, tracked_errors,
                initial_state=initial_state,
            )
            module_id = int(task["module_id"])
            good, bad = assess.practice_feedback(result)
            result["feedback_good"] = good
            result["feedback_bad"] = bad

        # Журнал действий оператора («Обуч.txt» §12).
        user_id = self._user_id(operator) or 0
        action_log_rows = []
        for a in actions:
            action_log_rows.append({
                "timestamp": float(a.get("wall_time") or _time.time()),
                "user_id": user_id,
                "username": operator,
                "object_id": a.get("equipment_id", ""),
                "object_name": a.get("equipment_id", ""),
                "action": a.get("action_type", ""),
                "old_state": a.get("old_value"),
                "new_state": a.get("new_value"),
                "source": a.get("source", "operator_panel"),
                "session_id": session_id,
                "module_id": module_id or None,
            })
        self.store.add_action_logs(action_log_rows)

        score = result.get("score", 0.0)
        errors_count = int(result.get("error_count", 0))
        critical_count = sum(1 for v in result.get("violations", [])
                             if str(v.get("severity", "")).upper() == "CRITICAL")
        critical_count += sum(
            1 for error in result.get("tracked_errors", [])
            if str(error.get("severity", "")).upper() == "CRITICAL"
        )
        passed = score >= 70.0

        if module_id and user_id:
            self._apply_competencies(user_id, task.get("competency_codes", []), score)
            self.lms.mark_module_completed(user_id, module_id, score, session_id=session_id)

        a = Assessment(
            user_id=user_id, module_id=module_id, kind=AssessmentKind.PRACTICE,
            task_id=task["id"] if task else None,
            scenario_id=scenario_id, score=score, max_score=100.0, passed=passed,
            criteria_scores=result.get("criteria", {}),
            errors_count=errors_count, critical_errors_count=critical_count,
            duration_s=round(dur, 1), answers=None,
            feedback_good=result.get("feedback_good", []),
            feedback_bad=result.get("feedback_bad", []),
            session_id=session_id, started_at=float(session.get("wall_start", 0.0)),
            finished_at=_now(),
        )
        aid = self.store.create_assessment(a)
        self.lms.add_log(f"Оператор {operator} завершил практику: {score:.0f}/100", category="assessment")

        # Закрыть общий рекордер, чтобы последующие действия оператора
        # не попадали в завершённую практику.
        recorder = runtime.get_session_recorder()
        if recorder is not None and recorder.active and recorder.session_id == session_id:
            # Зафиксировать ошибки, появившиеся на последнем simulation tick,
            # до отсоединения рекордера.
            twin = runtime.get_twin()
            twin._engine._error_tracker.check_missed_actions(twin._simulation_time)
            recorder.sync_errors(twin._engine.get_events())
            recorder.end(sim_end=runtime.get_twin()._simulation_time, score=score)
        # Инференс выполняется после COMMIT завершения: 34 признака видят
        # корректные sim_end/wall_end. Модель загружается лениво и кешируется.
        from ml.error_cause_inference import FEATURE_SCHEMA_VERSION, MODEL, build_features
        features = build_features(session_store, session_id)
        if passed:
            predictions, model_status, latency_ms = [], "not_applicable_success", 0.0
        else:
            predictions, model_status, latency_ms = MODEL.predict(features)
        session_store.save_cause_prediction(
            session_id, features, predictions, MODEL.name, model_status, latency_ms,
            FEATURE_SCHEMA_VERSION,
        )
        self._ready_sessions.discard(session_id)

        return self._assessment_view(aid)

    def _apply_competencies(self, user_id: int, codes: List[str], score: float) -> None:
        for code in codes:
            if code:
                self.lms.blend_user_competency(user_id, code, score, weight=0.7)

    # ------------------------------------------------------------------
    # Assessments
    # ------------------------------------------------------------------

    def _assessment_view(self, assessment_id: int) -> Dict[str, Any]:
        a = self.store.get_assessment(assessment_id)
        if a is None:
            raise KeyError(f"Оценка '{assessment_id}' не найдена")
        uid = a.get("user_id")
        user = self.auth.user_view(uid) if uid else None
        return {
            **a,
            "username": user.username if user else "",
            "full_name": user.full_name if user else "",
            "module_title": self._module_title(int(a.get("module_id", 0) or 0)),
            "task_title": self._task_title(a.get("task_id")),
            "scenario_title": self._scenario_title(a.get("scenario_id")),
        }

    def assessments(self, username: Optional[str] = None, module_id: Optional[int] = None,
                    limit: int = 200) -> List[Dict[str, Any]]:
        user_id = self._user_id(username) if username else None
        rows = self.store.list_assessments(user_id=user_id, module_id=module_id, limit=limit)
        users = {}
        out = []
        for r in rows:
            uid = r.get("user_id")
            if uid not in users:
                u = self.auth.user_view(uid) if uid else None
                users[uid] = (u.username if u else "", u.full_name if u else "")
            uname, fname = users[uid]
            out.append({
                **r,
                "username": uname, "full_name": fname,
                "module_title": self._module_title(int(r.get("module_id", 0) or 0)),
                "task_title": self._task_title(r.get("task_id")),
                "scenario_title": self._scenario_title(r.get("scenario_id")),
            })
        return out

    def operators(self) -> List[Dict[str, Any]]:
        """Список операторов с итогами и компетенциями (для инструктора)."""
        out = []
        for u in self.auth.list_users():
            if "operator" not in (u.roles or []) and u.username != "operator":
                continue
            uid = int(u.id)
            assessments = self.store.list_assessments(user_id=uid, limit=100)
            passed = [a for a in assessments if a.get("passed")]
            avg = (sum(float(a.get("score", 0.0)) for a in passed) / len(passed)) if passed else 0.0
            comps = [{"code": c["code"], "title": c["title"],
                      "level_percent": float(c["level_percent"])}
                     for c in self.lms.get_user_competencies(uid)]
            out.append({
                "user_id": uid,
                "username": u.username,
                "full_name": u.full_name,
                "total_assessments": len(assessments),
                "passed_assessments": len(passed),
                "avg_score": round(avg, 1),
                "last_assessment": self._assessment_view(assessments[0]["id"]) if assessments else None,
                "competencies": comps,
            })
        return out

    def action_log(self, username: Optional[str] = None, object_id: Optional[str] = None,
                   session_id: Optional[str] = None, limit: int = 500) -> List[Dict[str, Any]]:
        return self.store.list_action_log(
            username=username, object_id=object_id, session_id=session_id, limit=limit)

    # ------------------------------------------------------------------
    # SCADA interaction log (клики по объектам и время в окне)
    # ------------------------------------------------------------------

    def log_scada_event(self, username: str, req: ScadaLogWrite) -> None:
        self.store.add_scada_log({
            "timestamp": _now(),
            "user_id": self._user_id(username),
            "username": username,
            "event_type": req.event_type.value,
            "object_id": req.object_id,
            "object_name": req.object_name,
            "duration_s": req.duration_s,
            "session_id": req.session_id,
            "module_id": req.module_id,
        })

    def scada_log(self, username: Optional[str] = None, object_id: Optional[str] = None,
                  event_type: Optional[str] = None, session_id: Optional[str] = None,
                  limit: int = 500) -> List[Dict[str, Any]]:
        return self.store.list_scada_log(
            username=username, object_id=object_id, event_type=event_type,
            session_id=session_id, limit=limit)

    def log_action(self, username: str, object_id: str, action: str,
                   old_state: Any = None, new_state: Any = None,
                   source: str = "operator_panel", module_id: Optional[int] = None) -> None:
        self.store.add_action_log({
            "timestamp": _now(),
            "user_id": self._user_id(username),
            "username": username,
            "object_id": object_id,
            "object_name": object_id,
            "action": action,
            "old_state": old_state,
            "new_state": new_state,
            "source": source,
            "module_id": module_id,
        })
