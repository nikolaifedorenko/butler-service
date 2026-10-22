"""Стражи находок P0 внешнего ревью от 20.10.2026 (REVIEW-2026-10-20).

Каждая группа закрепляет один фикс, чтобы находка не вернулась:

* **P0-2** — инициализация схемы сериализована замком (`core.startup_lock`): прод-профиль
  поднимает 2 воркера uvicorn, а DDL-шаги и `sync_reports(force=True)` при одновременном
  старте давали «duplicate column name» и IntegrityError по `night_reports.date`;
* **P0-3** — массовые операции (bulk / range-absence / copy) перегенерируют График одним
  проходом на затронутый месяц, а не на каждую ячейку;
* **P0-4** — заглушки `recalc_double_rows` и поля `recalculated` в ответах больше нет:
  движок v7.1 считает УТ при чтении, пересчитывать нечего (контракт не врёт);
* **P0-5** — `year`/`month` проверяются во ВСЕХ точках ввода периода: `month=13` — это 422
  с человеческим текстом, а не 500 из `calendar.monthrange`.

P0-1 (демо-пароль на пустой базе) закрыт организационно решением владельца от 20.10.2026:
боевая база разворачивается без демо-данных.
"""
from __future__ import annotations

import ast
import contextlib
import datetime as dt
import os
import pathlib
import subprocess
import sys
import time

import pytest

from app.core.time import local_date
from app.modules.timesheet.interface.period_params import PERIOD_DETAIL

BASE = pathlib.Path(__file__).resolve().parent.parent
TODAY = local_date()
MONTH_FIRST = TODAY.replace(day=1)

# сколько DELETE FROM schedule_shifts допустимо на одну массовку: одна перегенерация
# на затронутый месяц (P0-3). Раньше было по одной на каждую ячейку.
REBUILD_DELETES_PER_MONTH = 1


def _month_days(count: int) -> list[str]:
    return [(MONTH_FIRST + dt.timedelta(days=i)).isoformat() for i in range(count)]


def _rebuild_deletes(counter: dict) -> int:
    """Число DELETE по generated/manual-сменам = число вызовов перегенерации Графика."""
    return sum(n for k, n in counter["by_statement"].items()
               if k.startswith("DELETE FROM schedule_shifts"))


@pytest.fixture()
def fresh_employee(admin_client):
    """Сотрудник, принятый 1-го числа текущего месяца (период открыт, трудоустроен весь месяц).

    После теста — мягкое удаление: история остаётся, а из списков и сетки Графика
    сотрудник исчезает и не мешает соседним тестам прогона (база общая, session-scope).
    """
    r = admin_client.post("/api/employees", json={
        "full_name": "Пакетов Пакет Пакетович", "position": "Батлер (тест P0-3)",
        "hired_at": MONTH_FIRST.isoformat(), "schedule_group": "Смена 1"})
    assert r.status_code == 200, r.text
    emp = r.json()
    try:
        yield emp
    finally:
        admin_client.post(f"/api/employees/{emp['id']}/delete")


# ── P0-5: year/month валидируются везде (422 вместо 500) ───────────────────────

# (id, метод, путь, payload) — все точки ввода периода, где year/month приходят от клиента
_PERIOD_CASES = [
    ("grid", "get", "/api/schedule", {"year": 2026, "month": 13}),
    ("grid-m0", "get", "/api/schedule", {"year": 2026, "month": 0}),
    ("tabel", "get", "/api/tabel", {"year": 0, "month": 5}),
    ("mgmt", "get", "/api/mgmt", {"year": 2026, "month": 13}),
    ("fact", "get", "/api/fact/month", {"year": 2026, "month": 13}),
    ("modifiers", "get", "/api/engine-settings/modifiers", {"year": 2026, "month": 13}),
    ("reset-month", "post", "/api/schedule/reset-month", {"year": 2026, "month": 13}),
    ("fill", "post", "/api/tabel/fill-from-cycles", {"year": 2026, "month": 13}),
    ("tabel-reset", "post", "/api/tabel/reset", {"year": 2026, "month": 13}),
    ("close", "post", "/api/mgmt/close", {"year": 2026, "month": 13}),
    ("recalculate", "post", "/api/mgmt/recalculate", {"year": 2026, "month": 13}),
]


@pytest.mark.parametrize("case_id,method,path,payload", _PERIOD_CASES,
                         ids=[c[0] for c in _PERIOD_CASES])
def test_bad_period_is_422_not_500(admin_client, case_id, method, path, payload):
    """Невалидный период — ошибка ввода клиента (422), а не Internal Server Error.

    До фикса `month=13` в continue/copy/clear-month/fill/reset/modifiers долетал до
    `calendar.monthrange`/`dt.date(...)` → ValueError/IllegalMonthError → 500, а в
    mgmt close/recalculate маскировался под 409 «повреждённая конфигурация».
    """
    r = (admin_client.get(path, params=payload) if method == "get"
         else admin_client.post(path, json=payload))
    assert r.status_code == 422, f"{method.upper()} {path} {payload} → {r.status_code}: {r.text[:200]}"
    assert r.json()["detail"] == PERIOD_DETAIL


