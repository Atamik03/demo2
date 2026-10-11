"""Additional practice-task cards for the ORBITA task-library tab.

The library contains launchable assignments.  Each card deliberately points
to an existing authored scenario instead of duplicating process logic.
"""

from __future__ import annotations

from typing import Any, Dict, List

from .content_store import LmsContentStore
from .models import Difficulty, TaskCreate, TaskUpdate
from .store import LmsStore


TASKS: List[Dict[str, Any]] = [
    {
        "title": "Компенсация отказа FRC 458",
        "description": "Сохранить подачу в К-1 двумя исправными регуляторами FRC 459 и FRC 460.",
        "scenario_title": "01. Отказ FRC 458",
        "difficulty": Difficulty.EASY,
        "duration_min": 8,
        "competencies": ["emergency", "column"],
    },
    {
        "title": "Работа К-1 при двух отказах подачи",
        "description": "Ограничить отбор и удержать безопасный уровень К-1 при отказе двух FRC.",
        "scenario_title": "02. Отказ двух FRC подачи К-1",
        "difficulty": Difficulty.HARD,
        "duration_min": 12,
        "competencies": ["emergency", "column"],
    },
    {
        "title": "Снижение высокого уровня К-1",
        "description": "Управлять притоком и отбором для безопасного снижения уровня куба К-1.",
        "scenario_title": "03. Высокий уровень К-1",
        "difficulty": Difficulty.MIDDLE,
        "duration_min": 8,
        "competencies": ["column", "emergency"],
    },
    {
        "title": "Восстановление уровня К-1",
        "description": "Восстановить уровень колонны ограничением отбора и увеличением подачи.",
        "scenario_title": "04. Низкий уровень К-1",
        "difficulty": Difficulty.MIDDLE,
        "duration_min": 8,
        "competencies": ["column"],
    },
    {
        "title": "Снижение тепловой нагрузки П-1",
        "description": "Распознать перегрев и снизить расход топлива трубчатой печи П-1.",
        "scenario_title": "05. Сигнал перегрева печи П-1",
        "difficulty": Difficulty.EASY,
        "duration_min": 6,
        "competencies": ["emergency"],
    },
    {
        "title": "Действия при снижении эффективности Т-17",
        "description": "Ограничить поток через Т-17 и проконтролировать температурный режим.",
        "scenario_title": "06. Потеря эффективности Т-17",
        "difficulty": Difficulty.MIDDLE,
        "duration_min": 8,
        "competencies": ["emergency"],
    },
    {
        "title": "Полевой осмотр Н-20А при кавитации",
        "description": "Отработать осмотр Н-20А, проверку всасывания и передачу результата АРМ.",
        "scenario_title": "07. Кавитация Н-20А",
        "difficulty": Difficulty.EASY,
        "duration_min": 6,
        "competencies": ["pumps", "emergency"],
    },
    {
        "title": "Совместное устранение роста уровня Е-1",
        "description": "Согласовать действия АРМ и поля при росте уровня в ёмкости Е-1.",
        "scenario_title": "14. Высокий уровень Е-1",
        "difficulty": Difficulty.MIDDLE,
        "duration_min": 10,
        "competencies": ["emergency", "column"],
    },
    {
        "title": "Совместное восстановление уровня К-1",
        "description": "Отработать взаимодействие АРМ и полевого оператора при падении уровня К-1.",
        "scenario_title": "16. Падение уровня К-1",
        "difficulty": Difficulty.HARD,
        "duration_min": 12,
        "competencies": ["column", "emergency"],
    },
    {
        "title": "Проверка газового отвода Е-15",
        "description": "Снизить нагрузку К-1 и подтвердить состояние газового отвода Е-15.",
        "scenario_title": "20. Рост давления К-1",
        "difficulty": Difficulty.HARD,
        "duration_min": 10,
        "competencies": ["column", "emergency"],
    },
]


def seed_task_library() -> int:
    content = LmsContentStore()
    lms = LmsStore()
    scenarios = {str(s.get("title")): s for s in content.list_scenarios()}
    existing = {str(t.get("title")): t for t in lms.list_tasks()}
    created = 0
    for item in TASKS:
        scenario = scenarios.get(item["scenario_title"])
        if scenario is None:
            raise ValueError(f"Не найден сценарий «{item['scenario_title']}» для задания «{item['title']}»")
        payload = TaskCreate(
            title=item["title"],
            description=item["description"],
            scenario_id=f"LMS-{scenario['id']}",
            category="practice",
            difficulty=item["difficulty"],
            duration_min=item["duration_min"],
            required_competencies=item["competencies"],
            is_random=False,
            enabled=True,
        )
        old = existing.get(item["title"])
        if old is None:
            lms.create_task(payload)
            created += 1
        else:
            lms.update_task(int(old["id"]), TaskUpdate(
                description=payload.description,
                scenario_id=payload.scenario_id,
                category=payload.category,
                difficulty=payload.difficulty,
                duration_min=payload.duration_min,
                required_competencies=payload.required_competencies,
                is_random=False,
                enabled=True,
            ))
    return created


if __name__ == "__main__":
    print(f"ORBITA practice tasks created: {seed_task_library()}")
