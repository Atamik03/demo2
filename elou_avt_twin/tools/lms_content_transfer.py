"""
lms_content_transfer.py
=======================
Перенос учебного контента LMS (курсы, модули, уроки, тесты, вопросы,
практические задания и сценарии) между базами — например, из локального
`sessions.db` (SQLite) в Postgres на сервере.

Два шага:

    export  — читает SQLite и пишет JSON-файл. В файл попадает только
              контент: пользователи, пароли, сессии и журналы не выгружаются,
              поэтому JSON можно хранить в git.
    import  — читает JSON и записывает контент в целевую базу. По умолчанию
              целевая база берётся так же, как у бэкенда:
              DATABASE_URL_FILE / DATABASE_URL / локальный sessions.db.

Импорт идемпотентный: курс ищется по названию, модуль — по (курс, название),
урок — по (модуль, название), вопрос — по (тест, порядковый номер), тест,
задание и сценарий — по модулю. Найденное обновляется, недостающее
создаётся, лишнее в целевой базе не удаляется.

Run from the project root (elou_avt_twin):
    python -m tools.lms_content_transfer export [--source sessions.db] [--out lms/content_export.json]
    python -m tools.lms_content_transfer import [--file lms/content_export.json] [--target URL] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from persistence import db as _db  # noqa: E402

DEFAULT_SOURCE = ROOT / "sessions.db"
DEFAULT_FILE = ROOT / "lms" / "content_export.json"
FORMAT_VERSION = 1

# Таблицы контента и их ссылки на родителя.
CONTENT_TABLES = (
    "lms_courses", "lms_course_modules", "lms_lessons", "lms_tests",
    "lms_questions", "lms_training_tasks", "lms_scenarios",
)


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------

def _rows(conn: sqlite3.Connection, sql: str, params: Sequence[Any] = ()) -> List[Dict[str, Any]]:
    return [dict(r) for r in conn.execute(sql, tuple(params)).fetchall()]


def _has_table(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def export_content(source: Path) -> Dict[str, Any]:
    if not source.is_file():
        raise SystemExit(f"Файл базы не найден: {source}")
    conn = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        missing = [t for t in CONTENT_TABLES if not _has_table(conn, t)]
        if missing:
            raise SystemExit(f"В {source} нет таблиц: {', '.join(missing)}")

        courses = []
        for course in _rows(conn, "SELECT * FROM lms_courses ORDER BY id"):
            modules = []
            for module in _rows(conn, "SELECT * FROM lms_course_modules WHERE course_id = ? "
                                      "ORDER BY seq, id", (course["id"],)):
                mid = module["id"]
                test = next(iter(_rows(conn, "SELECT * FROM lms_tests WHERE module_id = ?", (mid,))), None)
                if test is not None:
                    test["questions"] = _rows(
                        conn, "SELECT * FROM lms_questions WHERE test_id = ? ORDER BY seq, id", (test["id"],))
                module["lessons"] = _rows(
                    conn, "SELECT * FROM lms_lessons WHERE module_id = ? ORDER BY seq, id", (mid,))
                module["test"] = test
                module["task"] = next(iter(_rows(
                    conn, "SELECT * FROM lms_training_tasks WHERE module_id = ?", (mid,))), None)
                module["scenario"] = next(iter(_rows(
                    conn, "SELECT * FROM lms_scenarios WHERE module_id = ?", (mid,))), None)
                modules.append(module)
            course["modules"] = modules
            courses.append(course)
    finally:
        conn.close()
    return {"format": "elou-lms-content", "version": FORMAT_VERSION, "courses": courses}


# ---------------------------------------------------------------------------
# import
# ---------------------------------------------------------------------------

class Importer:
    def __init__(self, conn: _db.Connection):
        self.conn = conn
        self._columns: Dict[str, set] = {}
        self.stats: Dict[str, Dict[str, int]] = {}

    def columns(self, table: str) -> set:
        if table not in self._columns:
            if self.conn.dialect == "sqlite":
                rows = self.conn.execute(f"PRAGMA table_info({table})").fetchall()  # nosec B608
                cols = {r["name"] for r in rows}
            else:
                rows = self.conn.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = current_schema() AND table_name = ?", (table,)
                ).fetchall()
                cols = {r["column_name"] for r in rows}
            if not cols:
                raise SystemExit(
                    f"В целевой базе нет таблицы {table}. Запустите бэкенд один раз, "
                    "чтобы он создал схему, и повторите импорт.")
            self._columns[table] = cols
        return self._columns[table]

    def _count(self, table: str, action: str) -> None:
        self.stats.setdefault(table, {"created": 0, "updated": 0})[action] += 1

    def upsert(self, table: str, row: Dict[str, Any], key: Dict[str, Any],
               overrides: Optional[Dict[str, Any]] = None) -> int:
        """Обновить строку, найденную по `key`, или вставить новую. Возвращает id."""
        data = {k: v for k, v in row.items()
                if k != "id" and not isinstance(v, (list, dict)) and k in self.columns(table)}
        data.update(overrides or {})
        data.update(key)

        where = " AND ".join(f"{k} = ?" for k in key)
        found = self.conn.execute(
            f"SELECT id FROM {table} WHERE {where} ORDER BY id LIMIT 1",  # nosec B608
            tuple(key.values()),
        ).fetchone()
        if found:
            sets = [k for k in data if k not in key]
            if sets:
                self.conn.execute(
                    f"UPDATE {table} SET {', '.join(f'{k} = ?' for k in sets)} WHERE id = ?",  # nosec B608
                    tuple(data[k] for k in sets) + (found["id"],),
                )
            self._count(table, "updated")
            return int(found["id"])

        cols = list(data)
        new_id = self.conn.insert_returning_id(
            f"INSERT INTO {table} ({', '.join(cols)}) "  # nosec B608
            f"VALUES ({', '.join('?' for _ in cols)})",
            tuple(data[c] for c in cols),
        )
        self._count(table, "created")
        return new_id

    def run(self, payload: Dict[str, Any]) -> None:
        for course in payload["courses"]:
            course_id = self.upsert("lms_courses", course, {"title": course["title"]})
            for module in course["modules"]:
                # practice_task_id ссылается на lms_practice_tasks, которые не
                # переносятся; scenario_id — строковый id сценария движка.
                module_id = self.upsert(
                    "lms_course_modules", module,
                    {"course_id": course_id, "title": module["title"]},
                    overrides={"practice_task_id": None},
                )
                for lesson in module.get("lessons") or []:
                    self.upsert("lms_lessons", lesson, {"module_id": module_id, "title": lesson["title"]})
                test = module.get("test")
                if test:
                    test_id = self.upsert("lms_tests", test, {"module_id": module_id})
                    for q in test.get("questions") or []:
                        self.upsert("lms_questions", q, {"test_id": test_id, "seq": q["seq"]})
                if module.get("task"):
                    self.upsert("lms_training_tasks", module["task"], {"module_id": module_id})
                if module.get("scenario"):
                    self.upsert("lms_scenarios", module["scenario"], {"module_id": module_id})


def _ensure_schema(target: Optional[str]) -> None:
    """Создать таблицы в целевой базе, если бэкенд ещё ни разу не запускался."""
    from auth.store import AuthStore
    from lms.content_store import LmsContentStore
    from lms.store import LmsStore

    for store_cls in (AuthStore, LmsStore, LmsContentStore):
        store_cls(target).close()


def import_content(file: Path, target: Optional[str], dry_run: bool) -> Dict[str, Dict[str, int]]:
    payload = json.loads(file.read_text(encoding="utf-8"))
    if payload.get("format") != "elou-lms-content":
        raise SystemExit(f"{file} не похож на выгрузку контента LMS")
    if payload.get("version") != FORMAT_VERSION:
        raise SystemExit(f"Неподдерживаемая версия выгрузки: {payload.get('version')}")

    _ensure_schema(target)
    conn = _db.connect(target, DEFAULT_SOURCE)
    print(f"Целевая база: {conn.dialect}")
    importer = Importer(conn)
    try:
        importer.run(payload)
        if dry_run:
            conn.rollback()
            print("Пробный запуск: изменения отменены.")
        else:
            conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()
    return importer.stats


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_exp = sub.add_parser("export", help="SQLite -> JSON")
    p_exp.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    p_exp.add_argument("--out", type=Path, default=DEFAULT_FILE)

    p_imp = sub.add_parser("import", help="JSON -> целевая база")
    p_imp.add_argument("--file", type=Path, default=DEFAULT_FILE)
    p_imp.add_argument("--target", default=None,
                       help="postgresql://... или путь к SQLite; по умолчанию как у бэкенда")
    p_imp.add_argument("--dry-run", action="store_true", help="проверить без записи")

    args = parser.parse_args(argv)

    if args.command == "export":
        payload = export_content(args.source)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        modules = [m for c in payload["courses"] for m in c["modules"]]
        print(f"Выгружено в {args.out}: курсов {len(payload['courses'])}, модулей {len(modules)}, "
              f"сценариев {sum(1 for m in modules if m['scenario'])}, "
              f"заданий {sum(1 for m in modules if m['task'])}")
        return 0

    stats = import_content(args.file, args.target, args.dry_run)
    for table in CONTENT_TABLES:
        s = stats.get(table, {"created": 0, "updated": 0})
        print(f"  {table:<20} создано {s['created']:>3}, обновлено {s['updated']:>3}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