def test_valid_period_still_works(admin_client):
    """Единая проверка не отбраковывает валидный период (регресс на ложные срабатывания)."""
    r = admin_client.get("/api/schedule", params={"year": TODAY.year, "month": TODAY.month})
    assert r.status_code == 200, r.text


def test_ensure_period_shared_by_all_period_endpoints():
    """Все точки ввода периода ходят через один помощник, а не копируют проверку текстом."""
    from app.modules.timesheet.interface import engine_settings_api, fact_api, mgmt_api, schedule, tabel_api

    for mod in (engine_settings_api, fact_api, mgmt_api, schedule, tabel_api):
        src = pathlib.Path(mod.__file__).read_text(encoding="utf-8")
        assert "ensure_period(" in src, f"{mod.__name__}: нет вызова ensure_period"
        assert "1 <= month <= 12" not in src, f"{mod.__name__}: проверка скопирована текстом"


# ── P0-4: recalc_double_rows / recalculated удалены ───────────────────────────

def test_recalc_double_rows_stub_is_gone():
    from app.modules.timesheet.application import doublepay as app_doublepay

    assert not hasattr(app_doublepay, "recalc_double_rows"), \
        "заглушка recalc_double_rows вернулась: она всегда возвращала 0 и ничего не пересчитывала"


