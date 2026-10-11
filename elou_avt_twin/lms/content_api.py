"""
lms/content_api.py
==================
REST API of the authoring & study system («Обуч.txt»).

Дерево маршрутов:

    Конструктор (инструктор, manage_courses):
        GET    /lms/authoring/modules/{id}        сводка модуля (теория/тест/задание/сценарий)
        POST   /lms/modules/{id}/publish          публикация модуля
        POST   /lms/modules/{id}/lessons          создать урок
        PUT    /lms/lessons/{id}                  изменить урок
        DELETE /lms/lessons/{id}
        PUT    /lms/modules/{id}/test             сохранить тест
        DELETE /lms/tests/{id}
        POST   /lms/tests/{id}/questions          добавить вопрос
        PUT    /lms/questions/{id}                изменить вопрос
        DELETE /lms/questions/{id}
        PUT    /lms/modules/{id}/task             сохранить практическое задание
        DELETE /lms/tasks/{id}
        PUT    /lms/modules/{id}/scenario         сохранить сценарий
        DELETE /lms/scenarios/{id}
        POST   /lms/scenarios/{id}/status         DRAFT/REVIEW/PUBLISHED/ARCHIVED
        GET    /lms/authoring/equipment           каталог оборудования схемы
        GET    /lms/authoring/scenarios           все сценарии всех модулей
        GET    /lms/authoring/scenario-status/{id}

    Оператор (view_courses / view_own_results):
        GET    /lms/modules/{id}/study            только опубликованный контент
        POST   /lms/tests/{id}/submit             ответы -> оценка
        POST   /lms/modules/{id}/practice/start   запуск практики на физическом ядре
        POST   /lms/practice/{session_id}/finish  автооценка практики
        GET    /lms/assessments                   свои результаты
        GET    /lms/assessments/{id}

    Мультиролевая практика (view_scheme):
        GET    /lms/field/errors                  ошибки поля активного сценария
        POST   /lms/chat/send                     отправить сообщение чата
        GET    /lms/chat?session_id=              история чата сессии

    Инструктор (view_analytics / view_history):
        GET    /lms/instructor/operators          список операторов и итоги
        GET    /lms/instructor/assessments        все результаты
        GET    /lms/instructor/assessments/{id}
        GET    /lms/action-log                    журнал действий оператора
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from auth.deps import get_current_user, require_permission
from auth.models import Principal
from auth.store import AuthStore

from .content_models import (
    ChatWrite,
    FieldActionComplete,
    LessonWrite,
    PracticeStartWrite,
    PublishWrite,
    QuestionWrite,
    ScenarioWrite,
    ScadaLogWrite,
    StatusWrite,
    TaskWrite,
    TestSubmit,
    TestWrite,
)
from .content_service import ContentService
from .content_store import LmsContentStore
from .chat_hub import broadcast as chat_broadcast
from .store import LmsStore
from . import runtime as lms_runtime

router = APIRouter(prefix="/lms", tags=["lms-content"])

_service: Optional[ContentService] = None


def get_service() -> ContentService:
    global _service
    if _service is None:
        _service = ContentService(
            content_store=LmsContentStore(),
            lms_store=LmsStore(),
            auth_store=AuthStore(),
        )
    return _service


def _not_found(e: Exception) -> HTTPException:
    return HTTPException(status_code=404, detail=str(e))


def _call(fn):
    try:
        return fn()
    except KeyError as e:
        raise _not_found(e)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


def _ensure_session_layer() -> None:
    """Ensure the shared training session store/recorder exists.

    IMPORTANT: must NOT `import api_server` here. When the server runs as
    `python api_server.py` the module is loaded as `__main__`, so importing
    `api_server` would execute the module a second time and create a *second*
    DigitalTwin, a second simulation loop and a second session recorder.
    The practice runs against that orphan twin while /state, SCADA and the
    WebSocket keep reading the __main__ twin -- so scenario events never show
    up and sessions finish with sim_end=0.0.
    """
    try:
        from __main__ import ensure_session_layer as _fn
    except ImportError:
        from api_server import ensure_session_layer as _fn
    _fn()


def _require_practice_chat(current_user: Principal = Depends(get_current_user)) -> Principal:
    """Чат и карточки ошибок поля доступны и консольному (view_scheme),
    и полевому (view_field_operator_screen) оператору."""
    if not (current_user.has_permission("view_scheme") or
            current_user.has_permission("view_field_operator_screen")):
        raise HTTPException(status_code=403, detail="Permission denied: practice chat")
    return current_user


def _practice_role(principal: Principal) -> Optional[str]:
    """Роль для гейтки подтверждения: только консольный/полевой оператор."""
    if "operator" in principal.roles:
        return "operator"
    if "field_operator" in principal.roles:
        return "field_operator"
    return None


# ---------------------------------------------------------------------------
# Конструктор: сводка модуля, публикация, оборудование
# ---------------------------------------------------------------------------


@router.get("/authoring/modules/{module_id}",
            dependencies=[Depends(require_permission("manage_courses"))])
def authoring_module(module_id: int, current_user: Principal = Depends(get_current_user)):
    return _call(lambda: get_service().module_authoring_view(module_id))


@router.post("/modules/{module_id}/publish",
             dependencies=[Depends(require_permission("manage_courses"))])
def publish_module(module_id: int, req: PublishWrite,
                   current_user: Principal = Depends(get_current_user)):
    return _call(lambda: get_service().publish_module(module_id, req.published))


@router.get("/authoring/equipment",
            dependencies=[Depends(require_permission("manage_courses"))])
def authoring_equipment(current_user: Principal = Depends(get_current_user)):
    return get_service().equipment_catalog()


@router.get("/authoring/scenarios",
            dependencies=[Depends(require_permission("manage_courses"))])
def authoring_scenarios(current_user: Principal = Depends(get_current_user)):
    """Все сценарии всех модулей (для администратора)."""
    return get_service().scenarios_catalog()


@router.get("/authoring/scenario-status/{scenario_id}",
            dependencies=[Depends(require_permission("manage_courses"))])
def scenario_status_flow(scenario_id: int, current_user: Principal = Depends(get_current_user)):
    return _call(lambda: get_service().scenario_status_flow(scenario_id))


# ---------------------------------------------------------------------------
# Конструктор: уроки (теория)
# ---------------------------------------------------------------------------


@router.post("/modules/{module_id}/lessons",
             dependencies=[Depends(require_permission("manage_courses"))])
def create_lesson(module_id: int, req: LessonWrite,
                  current_user: Principal = Depends(get_current_user)):
    return _call(lambda: get_service().create_lesson(module_id, req))


@router.put("/lessons/{lesson_id}",
            dependencies=[Depends(require_permission("manage_courses"))])
def update_lesson(lesson_id: int, req: LessonWrite,
                  current_user: Principal = Depends(get_current_user)):
    return _call(lambda: get_service().update_lesson(lesson_id, req))


@router.delete("/lessons/{lesson_id}",
               dependencies=[Depends(require_permission("manage_courses"))])
def delete_lesson(lesson_id: int, current_user: Principal = Depends(get_current_user)):
    get_service().delete_lesson(lesson_id)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Конструктор: тесты и вопросы
# ---------------------------------------------------------------------------


@router.put("/modules/{module_id}/test",
            dependencies=[Depends(require_permission("manage_courses"))])
def save_test(module_id: int, req: TestWrite,
              current_user: Principal = Depends(get_current_user)):
    return _call(lambda: get_service().save_test(module_id, req))


@router.delete("/tests/{test_id}",
               dependencies=[Depends(require_permission("manage_courses"))])
def delete_test(test_id: int, current_user: Principal = Depends(get_current_user)):
    get_service().delete_test(test_id)
    return {"ok": True}


@router.post("/tests/{test_id}/questions",
             dependencies=[Depends(require_permission("manage_courses"))])
def create_question(test_id: int, req: QuestionWrite,
                    current_user: Principal = Depends(get_current_user)):
    return _call(lambda: get_service().create_question(test_id, req))


@router.put("/questions/{question_id}",
            dependencies=[Depends(require_permission("manage_courses"))])
def update_question(question_id: int, req: QuestionWrite,
                    current_user: Principal = Depends(get_current_user)):
    return _call(lambda: get_service().update_question(question_id, req))


@router.delete("/questions/{question_id}",
               dependencies=[Depends(require_permission("manage_courses"))])
def delete_question(question_id: int, current_user: Principal = Depends(get_current_user)):
    get_service().delete_question(question_id)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Конструктор: практическое задание
# ---------------------------------------------------------------------------


@router.put("/modules/{module_id}/task",
            dependencies=[Depends(require_permission("manage_courses"))])
def save_task(module_id: int, req: TaskWrite,
              current_user: Principal = Depends(get_current_user)):
    return _call(lambda: get_service().save_task(module_id, req))


@router.delete("/tasks/{task_id}",
               dependencies=[Depends(require_permission("manage_courses"))])
def delete_task(task_id: int, current_user: Principal = Depends(get_current_user)):
    get_service().delete_task(task_id)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Конструктор: сценарий
# ---------------------------------------------------------------------------


@router.put("/modules/{module_id}/scenario",
            dependencies=[Depends(require_permission("manage_courses"))])
def save_scenario(module_id: int, req: ScenarioWrite,
                  current_user: Principal = Depends(get_current_user)):
    return _call(lambda: get_service().save_scenario(module_id, req))


@router.delete("/scenarios/{scenario_id}",
               dependencies=[Depends(require_permission("manage_courses"))])
def delete_scenario(scenario_id: int, current_user: Principal = Depends(get_current_user)):
    get_service().delete_scenario(scenario_id)
    return {"ok": True}


@router.post("/scenarios/{scenario_id}/status",
             dependencies=[Depends(require_permission("manage_courses"))])
def set_scenario_status(scenario_id: int, req: StatusWrite,
                        current_user: Principal = Depends(get_current_user)):
    return _call(lambda: get_service().set_scenario_status(scenario_id, req.status.value))


# ---------------------------------------------------------------------------
# Оператор: изучение модуля (только опубликованный контент)
# ---------------------------------------------------------------------------


@router.get("/modules/{module_id}/study",
            dependencies=[Depends(require_permission("view_courses"))])
def study_module(module_id: int, current_user: Principal = Depends(get_current_user)):
    return _call(lambda: get_service().study_view(module_id))


@router.get("/practice-library",
            dependencies=[Depends(require_permission("view_courses"))])
def practice_library(current_user: Principal = Depends(get_current_user)):
    """Библиотека практики оператора: сценарии опубликованных курсов."""
    return get_service().practice_catalog(current_user.username)


@router.get("/practice-library/{task_id}",
            dependencies=[Depends(require_permission("view_courses"))])
def practice_library_task(task_id: int, current_user: Principal = Depends(get_current_user)):
    task = get_service().practice_catalog_task(task_id, current_user.username)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Задание '{task_id}' не найдено")
    return task


@router.post("/tests/{test_id}/submit",
             dependencies=[Depends(require_permission("view_courses"))])
def submit_test(test_id: int, req: TestSubmit,
                current_user: Principal = Depends(get_current_user)):
    return _call(lambda: get_service().submit_test(test_id, current_user.username, req))


@router.post("/modules/{module_id}/practice/start",
             dependencies=[Depends(require_permission("start_training"))])
def start_practice(module_id: int, mode: str = Query("gated"),
                   req: Optional[PracticeStartWrite] = None,
                   current_user: Principal = Depends(get_current_user)):
    _ensure_session_layer()
    invited = (req.invited_usernames if req else None) or []
    return _call(lambda: get_service().start_practice(
        module_id, current_user.username, mode=mode,
        invited_usernames=invited))


@router.get("/practice/invite-candidates",
            dependencies=[Depends(require_permission("view_analytics"))])
def practice_invite_candidates(scenario_id: Optional[str] = Query(None),
                               current_user: Principal = Depends(get_current_user)):
    """Кандидаты на приглашение в мультиоператорную практику.

    Полевой оператор доступен только для мультиоператорного сценария."""
    return get_service().invite_candidates(scenario_id)


@router.post("/practice/{session_id}/ready",
             dependencies=[Depends(require_permission("start_training"))])
def ready_practice(session_id: str, current_user: Principal = Depends(get_current_user)):
    _ensure_session_layer()
    role = _practice_role(current_user) or "operator"
    return _call(lambda: get_service().ready_practice(session_id, current_user.username, role))


@router.post("/practice/{session_id}/confirm",
             dependencies=[Depends(_require_practice_chat)])
def confirm_practice(session_id: str, current_user: Principal = Depends(get_current_user)):
    _ensure_session_layer()
    role = _practice_role(current_user)
    if role is None:
        raise HTTPException(status_code=403, detail="Ваша роль не участвует в подтверждении практики")
    return _call(lambda: get_service().confirm_practice(session_id, current_user.username, role))


@router.post("/practice/{session_id}/decline",
             dependencies=[Depends(_require_practice_chat)])
def decline_practice(session_id: str, current_user: Principal = Depends(get_current_user)):
    _ensure_session_layer()
    role = _practice_role(current_user)
    if role is None:
        raise HTTPException(status_code=403, detail="Ваша роль не участвует в практике")
    return _call(lambda: get_service().decline_practice(session_id, current_user.username))


@router.get("/practice/current",
            dependencies=[Depends(_require_practice_chat)])
def practice_current(current_user: Principal = Depends(get_current_user)):
    _ensure_session_layer()
    return _call(lambda: get_service().current_practice())


@router.get("/practice/{session_id}/status",
            dependencies=[Depends(_require_practice_chat)])
def practice_status(session_id: str, current_user: Principal = Depends(get_current_user)):
    _ensure_session_layer()
    status = get_service().practice_status(session_id)
    if status is None:
        raise HTTPException(status_code=404, detail=f"Сессия '{session_id}' не активна")
    return status


@router.post("/practice/{session_id}/finish",
             dependencies=[Depends(require_permission("start_training"))])
def finish_practice(session_id: str, current_user: Principal = Depends(get_current_user)):
    _ensure_session_layer()
    return _call(lambda: get_service().finish_practice(session_id, current_user.username))


# ---------------------------------------------------------------------------
# Оператор: свои результаты
# ---------------------------------------------------------------------------


@router.get("/assessments", dependencies=[Depends(require_permission("view_own_results"))])
def my_assessments(limit: int = Query(100, ge=1, le=500),
                   current_user: Principal = Depends(get_current_user)):
    return get_service().assessments(username=current_user.username, limit=limit)


@router.get("/assessments/{assessment_id}",
            dependencies=[Depends(require_permission("view_own_results"))])
def assessment_detail(assessment_id: int,
                      current_user: Principal = Depends(get_current_user)):
    rows = [a for a in get_service().assessments(username=current_user.username)
            if a.get("id") == assessment_id]
    if not rows:
        raise HTTPException(status_code=404, detail=f"Оценка '{assessment_id}' не найдена")
    return rows[0]


# ---------------------------------------------------------------------------
# Инструктор: операторы, результаты, журнал действий
# ---------------------------------------------------------------------------


@router.get("/instructor/operators",
            dependencies=[Depends(require_permission("view_analytics"))])
def instructor_operators(current_user: Principal = Depends(get_current_user)):
    return get_service().operators()


@router.get("/instructor/assessments",
            dependencies=[Depends(require_permission("view_analytics"))])
def instructor_assessments(limit: int = Query(300, ge=1, le=1000),
                           current_user: Principal = Depends(get_current_user)):
    return get_service().assessments(limit=limit)


@router.get("/instructor/assessments/{assessment_id}",
            dependencies=[Depends(require_permission("view_analytics"))])
def instructor_assessment(assessment_id: int,
                          current_user: Principal = Depends(get_current_user)):
    return _call(lambda: get_service()._assessment_view(assessment_id))


@router.get("/action-log", dependencies=[Depends(require_permission("view_history"))])
def action_log(username: Optional[str] = None,
               object_id: Optional[str] = None,
               session_id: Optional[str] = None,
               limit: int = Query(500, ge=1, le=2000),
               current_user: Principal = Depends(get_current_user)):
    return get_service().action_log(username=username, object_id=object_id,
                                    session_id=session_id, limit=limit)


# ---------------------------------------------------------------------------
# SCADA: журнал кликов по объектам и время в окне
# ---------------------------------------------------------------------------


@router.post("/scada-log", dependencies=[Depends(require_permission("view_scheme"))])
def scada_log_write(req: ScadaLogWrite,
                    current_user: Principal = Depends(get_current_user)):
    get_service().log_scada_event(current_user.username, req)
    return {"ok": True}


@router.get("/scada-log", dependencies=[Depends(require_permission("view_history"))])
def scada_log(username: Optional[str] = None,
              object_id: Optional[str] = None,
              event_type: Optional[str] = None,
              session_id: Optional[str] = None,
              limit: int = Query(500, ge=1, le=5000),
              current_user: Principal = Depends(get_current_user)):
    return get_service().scada_log(username=username, object_id=object_id,
                                   event_type=event_type, session_id=session_id,
                                   limit=limit)


# ---------------------------------------------------------------------------
# Мультиролевая практика: ошибки поля + чат операторов
# ---------------------------------------------------------------------------


@router.get("/field/errors", dependencies=[Depends(_require_practice_chat)])
def field_errors(current_user: Principal = Depends(get_current_user)):
    recorder = lms_runtime.get_session_recorder()
    if recorder is None or not recorder.active:
        return {"active": False, "session_id": None, "scenario_id": None,
                "title": "", "errors": [], "status": "NO_ACTIVE"}
    session_store = lms_runtime.get_session_store()
    session = session_store.get_session(recorder.session_id) if session_store else None
    scenario_id = session.get("scenario_id") if session else None
    errors: List[Dict[str, Any]] = []
    title = ""
    multi_operator = False
    if scenario_id:
        try:
            sid = int(scenario_id.split("-", 1)[1]) if scenario_id.startswith("LMS-") else int(scenario_id)
            sc = get_service().store.get_scenario(sid)
            if sc:
                title = sc.get("title", "") or ""
                multi_operator = bool(sc.get("multi_operator"))
                # Ошибки поля показываются только в мультиоператорном режиме.
                errors = (sc.get("field_errors") or []) if multi_operator else []
        except (ValueError, TypeError):
            errors = []
            title = ""
    base = {"active": True, "session_id": recorder.session_id,
            "scenario_id": scenario_id, "title": title, "errors": errors,
            "field_actions": get_service().field_action_progress(recorder.session_id) if multi_operator else [],
            "status": "RUNNING", "multi_operator": multi_operator,
            "invited_me": False}
    try:
        cur = get_service().current_practice()
        if cur:
            base["status"] = cur.get("status")
            base["confirmed_roles"] = cur.get("confirmed_roles") or []
            base["required_roles"] = cur.get("required_roles") or []
            base["confirmed_names"] = cur.get("confirmed_names") or []
            base["timeout_seconds"] = cur.get("timeout_seconds")
            base["sim_time"] = cur.get("sim_time")
            invited = cur.get("invited_users") or []
            base["invited_me"] = current_user.username in {
                i.get("username") for i in invited if isinstance(i, dict)
            }
    except Exception:
        pass
    return base


@router.post("/field/actions/complete", dependencies=[Depends(_require_practice_chat)])
def complete_field_action(req: FieldActionComplete, current_user: Principal = Depends(get_current_user)):
    if "field_operator" not in current_user.roles:
        raise HTTPException(status_code=403, detail="Местное действие подтверждает полевой оператор")
    steps = _call(lambda: get_service().complete_field_action(
        req.session_id, current_user.username, req.object_id.strip(), req.action_type.strip(),
    ))
    return {"ok": True, "field_actions": steps}


@router.post("/chat/send", dependencies=[Depends(_require_practice_chat)])
def chat_send(req: ChatWrite, current_user: Principal = Depends(get_current_user)):
    if req.kind == "equipment_check":
        recorder = lms_runtime.get_session_recorder()
        if recorder is None or not recorder.active or recorder.session_id != req.session_id:
            raise HTTPException(status_code=409, detail="Нет активной практики для запроса")
        if "operator" not in current_user.roles:
            raise HTTPException(status_code=403, detail="Запрос проверки отправляет консольный оператор")
        session_store = lms_runtime.get_session_store()
        session = session_store.get_session(req.session_id) if session_store else None
        scenario_id = session.get("scenario_id", "") if session else ""
        try:
            sid = int(scenario_id.split("-", 1)[1]) if scenario_id.startswith("LMS-") else int(scenario_id)
            scenario = get_service().store.get_scenario(sid)
        except (TypeError, ValueError):
            scenario = None
        if not scenario or not scenario.get("multi_operator"):
            raise HTTPException(status_code=409, detail="Сценарий не является мультиоператорным")
        if not req.object_id.strip():
            raise HTTPException(status_code=422, detail="Оборудование не выбрано")
    msg = get_service().lms.add_chat_message(
        req.session_id, current_user.username, req.kind, req.object_id, req.text)
    chat_broadcast({"type": "chat_message", **msg})
    return msg


@router.get("/chat", dependencies=[Depends(_require_practice_chat)])
def chat_history(session_id: str, current_user: Principal = Depends(get_current_user)):
    return get_service().lms.list_chat_messages(session_id)
