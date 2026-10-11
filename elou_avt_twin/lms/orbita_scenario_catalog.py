"""Idempotent catalogue of ORBITA practice scenarios.

The scenarios deliberately use the current process scheme's identifiers.  They
cover the atmospheric block and crude-oil preheat in three formats: ARM-only,
field-only and joint ARM/field practice.

Run with: ``python -m lms.orbita_scenario_catalog``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Set

from .content_models import (
    ExpectedAction, FieldErrorDef, ScenarioEventDef, ScenarioWrite, TaskWrite,
)
from .content_store import LmsContentStore
from .models import ModuleCreate, ModuleKind
from .store import LmsStore


COURSE_TITLE = "ORBITA · аварийные тренировки: атмосферный блок и подогрев"

# Названия первых версий каталога, которые содержали невыполнимые требования
# о резерве. При повторной загрузке удаляем только эти служебные модули: новые
# версии уже имеют другие названия и сохраняются под своими идентификаторами.
LEGACY_REPLACED_TITLES = {
    "05. Перегрев печи П-1",
    "13. Отказ Н-20А: переход на резерв",
    "18. Перегрев П-1",
}

# Только позиции, которые сейчас действительно доступны оператору на АРМ.
# Резервный насос не включается в сценарий лишь потому, что он существует на
# технологической схеме: для упражнения он должен быть отдельным управляемым
# объектом в открытой мнемосхеме.
ARM_CONTROLLED_IDS: Set[str] = {
    "val_44", "val_45", "val_46", "val_52", "val_159", "hea_66",
}

# Метки реальных объектов текущей 3D-модели полевого оператора.
FIELD_VISIBLE_TAGS: Set[str] = {"Н-20", "К-1", "Е-1", "Т-17", "П-1", "Е-15"}


def arm(seq: int, object_id: str, action: str, description: str) -> ExpectedAction:
    return ExpectedAction(seq=seq, actor="operator", object_id=object_id,
                          action_type=action, description=description)


def field(seq: int, tag: str, action: str, description: str) -> ExpectedAction:
    return ExpectedAction(seq=seq, actor="field_operator", object_id=tag,
                          action_type=action, description=description)


def fault(time_s: int, object_id: str, mode: str, message: str) -> ScenarioEventDef:
    return ScenarioEventDef(time=time_s, event_type="fault", object_id=object_id,
                            value=mode, severity="HIGH", message=message)


def alarm(time_s: int, object_id: str, message: str) -> ScenarioEventDef:
    return ScenarioEventDef(time=time_s, event_type="alarm", object_id=object_id,
                            value=1.0, severity="HIGH", message=message)


def item(title: str, description: str, goal: str, actions: List[ExpectedAction],
         events: List[ScenarioEventDef], *, multi: bool = False,
         field_tag: str = "", equipment: List[str] | None = None) -> Dict[str, Any]:
    return {
        "title": title,
        "description": description,
        "goal": goal,
        "actions": actions,
        "events": events,
        "multi": multi,
        "field_errors": ([FieldErrorDef(
            object_id=field_tag,
            title="Задание полевому оператору",
            description=description,
            severity="warning",
        )] if field_tag else []),
        "equipment": equipment or [],
    }


# All tags/ids below exist in schemes/default.json.  Field tags are the tags
# rendered by the 3D model; machine ids are used for commands in ARM.
CATALOG: List[Dict[str, Any]] = [
    # ARM-only -------------------------------------------------------------
    item("01. Отказ FRC 458", "Отказ регулятора первого потока подачи в К-1.",
         "Сохранить питание К-1 исправными потоками.",
         [arm(1, "val_45", "INCREASE_PARAM", "Увеличить FRC 459"),
          arm(2, "val_46", "INCREASE_PARAM", "Увеличить FRC 460")],
         [fault(10, "val_44", "MECHANICAL_FAILURE", "Отказ FRC 458")], equipment=["val_44", "val_45", "val_46", "col_32"]),
    item("02. Отказ двух FRC подачи К-1", "Недоступны FRC 458 и FRC 459.",
         "Ограничить нагрузку и сохранить безопасный уровень К-1.",
         [arm(1, "val_46", "INCREASE_PARAM", "Увеличить подачу через FRC 460"),
          arm(2, "val_52", "DECREASE_PARAM", "Ограничить регулируемый отбор")],
         [fault(10, "val_44", "MECHANICAL_FAILURE", "Отказ FRC 458"),
          fault(10, "val_45", "MECHANICAL_FAILURE", "Отказ FRC 459")], equipment=["val_44", "val_45", "val_46", "val_52", "col_32"]),
    item("03. Высокий уровень К-1", "Аварийный рост уровня внизу колонны К-1.",
         "Снизить уровень без потери управляемости колонны.",
         [arm(1, "val_52", "INCREASE_PARAM", "Увеличить отбор из К-1"),
          arm(2, "val_44", "DECREASE_PARAM", "Ограничить первый поток подачи")],
         [alarm(10, "col_32", "Высокий уровень К-1")], equipment=["col_32", "val_52", "val_44"]),
    item("04. Низкий уровень К-1", "Уровень внизу К-1 снижается.",
         "Восстановить уровень, не допуская переполнения.",
         [arm(1, "val_52", "DECREASE_PARAM", "Прикрыть отбор из К-1"),
          arm(2, "val_44", "INCREASE_PARAM", "Увеличить подачу в К-1")],
         [alarm(10, "col_32", "Низкий уровень К-1")], equipment=["col_32", "val_52", "val_44"]),
    item("05. Сигнал перегрева печи П-1", "Температура выходного потока П-1 растёт выше нормы.",
         "Снизить тепловую нагрузку печи.",
         [arm(1, "hea_66", "DECREASE_PARAM", "Снизить подачу топлива П-1")],
         # Это именно тревога, а не отказ печи: иначе подача топлива уже
         # заблокирована, и требовать её снижения от оператора невозможно.
         [alarm(10, "hea_66", "Перегрев П-1")], equipment=["hea_66"]),
    item("06. Потеря эффективности Т-17", "Снижение теплопередачи в группе Т-17.",
         "Сохранить допустимый режим подачи сырья.",
         [arm(1, "val_44", "DECREASE_PARAM", "Ограничить поток через Т-17")],
         [fault(10, "hea_33", "MECHANICAL_FAILURE", "Потеря эффективности Т-17")], equipment=["hea_33", "val_44"]),

    # Field-only -----------------------------------------------------------
    item("07. Кавитация Н-20А", "На Н-20А признаки кавитации.", "Подтвердить осмотр и местную проверку.",
         [field(1, "Н-20", "FIELD_INSPECT", "Осмотреть Н-20А"),
          field(2, "Н-20", "FIELD_CONFIRM_LOCAL", "Проверить всасывающую арматуру"),
          field(3, "Н-20", "FIELD_CONFIRM_RESULT", "Передать результат осмотра")],
         [fault(10, "pum_176", "CAVITATION", "Кавитация Н-20А")], multi=True, field_tag="Н-20", equipment=["pum_176"]),
    item("08. Останов Н-20А", "Рабочий насос Н-20А остановился.", "Подтвердить останов и передать результат осмотра.",
         [field(1, "Н-20", "FIELD_INSPECT", "Подтвердить останов Н-20А"),
          field(2, "Н-20", "FIELD_CONFIRM_LOCAL", "Проверить отсутствие утечки и вибрации"),
          field(3, "Н-20", "FIELD_CONFIRM_RESULT", "Передать результат осмотра")],
         [fault(10, "pum_176", "MECHANICAL_FAILURE", "Останов Н-20А")], multi=True, field_tag="Н-20", equipment=["pum_176"]),
    item("09. Закрыта ручная арматура подачи К-1", "На первом потоке К-1 обнаружено местное ограничение подачи.", "Подтвердить состояние арматуры.",
         [field(1, "К-1", "FIELD_INSPECT", "Осмотреть линию подачи К-1"),
          field(2, "К-1", "FIELD_CONFIRM_LOCAL", "Проверить положение ручной арматуры"),
          field(3, "К-1", "FIELD_CONFIRM_RESULT", "Подтвердить результат")],
         [fault(10, "val_44", "MECHANICAL_FAILURE", "Ограничение подачи через FRC 458")], multi=True, field_tag="К-1", equipment=["val_44", "col_32"]),
    item("10. Проверка уровня Е-1", "Требуется сверка показания уровня Е-1 по месту.", "Передать фактический результат осмотра.",
         [field(1, "Е-1", "FIELD_INSPECT", "Осмотреть Е-1"),
          field(2, "Е-1", "FIELD_CONFIRM_LOCAL", "Проверить местный уровнемер"),
          field(3, "Е-1", "FIELD_CONFIRM_RESULT", "Подтвердить показание")],
         [alarm(10, "tan_2", "Расхождение показаний уровня Е-1")], multi=True, field_tag="Е-1", equipment=["tan_2"]),
    item("11. Осмотр Т-17", "Падение температуры после Т-17.", "Проверить местную арматуру и состояние теплообменника.",
         [field(1, "Т-17", "FIELD_INSPECT", "Осмотреть Т-17"),
          field(2, "Т-17", "FIELD_CONFIRM_LOCAL", "Проверить арматуру"),
          field(3, "Т-17", "FIELD_CONFIRM_RESULT", "Передать результат")],
         [fault(10, "hea_33", "MECHANICAL_FAILURE", "Потеря эффективности Т-17")], multi=True, field_tag="Т-17", equipment=["hea_33"]),
    item("12. Останов П-1 по ПАЗ", "П-1 остановлена защитой.", "Подтвердить безопасное состояние печи по месту.",
         [field(1, "П-1", "FIELD_INSPECT", "Осмотреть П-1 с безопасной дистанции"),
          field(2, "П-1", "FIELD_CONFIRM_LOCAL", "Проверить отсечку топлива"),
          field(3, "П-1", "FIELD_CONFIRM_RESULT", "Подтвердить отсутствие пламени")],
         [fault(10, "hea_66", "MECHANICAL_FAILURE", "Останов П-1 по ПАЗ")], multi=True, field_tag="П-1", equipment=["hea_66"]),

    # Joint ARM + field ----------------------------------------------------
    item("13. Отказ Н-20А: ограничение нагрузки", "Н-20А отказал, резервное включение на текущем АРМ не выведено.", "Ограничить подачу и подтвердить состояние насоса по месту.",
         [field(1, "Н-20", "FIELD_INSPECT", "Подтвердить останов Н-20А"),
          arm(2, "val_44", "DECREASE_PARAM", "Ограничить подачу сырья"),
          field(3, "Н-20", "FIELD_CONFIRM_RESULT", "Доложить о безопасном состоянии Н-20А")],
         [fault(10, "pum_176", "MECHANICAL_FAILURE", "Отказ Н-20А")], multi=True, field_tag="Н-20", equipment=["pum_176", "val_44"]),
    item("14. Высокий уровень Е-1", "Уровень Е-1 растёт, требуется отвод воды.", "Снизить уровень и подтвердить состояние дренажа.",
         [field(1, "Е-1", "FIELD_INSPECT", "Осмотреть Е-1"),
          arm(2, "val_159", "INCREASE_PARAM", "Увеличить слив воды из Е-1"),
          field(3, "Е-1", "FIELD_CONFIRM_RESULT", "Подтвердить работу дренажа")],
         [alarm(10, "tan_2", "Высокий уровень Е-1")], multi=True, field_tag="Е-1", equipment=["tan_2", "val_159"]),
    item("15. Рост уровня К-1", "Уровень К-1 повышается.", "Согласованно увеличить отбор и проверить линию по месту.",
         [field(1, "К-1", "FIELD_INSPECT", "Осмотреть линию отбора К-1"),
          arm(2, "val_52", "INCREASE_PARAM", "Увеличить отбор из К-1"),
          field(3, "К-1", "FIELD_CONFIRM_RESULT", "Подтвердить состояние линии отбора")],
         [alarm(10, "col_32", "Высокий уровень К-1")], multi=True, field_tag="К-1", equipment=["col_32", "val_52"]),
    item("16. Падение уровня К-1", "Уровень К-1 снижается.", "Ограничить отбор и проверить подачу по месту.",
         [field(1, "К-1", "FIELD_INSPECT", "Осмотреть подачу в К-1"),
          arm(2, "val_52", "DECREASE_PARAM", "Прикрыть отбор из К-1"),
          arm(3, "val_46", "INCREASE_PARAM", "Увеличить доступную подачу"),
          field(4, "К-1", "FIELD_CONFIRM_RESULT", "Подтвердить восстановление подачи")],
         [alarm(10, "col_32", "Низкий уровень К-1")], multi=True, field_tag="К-1", equipment=["col_32", "val_52", "val_46"]),
    item("17. Потеря орошения К-1", "Нарушена циркуляция орошения К-1.", "Подтвердить насос и ограничить нагрузку по указанию АРМ.",
         [field(1, "К-1", "FIELD_INSPECT", "Осмотреть контур орошения К-1"),
          arm(2, "val_44", "DECREASE_PARAM", "Снизить подачу сырья"),
          field(3, "К-1", "FIELD_CONFIRM_RESULT", "Подтвердить состояние контура")],
         [fault(10, "pum_163", "MECHANICAL_FAILURE", "Потеря циркуляции орошения")], multi=True, field_tag="К-1", equipment=["pum_163", "val_44", "col_32"]),
    item("18. Сигнал перегрева П-1", "П-1 перегревается.", "Снизить тепловую нагрузку и подтвердить состояние печи.",
         [field(1, "П-1", "FIELD_INSPECT", "Осмотреть П-1"),
          arm(2, "hea_66", "DECREASE_PARAM", "Снизить подачу топлива"),
          field(3, "П-1", "FIELD_CONFIRM_RESULT", "Подтвердить безопасный режим П-1")],
         [alarm(10, "hea_66", "Перегрев П-1")], multi=True, field_tag="П-1", equipment=["hea_66"]),
    item("19. Загрязнение Т-17", "Перепад температуры Т-17 указывает на загрязнение.", "Ограничить поток и подтвердить осмотр аппарата.",
         [field(1, "Т-17", "FIELD_INSPECT", "Осмотреть Т-17"),
          arm(2, "val_44", "DECREASE_PARAM", "Снизить поток через Т-17"),
          field(3, "Т-17", "FIELD_CONFIRM_RESULT", "Подтвердить готовность к выводу")],
         [fault(10, "hea_33", "MECHANICAL_FAILURE", "Загрязнение Т-17")], multi=True, field_tag="Т-17", equipment=["hea_33", "val_44"]),
    item("20. Рост давления К-1", "Рост давления в К-1, требуется проверить газовый отвод Е-15.", "Снизить нагрузку и подтвердить состояние газового отвода.",
         [field(1, "Е-15", "FIELD_INSPECT", "Осмотреть газовый отвод Е-15"),
          arm(2, "val_44", "DECREASE_PARAM", "Снизить подачу в К-1"),
          field(3, "Е-15", "FIELD_CONFIRM_RESULT", "Подтвердить состояние газового отвода")],
         [alarm(10, "col_32", "Рост давления К-1")], multi=True, field_tag="Е-15", equipment=["col_32", "tan_1", "val_44"]),
]


def validate_catalog(catalog: List[Dict[str, Any]] = CATALOG) -> None:
    """Fail fast if a training step cannot be completed in the current UI."""
    scheme_path = Path(__file__).resolve().parents[1] / "schemes" / "default.json"
    scheme_nodes = {
        node["id"] for node in json.loads(scheme_path.read_text(encoding="utf-8")).get("nodes", [])
    }
    problems: List[str] = []
    for scenario in catalog:
        title = scenario["title"]
        for equipment_id in scenario["equipment"]:
            if equipment_id not in scheme_nodes:
                problems.append(f"{title}: отсутствует объект схемы {equipment_id}")
        for event in scenario["events"]:
            if event.object_id not in scheme_nodes:
                problems.append(f"{title}: событие ссылается на отсутствующий объект {event.object_id}")
        expected = sorted(scenario["actions"], key=lambda action: action.seq)
        if [action.seq for action in expected] != list(range(1, len(expected) + 1)):
            problems.append(f"{title}: нарушена нумерация действий")
        for action in expected:
            if action.actor == "field_operator":
                if action.object_id not in FIELD_VISIBLE_TAGS:
                    problems.append(f"{title}: {action.object_id} отсутствует на экране полевого оператора")
            elif action.object_id not in ARM_CONTROLLED_IDS:
                problems.append(f"{title}: {action.object_id} недоступен для управления на АРМ")
    if problems:
        raise ValueError("Некорректный каталог ORBITA:\n- " + "\n- ".join(problems))


def seed_catalog() -> int:
    validate_catalog()
    db = LmsStore()
    store = LmsContentStore()
    course = next((c for c in db.list_courses() if c.get("title") == COURSE_TITLE), None)
    course_id = int(course["id"]) if course else db.create_course(
        COURSE_TITLE,
        "20 практических сценариев для АРМ и полевого оператора.",
        status="ACTIVE",
    )
    db.update_course(course_id, {"status": "ACTIVE"})
    # Ранний запуск каталога создал три старые версии рядом с новыми, потому
    # что ключом модуля было его название. Они не должны оставаться доступны
    # учащемуся как альтернативные, невыполнимые упражнения.
    for module in db.get_modules(course_id):
        if module["title"] in LEGACY_REPLACED_TITLES:
            db.remove_module(int(module["id"]))
    modules = {m["title"]: m for m in db.get_modules(course_id)}
    for index, data in enumerate(CATALOG):
        module = modules.get(data["title"])
        if module is None:
            module_id = db.add_module(course_id, ModuleCreate(
                kind=ModuleKind.PRACTICE, title=data["title"], description=data["description"],
            ), seq=index)
        else:
            module_id = int(module["id"])
        task = TaskWrite(
            title=data["title"], goal=data["goal"], duration_min=10,
            expected_actions=data["actions"], equipment_ids=data["equipment"],
            competency_codes=["emergency", "pumps", "column"],
        )
        store.upsert_task(module_id, task)
        scenario = ScenarioWrite(
            title=data["title"], description=data["description"], goal=data["goal"],
            events=data["events"], expected_actions=data["actions"],
            field_errors=data["field_errors"], multi_operator=bool(data["multi"]),
            equipment_ids=data["equipment"], competency_codes=["emergency", "pumps", "column"],
            duration_min=10,
        )
        scenario_id = store.upsert_scenario(module_id, scenario)
        store.set_scenario_status(scenario_id, "PUBLISHED")
        store.set_module_published(module_id, True)
    return len(CATALOG)


if __name__ == "__main__":
    print(f"ORBITA scenarios seeded: {seed_catalog()}")