def test_doublepay_responses_have_no_recalculated(admin_client):
    """Ответы календаря двойной оплаты не обещают пересчёт, которого не существует."""
    day = "2031-05-17"          # далеко за пределами периодов прогона — никому не мешает
    r = admin_client.post("/api/doublepay/days", json={"dates": day, "scope": "all",
                                                       "note": "тест P0-4"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["added"] == 1
    assert "recalculated" not in body, body
    day_id = next(d["id"] for d in body["days"] if d["date"] == day)
    r = admin_client.delete(f"/api/doublepay/days/{day_id}")     # убираем за собой
    assert r.status_code == 200, r.text
    assert "recalculated" not in r.json(), r.json()


def test_doublepay_source_and_frontend_have_no_recalculated():
    """Ни роутер, ни интерфейс не упоминают `recalculated` (иначе в тосте — undefined)."""
    router = (BASE / "app/modules/timesheet/interface/doublepay.py").read_text(encoding="utf-8")
    assert '"recalculated"' not in router
    js = (BASE / "static/js/modules/dicts.js").read_text(encoding="utf-8")
    assert "recalculated" not in js


# ── P0-3: массовки перегенерируют График пакетно ──────────────────────────────

@pytest.mark.parametrize("days", [4, 12])
def test_bulk_regeneration_does_not_scale_with_cells(admin_client, fresh_employee, sql_counter, days):
    """`POST /api/tabel/bulk`: одна перегенерация Графика на месяц, а не на ячейку."""
    with sql_counter() as c:
        r = admin_client.post("/api/tabel/bulk", json={
            "employee_ids": [fresh_employee["id"]], "dates": _month_days(days), "code": "В"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["errors"] == [], body["errors"]
    assert body["cells"] == days
    assert _rebuild_deletes(c) == REBUILD_DELETES_PER_MONTH, (
        f"на {days} ячеек пришлось {_rebuild_deletes(c)} перегенераций Графика "
        f"(ожидалась {REBUILD_DELETES_PER_MONTH} на месяц); топ запросов: "
        f"{sorted(c['by_statement'].items(), key=lambda x: -x[1])[:3]}")


def test_bulk_still_regenerates_schedule(admin_client, fresh_employee):
    """Пакетная перегенерация не «потеряла» График: ячейки Табеля видны в сетке месяца."""
    days = _month_days(3)
    r = admin_client.post("/api/tabel/bulk", json={
        "employee_ids": [fresh_employee["id"]], "dates": days, "code": "Я", "hours": 12})
    assert r.status_code == 200, r.text
    assert r.json()["errors"] == [], r.text
    grid = admin_client.get("/api/schedule", params={"year": TODAY.year, "month": TODAY.month})
    assert grid.status_code == 200, grid.text
    row = next(x for x in grid.json()["rows"] if x["employee"]["id"] == fresh_employee["id"])
    for iso in days:
        cell = row["cells"].get(iso) or {}
        assert (cell.get("tabel") or {}).get("code") == "Я", (iso, cell)
        assert cell.get("shifts"), f"в день {iso} нет сгенерированной смены: {cell}"


def test_range_absence_regeneration_is_batched(admin_client, fresh_employee, sql_counter):
    """`POST /api/schedule/range-absence`: период внутри месяца — одна перегенерация."""
    first, last = MONTH_FIRST + dt.timedelta(days=1), MONTH_FIRST + dt.timedelta(days=10)
    with sql_counter() as c:
        r = admin_client.post("/api/schedule/range-absence", json={
            "employee_ids": [fresh_employee["id"]], "first": first.isoformat(),
            "last": last.isoformat(), "code": "ОТ", "note": "тест P0-3"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["errors"] == [], body["errors"]
    assert body["written"] == 10, body
    assert _rebuild_deletes(c) == REBUILD_DELETES_PER_MONTH, _rebuild_deletes(c)


def test_range_absence_cross_month_regeneration_per_month(admin_client, fresh_employee, sql_counter):
    """Период через границу месяцев — по одной перегенерации на каждый затронутый месяц."""
    nxt_first = (MONTH_FIRST + dt.timedelta(days=32)).replace(day=1)
    first, last = nxt_first - dt.timedelta(days=3), nxt_first + dt.timedelta(days=4)
    # сотрудник должен быть трудоустроен в следующем месяце: приём 1-го числа текущего
    with sql_counter() as c:
        r = admin_client.post("/api/schedule/range-absence", json={
            "employee_ids": [fresh_employee["id"]], "first": first.isoformat(),
            "last": last.isoformat(), "code": "ОТ"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["written"] == 8, body
    assert _rebuild_deletes(c) == 2 * REBUILD_DELETES_PER_MONTH, _rebuild_deletes(c)


def test_single_cell_edit_still_regenerates_neighbours(admin_client, fresh_employee, sql_counter):
    """Правка ОДНОЙ ячейки (`PUT /api/tabel/cell`) перегенерирует день и соседей, как раньше."""
    day = (MONTH_FIRST + dt.timedelta(days=5)).isoformat()
    with sql_counter() as c:
        r = admin_client.put("/api/tabel/cell", json={
            "employee_id": fresh_employee["id"], "date": day, "code": "Я", "hours": 12})
    assert r.status_code == 200, r.text
    assert _rebuild_deletes(c) == 1, _rebuild_deletes(c)


# ── P0-2: инициализация схемы под замком ──────────────────────────────────────

def test_init_db_runs_under_startup_lock(monkeypatch):
    """init_db берёт замок и только потом гоняет шаги: два воркера не встречаются в DDL."""
    import app.main as main

    calls: list[str] = []
    real_lock = main.startup_lock

    @contextlib.contextmanager
    def spy(timeout=None):
        calls.append("lock")
        with (real_lock() if timeout is None else real_lock(timeout)):
            yield
        calls.append("unlock")

    monkeypatch.setattr(main, "startup_lock", spy)
    monkeypatch.setattr(main, "_init_db_steps", lambda: calls.append("steps"))
    main.init_db()
    assert calls == ["lock", "steps", "unlock"], calls


def test_startup_lock_waits_for_other_process():
    """Замок межпроцессный: пока его держит сосед, старт ждёт и падает по таймауту."""
    from app.core.startup_lock import startup_lock

    holder = subprocess.Popen(
        [sys.executable, "-c",
         "import time\n"
         "from app.core.startup_lock import startup_lock\n"
         "with startup_lock():\n"
         "    print('held', flush=True)\n"
         "    time.sleep(10)\n"],
        cwd=BASE, env=os.environ.copy(), stdout=subprocess.PIPE, text=True)
    try:
        assert holder.stdout is not None
        assert holder.stdout.readline().strip() == "held", "ребёнок не взял замок"
        started = time.monotonic()
        with pytest.raises(RuntimeError, match="замка инициализации"), startup_lock(timeout=0.5):
            pass                                  # pragma: no cover — сюда не попадаем
        assert time.monotonic() - started >= 0.5      # действительно ждали, а не отказали сразу
    finally:
        holder.kill()
        holder.wait(timeout=10)
    # после выхода соседа замок свободен
    with startup_lock(timeout=5):
        pass


def test_startup_lock_is_reentrant_in_same_process():
    """Вложенный вызов в том же процессе не ждёт сам себя (init_db вызывают и тесты, и CI)."""
    from app.core.startup_lock import startup_lock

    with startup_lock(timeout=5), startup_lock(timeout=0.2):
        pass


def test_migrations_have_no_blanket_suppress():
    """`suppress(Exception)` вокруг DDL на PostgreSQL портит транзакцию всего шага (P0-2).

    Проверяем по AST, а не поиском подстроки: упоминание в комментарии — не код.
    """
    src = (BASE / "app/bootstrap/migrations.py").read_text(encoding="utf-8")
    found = []
    for node in ast.walk(ast.parse(src)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if name == "suppress" and any(getattr(a, "id", None) == "Exception" for a in node.args):
            found.append(node.lineno)
    assert not found, (
        f"в migrations.py на строках {found} подавляются ВСЕ исключения: на PostgreSQL "
        "сбой DDL оставляет транзакцию битой, и следующий шаг роняет старт")


def test_c4a_scratch_script_is_not_tracked():
    """Черновик фазы C4a не должен жить в репозитории (находка ревью 20.10.2026)."""
    assert not (BASE / ".c4a.py").exists(), "в рабочем каталоге лежит черновик .c4a.py"
    proc = subprocess.run(["git", "ls-files"], cwd=BASE, capture_output=True, text=True)
    if proc.returncode != 0:                      # не git-репозиторий (например, архив)
        pytest.skip("git недоступен")
    assert ".c4a.py" not in proc.stdout.split()
