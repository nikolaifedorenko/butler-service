"""Слои (ADR-0013, раздел 4): транзакцией и правилами владеет прикладной слой.

Роутер разбирает запрос, проверяет право и вызывает операцию прикладного слоя. Операция
ведёт транзакцию через ``core.db.transaction`` и отказывает типизированной ошибкой
(``core.errors``); у эндпоинта есть модель ответа.

Модули переводятся на это правило по одному. ``LEGACY`` — сколько в роутерах модуля осталось
от прежнего порядка: прямых ``commit``, ``HTTPException`` и эндпоинтов без модели ответа.
Числа могут только уменьшаться: перевели часть модуля — уменьшите число, перевели весь —
удалите строку.
"""
from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"

# прямой commit вне роутеров — только здесь, у каждого места своя причина
ALLOWED = {
    # граница операции прикладного слоя
    ("core/db.py", "transaction"),
    # неудачная попытка входа записывается до отказа: отказ откатил бы и её
    ("modules/access/application/auth.py", "_record_failure"),
    # advisory-lock держится на отдельном соединении — транзакцию открытой не держим
    ("core/startup_lock.py", "_pg_lock"), ("core/startup_lock.py", "try_lock"),
    # фоновые задачи: сами себе единица работы
    ("core/media.py", "cleanup_photos"),
    ("modules/night/application/night.py", "ensure_report"),
    ("modules/night/application/night.py", "sync_reports"),
    # очередь рассылки: строка фиксируется до обращения к сети
    ("modules/night/application/night_notify.py", "dispatch_defects"),
    ("modules/night/application/night_notify.py", "_queue_defects"),
    ("modules/notify/application/dispatch.py", "claim"),
    ("modules/notify/application/dispatch.py", "run_outbox"),
    ("modules/notify/application/dispatch.py", "fail_stale_sending"),
    # закрытие периода — своя транзакция на сотрудника
    ("modules/timesheet/adapters/sql_uow.py", "__exit__"),
}

# модуль → (commit, HTTPException, эндпоинты без модели ответа) в его роутерах
LEGACY: dict[str, tuple[int, int, int]] = {
    "stays": (18, 50, 96),
    "timesheet": (30, 89, 51),
}

HTTP_METHODS = {"get", "post", "put", "patch", "delete"}


def _is_router(rel: str) -> bool:
    return "/interface/" in f"/{rel}" or rel.endswith("_api.py")


def _owner(rel: str) -> str:
    parts = rel.split("/")
    return parts[1] if parts[0] == "modules" else parts[0]


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


def _legacy() -> dict[str, tuple[int, int, int]]:
    commits, raises, bare = Counter(), Counter(), Counter()
    for path in sorted(APP.rglob("*.py")):
        rel = path.relative_to(APP).as_posix()
        if not _is_router(rel):
            continue
        owner = _owner(rel)
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute) and node.func.attr == "commit":
                    commits[owner] += 1
                if isinstance(node.func, ast.Name) and node.func.id == "HTTPException":
                    raises[owner] += 1
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for dec in node.decorator_list:
                    if (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)
                            and dec.func.attr in HTTP_METHODS
                            and not {"response_model", "response_class"} & {k.arg for k in dec.keywords}):
                        bare[owner] += 1
    owners = sorted(set(commits) | set(raises) | set(bare))
    return {o: (commits[o], raises[o], bare[o]) for o in owners}


def test_commit_outside_routers_only_through_transaction():
    wrong = sorted({f"app/{rel}:{line} ({name})" for rel, name, line in _commits()
                    if not _is_router(rel) and not rel.startswith("bootstrap/")
                    and rel != "main.py" and (rel, name) not in ALLOWED})
    assert wrong == [], f"прямой commit — оберните операцию в core.db.transaction: {wrong}"


def test_routers_do_not_gain_rules_and_transactions():
    actual = _legacy()
    grown = {o: (LEGACY.get(o, (0, 0, 0)), now) for o, now in actual.items()
             if any(a > b for a, b in zip(now, LEGACY.get(o, (0, 0, 0)), strict=True))}
    assert grown == {}, ("в роутерах прибавилось commit / HTTPException / эндпоинтов без модели ответа "
                         f"(модуль: было, стало): {grown}")
    stale = {o: (was, actual.get(o, (0, 0, 0))) for o, was in LEGACY.items() if actual.get(o, (0, 0, 0)) != was}
    assert stale == {}, f"роутеры стали чище — уменьшите числа в LEGACY (модуль: записано, сейчас): {stale}"
