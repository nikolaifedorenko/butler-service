"""Транзакции (аудит 22.10.2026, ARCH-01): одна фиксация на запрос — в обработчике.

Сервисы (application, domain, adapters, core) готовят изменения и аудит, но не коммитят:
иначе у одного сценария commit в сервисе, у соседнего — в роутере, и запись аудита могла
оказаться в другой транзакции, чем само изменение. Обработчики (interface, *_api.py), bootstrap и
main.py коммитят. В остальном коде — только перечисленные ниже места, у каждого своя
единица работы.
"""
from __future__ import annotations

import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"

ALLOWED = {
    # advisory-lock держится на отдельном соединении — транзакцию открытой не держим
    ("core/startup_lock.py", "_pg_lock"), ("core/startup_lock.py", "try_lock"),
    # задачи планировщика (bootstrap/night_sync.py): сами себе единица работы
    ("core/media.py", "cleanup_photos"),
    ("modules/night/application/night.py", "ensure_report"),
    ("modules/night/application/night.py", "sync_reports"),
    # outbox рассылки: очередь и захват строки фиксируются ДО сети (CONC-02)
    ("modules/night/application/night_notify.py", "dispatch_defects"),
    ("modules/night/application/night_notify.py", "_queue_defects"),
    ("modules/notify/application/dispatch.py", "claim"),
    ("modules/notify/application/dispatch.py", "run_outbox"),
    ("modules/notify/application/dispatch.py", "fail_stale_sending"),
    # UnitOfWork движка (7.3): закрытие периода — своя транзакция на сотрудника
    ("modules/timesheet/adapters/sql_uow.py", "__exit__"),
}


def _commits():
    for path in sorted(APP.rglob("*.py")):
        rel = path.relative_to(APP).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for node in ast.walk(fn):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                        and node.func.attr == "commit"):
                    yield rel, fn.name, node.lineno


def test_commit_only_in_handlers_and_units_of_work():
    wrong = sorted({f"app/{rel}:{line} ({name})" for rel, name, line in _commits()
                    if "/interface/" not in f"/{rel}" and not rel.endswith("_api.py")
                    and not rel.startswith("bootstrap/")
                    and rel != "main.py" and (rel, name) not in ALLOWED})
    assert wrong == [], f"commit в сервисе — перенесите в обработчик: {wrong}"
