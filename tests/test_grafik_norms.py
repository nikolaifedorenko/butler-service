"""Норматив владельца от 12.10.2026: задачи T1, T3, T4.

План и решения — в `docs/REVIEW-GRAFIK-4-SLOYA-2026-10-12.md` (§5, §6, §9).

**T1 · «код в табеле» у смены** (ответ на Q9): модель не меняется — код Табеля жёстко
определяет стандартное окно дня, эти же часы попадают в График первоначальными сменами.
Чинится поле: редактор отправлял одну подпись («08-20») и в `display_code`, и в
`tzh_code`, из-за чего health-панель выдавала APP-SHIFT-CODE, а ночные и суточные смены
переставали заполнять Табель из циклов. Теперь подпись сетки и код Табеля — разные поля,
в коде Табеля допустимы только коды CFG-DAY-CODES или пусто, а старым базам значения не
из словаря чистит миграция.

**T3 · «Сбросить» в Табеле** (Q5): убирает введённые вручную коды периода и возвращает
автозаполнение из циклов; закрытых периодов не касается; График перегенерируется.

**T4 · единое «отпросился (выходной за часы)»** (Q3, Q4, Q8): одна запись словаря с двумя
точками ввода (интервал / вся смена), назначение информационное (часов и плана не меняет —
неотработанные часы окна уходят в недостачу, её гасит банк при закрытии), заявление
выбирается по точке ввода, а из Графика назначаются только виды «за счёт часов»:
отпуск/больничный/за свой счёт/оплачиваемый выходной — коды Табеля (слой 0).

**T5 · «График» = 4 слоя** (Q2, Q7): один пункт меню «График» со слоями 0 Табель ·
1 План/График · 2 Факт · 3 Управленческий Табель; в слое 2 — сетка «Номера»
(``GET /api/fact/day``): день глазами движка — отметки СКУД и округление до шага,
окно из кода Табеля, план/отработано/недостача/переработка, флаги из Графика.
Доска «Отметки» остаётся отдельным пунктом меню.
"""
from __future__ import annotations

import calendar
import datetime as dt
import os
import tempfile
import unittest

# свой файл БД при отдельном запуске модуля; в общем прогоне — база conftest
_tmp_db = os.path.join(tempfile.gettempdir(), "tt_grafik_norms.db")
if "DATABASE_URL" not in os.environ:
    if os.path.exists(_tmp_db):
        os.remove(_tmp_db)
    os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_db}"
    os.environ["SECRET_KEY"] = "test-secret-key"

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.core.db import SessionLocal  # noqa: E402
from app.core.time import local_date  # noqa: E402
from app.main import app, init_db  # noqa: E402
from app.modules.timesheet.application.catalog import (  # noqa: E402
    TabelDay,
)

init_db()
client = TestClient(app)          # администратор
employee_client = TestClient(app)  # сотрудник (проверка прав)

TODAY = local_date()
FIRST = TODAY.replace(day=1)
# месяц с уже прошедшей первой неделей — для тестов с отметками задним числом
# («Отметка не может быть в будущем»): в первые дни месяца — предыдущий месяц
PAST_FIRST = FIRST if TODAY.day > 7 else (FIRST - dt.timedelta(days=1)).replace(day=1)


def _login(c: TestClient, username: str) -> None:
    r = c.post("/api/auth/login", json={"username": username, "password": "demo1234"})
    assert r.status_code == 200, r.text


def _shift(code: str) -> dict:
    for s in client.get("/api/shift-types?include_archived=true").json():
        if s["code"] == code:
            return s
    raise AssertionError(f"вид смены {code} не найден в словаре")


def _tabel(year: int = None, month: int = None) -> dict:
    y, m = year or TODAY.year, month or TODAY.month
    r = client.get("/api/tabel", params={"year": y, "month": m})
    assert r.status_code == 200, r.text
    return r.json()


def _tabel_row(emp_id: int, day: dt.date):
    db = SessionLocal()
    try:
        return db.scalar(select(TabelDay).where(TabelDay.employee_id == emp_id,
                                                TabelDay.date == day))
    finally:
        db.close()


def _create_employee(username: str, full_name: str, group: str = "Смена 1") -> dict:
    r = client.post("/api/employees", json={
        "full_name": full_name, "position": "Батлер (норматив 12.10)",
        "hired_at": (TODAY - dt.timedelta(days=120)).isoformat(), "schedule_group": group,
        "role": "employee", "username": username, "password": "demo1234"})
    assert r.status_code == 200, r.text
    return r.json()


def _month_end(day: dt.date) -> dt.date:
    return dt.date(day.year, day.month, calendar.monthrange(day.year, day.month)[1])


def _fill_cycle(emp_id: int, first: dt.date = FIRST) -> None:
    """Цикл 2/2 сменами 08:00–20:00 на ВЕСЬ месяц: явки «Я 12» и выходные «В».

    Массовой правкой Табеля, как «Слой 0» в интерфейсе (прежний POST /api/schedule/fill-pattern
    удалён по решению владельца В-7); График перегенерируется из Табеля. Месяц заполняется
    целиком: Табель обязан покрывать период (RUL-TIMESHEET-COVERS-PERIOD).
    """
    days = [first + dt.timedelta(days=i) for i in range((_month_end(first) - first).days + 1)]
    for code, hours, part in (("Я", 12, [d for i, d in enumerate(days) if i % 4 < 2]),
                              ("В", 0, [d for i, d in enumerate(days) if i % 4 >= 2])):
        r = client.post("/api/tabel/bulk", json={"employee_ids": [emp_id], "code": code,
                                                 "hours": hours, "dates": [d.isoformat() for d in part]})
        assert r.status_code == 200 and r.json()["ok"], r.text


def _work_days(emp_id: int, first: dt.date = FIRST) -> list[dt.date]:
    """Дни месяца, где по Табелю стоит явка с часами."""
    data = _tabel(first.year, first.month)
    row = next(r for r in data["rows"] if r["employee"]["id"] == emp_id)
    return [dt.date.fromisoformat(iso) for iso, cell in sorted(row["cells"].items())
            if cell["hours"]]


class TestShiftDictSimplified(unittest.TestCase):
    """Словарь смен 18.10.2026: только ячейки Графика. Связка с Табелем (tzh_code),
    подпись сетки (display_code) и чекбокс банка удалены; отсутствий в словаре,
    кроме системного «Отпросился (выходной за часы)», нет."""

    @classmethod
    def setUpClass(cls):
        _login(client, "admin")
        _login(employee_client, "ivanov")

    def test_01_no_link_fields(self):
        r = client.post("/api/shift-types", json={
            "code": "NORM_T1_A", "name": "07:00–16:00 (9 ч, норматив)",
            "kind": "work", "start_time": "07:00", "end_time": "16:00"})
        self.assertEqual(r.status_code, 200, r.text)
        for gone in ("display_code", "tzh_code", "deduct_from_bank"):
            self.assertNotIn(gone, r.json(), f"поле {gone} удалено из модели")
        self.assertEqual(r.json()["planned_hours"], 9.0)

    def test_02_only_system_absence(self):
        live = [k for k in client.get("/api/shift-types").json()]
        self.assertEqual([k["code"] for k in live if k["kind"] == "absence"],
                         ["TIMEOFF_HOURS"],
                         "из Графика назначается один вид — «за счёт часов»")
        self.assertIn("Отпросился", live and
                      next(k for k in live if k["code"] == "TIMEOFF_HOURS")["name"])

    def test_03_tabel_codes_available_to_editor(self):
        r = client.get("/api/shift-types/tabel-codes")
        self.assertEqual(r.status_code, 200, r.text)
        codes = {c["code"]: c for c in r.json()["codes"]}
        self.assertIn("Я", codes)
        self.assertTrue(codes["Я"]["carries_hours"], "явка несёт часы")
        self.assertIn("В", codes)
        self.assertFalse(codes["В"]["carries_hours"])
        # справочник нужен карточке сотрудника, поэтому читается любым вошедшим
        r = employee_client.get("/api/shift-types/tabel-codes")
        self.assertEqual(r.status_code, 200, r.text)

    def test_04_values_endpoint_for_employee_card(self):
        r = client.get("/api/tabel-values")
        self.assertEqual(r.status_code, 200, r.text)
        vals = {v["value"]: v for v in r.json()["values"]}
        self.assertIn("Я 12", vals)
        self.assertEqual(vals["Я 12"]["start_hm"], "08:00")
        self.assertNotIn("В", {v["code"] for v in r.json()["values"]},
                         "выходной часов не несёт — в значения рабочего дня не попадает")


class TestTimeoffEntity(unittest.TestCase):
    """T4: «отпросился» и «выходной за часы» — одна сущность с двумя точками ввода."""

    @classmethod
    def setUpClass(cls):
        _login(client, "admin")
        cls.emp = _create_employee("norm_timeoff", "Отпросов Отпрос Отпросович")
        _fill_cycle(cls.emp["id"])
        cls.day = _work_days(cls.emp["id"])[0]
        cls.kind = _shift("TIMEOFF_HOURS")

    def test_01_single_dictionary_record(self):
        kinds = client.get("/api/shift-types?include_archived=true").json()
        away = [k for k in kinds if k["code"] == "AWAY_HOURS"]
        self.assertTrue(not away or away[0]["archived"],
                        "дубль «Отпросился: отсутствовал часть смены» слит и в архиве")
        live = [k for k in kinds if not k["archived"]]
        codeless = [k for k in live if k["kind"] == "absence"]
        self.assertEqual([k["code"] for k in codeless], ["TIMEOFF_HOURS"],
                         "из Графика назначается один вид — «за счёт часов»")
        self.assertIn("Отпросился", codeless[0]["name"])
        self.assertIn("выходной за часы", codeless[0]["name"].lower())

    def test_02_whole_shift_entry_point(self):
        """Точка ввода «на всю смену»: заявление — «выходной за ранее отработанные часы»."""
        before = _tabel_row(self.emp["id"], self.day)
        code_before, plan_before = before.code, before.plan_minutes
        r = client.post("/api/schedule/range-absence", json={
            "employee_ids": [self.emp["id"]], "first": self.day.isoformat(),
            "last": self.day.isoformat(), "shift_type_id": self.kind["id"],
            "workdays_only": True, "note": "за ранее отработанные часы"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["mode"], "schedule_absence", "пишется в График, не в Табель")

        p = client.get("/api/schedule/absence-period", params={
            "employee_id": self.emp["id"], "date": self.day.isoformat()})
        self.assertEqual(p.status_code, 200, p.text)
        data = p.json()
        self.assertEqual(data["source"], "schedule_absence")
        self.assertTrue(data["whole_shift"])
        self.assertEqual(data["doc_type"], "day_off_hours")
        self.assertEqual(data["hours_source"], "window_of_day")
        self.assertEqual(data["hours"], 12.0, "часы — стандартное окно, не длина записи")

        after = _tabel_row(self.emp["id"], self.day)
        self.assertEqual((after.code, after.plan_minutes), (code_before, plan_before),
                         "Q8: назначение информационное — Табель не меняется")

    def test_03_interval_entry_point(self):
        """Точка ввода «интервал»: заявление — «об отсутствии на рабочем месте»."""
        grid = client.get("/api/schedule", params={
            "year": self.day.year, "month": self.day.month}).json()
        row = next(r for r in grid["rows"] if r["employee"]["id"] == self.emp["id"])
        absence_id = row["cells"][self.day.isoformat()]["absences"][0]["id"]
        r = client.delete(f"/api/schedule/absence/{absence_id}")
        self.assertEqual(r.status_code, 200, r.text)

        before = _tabel_row(self.emp["id"], self.day)
        code_before, plan_before = before.code, before.plan_minutes
        r = client.post("/api/schedule/absence", json={
            "employee_id": self.emp["id"], "date": self.day.isoformat(),
            "from_time": "14:00", "until_time": "16:00", "kind_id": self.kind["id"],
            "note": "отпросился к врачу"})
        self.assertEqual(r.status_code, 200, r.text)

        data = client.get("/api/schedule/absence-period", params={
            "employee_id": self.emp["id"], "date": self.day.isoformat()}).json()
        self.assertEqual(data["source"], "schedule_absence")
        self.assertFalse(data["whole_shift"])
        self.assertEqual(data["doc_type"], "time_off_request")
        self.assertEqual(data["hours"], 2.0)
        self.assertEqual(data["partial"]["from_time"], "14:00")

        after = _tabel_row(self.emp["id"], self.day)
        self.assertEqual((after.code, after.plan_minutes), (code_before, plan_before))
        # смена физически не делится (v7/R17): разрез логический
        grid = client.get("/api/schedule", params={
            "year": self.day.year, "month": self.day.month}).json()
        row = next(r for r in grid["rows"] if r["employee"]["id"] == self.emp["id"])
        cell = row["cells"][self.day.isoformat()]
        self.assertEqual([(s["start_hm"], s["end_hm"]) for s in cell["shifts"]],
                         [("08:00", "20:00")])
        self.assertEqual(len(cell["absences"]), 1)


class TestIntervalStatements(unittest.TestCase):
    """Несколько отлучек в один день (решение владельца 16.10.2026): ОДНО заявление
    с перечнем интервалов либо заявление по каждому интервалу отдельно (absence_id)."""

    @classmethod
    def setUpClass(cls):
        _login(client, "admin")
        cls.emp = _create_employee("norm_intervals", "Интервалов Интервал Интервалович")
        _fill_cycle(cls.emp["id"])
        cls.day = _work_days(cls.emp["id"])[0]
        cls.kind = _shift("TIMEOFF_HOURS")
        for frm, until, note in (("14:00", "16:00", "к врачу"), ("18:00", "20:00", "")):
            r = client.post("/api/schedule/absence", json={
                "employee_id": cls.emp["id"], "date": cls.day.isoformat(),
                "from_time": frm, "until_time": until,
                "kind_id": cls.kind["id"], "note": note})
            assert r.status_code == 200, r.text

    def _period(self, **extra) -> dict:
        r = client.get("/api/schedule/absence-period", params={
            "employee_id": self.emp["id"], "date": self.day.isoformat(), **extra})
        return r

    def test_01_combined_period_lists_intervals(self):
        r = self._period()
        self.assertEqual(r.status_code, 200, r.text)
        data = r.json()
        self.assertEqual(data["source"], "schedule_absence")
        self.assertEqual([(iv["from_time"], iv["until_time"]) for iv in data["intervals"]],
                         [("14:00", "16:00"), ("18:00", "20:00")])
        self.assertEqual(data["hours"], 4.0, "часы — сумма интервалов")
        self.assertEqual(data["hours_source"], "combined")
        self.assertFalse(data["whole_shift"])
        self.assertEqual(data["doc_type"], "time_off_request")
        self.assertEqual(data["intervals_text"],
                         "с 14:00 до 16:00 (2 ч) и с 18:00 до 20:00 (2 ч)")
        # прежний контракт для одиночных полей сохранён: границы — первого и последнего
        self.assertEqual(data["partial"]["from_time"], "14:00")
        self.assertEqual(data["partial"]["until_time"], "20:00")
        self.assertEqual(data["notes"], ["к врачу"])

    def test_02_single_interval_by_id(self):
        combined = self._period().json()
        second = combined["intervals"][1]
        r = self._period(absence_id=second["id"])
        self.assertEqual(r.status_code, 200, r.text)
        one = r.json()
        self.assertEqual(len(one["intervals"]), 1)
        self.assertEqual(one["partial"]["from_time"], "18:00")
        self.assertEqual(one["partial"]["until_time"], "20:00")
        self.assertEqual(one["hours"], 2.0)
        self.assertEqual(one["hours_source"], "absence_interval")
        self.assertEqual(one["intervals_text"], "с 18:00 до 20:00 (2 ч)")
        self.assertEqual(one["doc_type"], "time_off_request")

    def test_03_unknown_interval_404(self):
        r = self._period(absence_id=10 ** 9)
        self.assertEqual(r.status_code, 404)

    def _docx_text(self, payload: dict) -> str:
        import io

        from docx import Document
        r = client.post("/api/docs/render", json=payload)
        self.assertEqual(r.status_code, 200, r.text[:300])
        doc = Document(io.BytesIO(r.content))
        return "\n".join(par.text for par in doc.paragraphs)

    def test_04_render_combined_intervals(self):
        text = self._docx_text({
            "type": "time_off_request", "employee_id": self.emp["id"],
            "date_from": self.day.isoformat(), "date_to": self.day.isoformat(),
            "format": "docx",
            "intervals": "с 14:00 до 16:00 (2 ч) и с 18:00 до 20:00 (2 ч)"})
        self.assertIn("с 14:00 до 16:00 (2 ч) и с 18:00 до 20:00 (2 ч)", text)
        self.assertIn(self.emp["full_name"], text)

    def test_05_render_single_interval_fallback(self):
        """Без intervals сервер собирает строку из from/until — старые вызовы работают."""
        text = self._docx_text({
            "type": "time_off_request", "employee_id": self.emp["id"],
            "date_from": self.day.isoformat(), "date_to": self.day.isoformat(),
            "format": "docx", "from_time": "14:00", "until_time": "16:00", "hours": 2})
        self.assertIn("с 14:00 до 16:00 (2 ч)", text)


class TestGridCellSegments(unittest.TestCase):
    """Сетка Графика (16.10.2026): segments — видимые отрезки смены (минус отсутствия),
    whole_shift — плашка «Выходной за часы» на весь день. Считает СЕРВЕР — один
    источник правила EX-29 для сетки, печати и заявлений."""

    @classmethod
    def setUpClass(cls):
        _login(client, "admin")
        cls.emp = _create_employee("norm_segments", "Отрезов Отрез Отрезович")
        _fill_cycle(cls.emp["id"])
        days = _work_days(cls.emp["id"])
        cls.day_a, cls.day_b = days[0], days[1]
        cls.kind = _shift("TIMEOFF_HOURS")

    def _cell(self, day) -> dict:
        grid = client.get("/api/schedule", params={
            "year": day.year, "month": day.month}).json()
        row = next(r for r in grid["rows"] if r["employee"]["id"] == self.emp["id"])
        return row["cells"][day.isoformat()]

    def test_01_interval_splits_shift_into_segments(self):
        r = client.post("/api/schedule/absence", json={
            "employee_id": self.emp["id"], "date": self.day_a.isoformat(),
            "from_time": "14:00", "until_time": "16:00", "kind_id": self.kind["id"]})
        self.assertEqual(r.status_code, 200, r.text)
        cell = self._cell(self.day_a)
        self.assertEqual(cell["segments"], [["08:00", "14:00"], ["16:00", "20:00"]])
        self.assertEqual([a["whole_shift"] for a in cell["absences"]], [False])
        self.assertEqual(cell["color"], "#34a862",
                         "цвет ячейки — словарной смены DAY12 (08:00–20:00)")
        # смена физически не делится (v7/R17) — запись осталась одной
        self.assertEqual([(s["start_hm"], s["end_hm"]) for s in cell["shifts"]],
                         [("08:00", "20:00")])

    def test_02_whole_window_absence_flags_whole_shift(self):
        r = client.post("/api/schedule/absence", json={
            "employee_id": self.emp["id"], "date": self.day_b.isoformat(),
            "from_time": "08:00", "until_time": "20:00", "kind_id": self.kind["id"]})
        self.assertEqual(r.status_code, 200, r.text)
        cell = self._cell(self.day_b)
        self.assertTrue(any(a["whole_shift"] for a in cell["absences"]),
                        "отсутствие на всё окно дня — whole_shift для плашки")
        self.assertEqual(cell["segments"], [], "видимых отрезков не осталось")
        self.assertEqual(cell["color"], "#0e9aa7",
                         "цвет плашки — вида отсутствия «Отпросился» из словаря")

    def test_03_seniors_first_within_group(self):
        """Порядок строк (решение 16.10.2026): внутри блока старшие впереди,
        далее по алфавиту — задаётся сервером, поэтому действует на всех стоках."""
        base = {"hired_at": (TODAY - dt.timedelta(days=120)).isoformat(),
                "schedule_group": "Смена 1", "role": "employee", "password": "demo1234"}
        junior = client.post("/api/employees", json={
            **base, "full_name": "Абрамова Батлеровна Батлерова", "position": "Батлер",
            "username": "norm_order_jr"})
        senior = client.post("/api/employees", json={
            **base, "full_name": "Яковлева Старшая Петровна", "position": "Старший батлер",
            "username": "norm_order_sr"})
        self.assertEqual(junior.status_code, 200, junior.text)
        self.assertEqual(senior.status_code, 200, senior.text)
        grid = client.get("/api/schedule", params={
            "year": TODAY.year, "month": TODAY.month}).json()
        order = [r["employee"]["id"] for r in grid["rows"]]
        self.assertLess(order.index(senior.json()["id"]), order.index(junior.json()["id"]),
                        "«Старший батлер» Яковлева — раньше «Батлера» Абрамовой")


class TestManualReplacesGenerated(unittest.TestCase):
    """Дефект 16.10.2026: ручная смена НЕ вытесняла генерацию дня — в ячейке
    соседствовали оба интервала («08:00–20:00» из Табеля + «09:00–18:00» ручная),
    а отрезки отсутствий удваивались. Ручная смена заменяет генерацию дня целиком
    (16.3): save_manual убирает generated-строки дня, rebuild их не возвращает,
    удаление ручной — возвращает день к генерации."""

    @classmethod
    def setUpClass(cls):
        _login(client, "admin")
        cls.emp = _create_employee("norm_manual_gen", "Ручнов Ручной Ручнович")
        _fill_cycle(cls.emp["id"])
        cls.day = _work_days(cls.emp["id"])[0]

    def _cell(self, day) -> dict:
        grid = client.get("/api/schedule", params={
            "year": day.year, "month": day.month}).json()
        row = next(r for r in grid["rows"] if r["employee"]["id"] == self.emp["id"])
        return row["cells"][day.isoformat()]

    def test_01_manual_shift_displaces_generated(self):
        r = client.put("/api/schedule/shift", json={
            "employee_id": self.emp["id"], "date": self.day.isoformat(),
            "shifts": [{"start": "09:00", "end": "18:00"}]})
        self.assertEqual(r.status_code, 200, r.text)
        cell = self._cell(self.day)
        self.assertEqual([(s["source"], s["start_hm"], s["end_hm"]) for s in cell["shifts"]],
                         [("manual", "09:00", "18:00")],
                         "смена из Табеля ушла — осталась только ручная")
        self.assertEqual(cell["segments"], [["09:00", "18:00"]])

    def test_02_rebuild_keeps_manual_priority(self):
        """Правка Табеля дня запускает перегенерацию — ручная смена в приоритете."""
        row = _tabel_row(self.emp["id"], self.day)
        r = client.put("/api/tabel/cell", json={
            "employee_id": self.emp["id"], "date": self.day.isoformat(),
            "code": row.code, "hours": row.plan_minutes / 60, "note": ""})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual([s["source"] for s in self._cell(self.day)["shifts"]], ["manual"])

    def test_03_drop_manual_returns_generated(self):
        r = client.delete("/api/schedule/shift", params={
            "employee_id": self.emp["id"], "date": self.day.isoformat()})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual([(s["source"], s["start_hm"], s["end_hm"])
                          for s in self._cell(self.day)["shifts"]],
                         [("generated", "08:00", "20:00")],
                         "день вернулся к генерации из Табеля")


class TestScheduleMonthReset(unittest.TestCase):
    """«Сбросить месяц» в Графике (16.10.2026, правка владельца того же дня):
    убирает РУЧНЫЕ смены И согласованные отсутствия месяца (отлучки, «выходные
    за часы») — слой 1 возвращается к чистому плану из слоя 0; Табель не
    трогается (сбрасывается из слоя 0)."""

    @classmethod
    def setUpClass(cls):
        _login(client, "admin")
        cls.emp = _create_employee("norm_month_reset", "Сбросов Сброс Сбросович")
        _fill_cycle(cls.emp["id"])
        cls.day = _work_days(cls.emp["id"])[0]
        cls.kind = _shift("TIMEOFF_HOURS")

    def test_01_reset_removes_manual_shifts_and_absences_keeps_tabel(self):
        day = self.day
        r = client.put("/api/schedule/shift", json={
            "employee_id": self.emp["id"], "date": day.isoformat(),
            "shifts": [{"start": "10:00", "end": "19:00"}]})
        self.assertEqual(r.status_code, 200, r.text)
        r = client.post("/api/schedule/absence", json={
            "employee_id": self.emp["id"], "date": day.isoformat(),
            "from_time": "14:00", "until_time": "15:00", "kind_id": self.kind["id"]})
        self.assertEqual(r.status_code, 200, r.text)
        before = _tabel_row(self.emp["id"], day)
        self.assertEqual((before.code, before.plan_minutes), ("Я", 720))

        r = client.post("/api/schedule/reset-month", json={
            "year": day.year, "month": day.month, "employee_ids": [self.emp["id"]]})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["cleared"], 1, "удалена одна ручная смена")
        self.assertEqual(r.json()["absences_cleared"], 1, "удалено согласованное отсутствие")

        grid = client.get("/api/schedule", params={
            "year": day.year, "month": day.month}).json()
        row = next(x for x in grid["rows"] if x["employee"]["id"] == self.emp["id"])
        cell = row["cells"][day.isoformat()]
        self.assertEqual([(s["source"], s["start_hm"], s["end_hm"]) for s in cell["shifts"]],
                         [("generated", "08:00", "20:00")], "График снова из Табеля")
        self.assertEqual(cell["absences"], [],
                         "отлучка снята — слой 1 снова чистый план из слоя 0")
        self.assertEqual(cell["segments"], [["08:00", "20:00"]],
                         "отрезки снова на всё окно — разреза нет")
        after = _tabel_row(self.emp["id"], day)
        self.assertEqual((after.code, after.plan_minutes, after.source),
                         (before.code, before.plan_minutes, before.source),
                         "Табель не тронут")

    def test_02_reset_requires_schedule_edit(self):
        _login(client, "ivanov")
        r = client.post("/api/schedule/reset-month", json={
            "year": TODAY.year, "month": TODAY.month})
        self.assertEqual(r.status_code, 403)
        _login(client, "admin")


class TestFactMonthGantt(unittest.TestCase):
    """Вкладка «Месяц» слоя 2 (16.10.2026): гант фактических присутствий —
    округлённые сессии ЦЕЛИКОМ на непрерывной оси месяца (смена через полночь —
    одна полоса), на день — окно Табеля и цвет словарной смены; сотруднику —
    только своя строка."""

    @classmethod
    def setUpClass(cls):
        _login(client, "admin")
        cls.emp = _create_employee("norm_gantt", "Гантов Гант Гантович")
        _fill_cycle(cls.emp["id"], PAST_FIRST)
        days = _work_days(cls.emp["id"], PAST_FIRST)
        # смена и уход утром следующих суток — в прошлом и в том же месяце
        cls.day = next(d for d in days if d < TODAY - dt.timedelta(days=1)
                       and (d + dt.timedelta(days=1)).month == d.month)
        cls.next_day = cls.day + dt.timedelta(days=1)
        # ручная ночная смена 20:00–08:00 и непрерывные отметки через полночь
        r = client.put("/api/schedule/shift", json={
            "employee_id": cls.emp["id"], "date": cls.day.isoformat(),
            "shifts": [{"start": "20:00", "end": "08:00", "end_next_day": True}]})
        assert r.status_code == 200, r.text
        for ts, kind in ((f"{cls.day.isoformat()}T20:05:00", "in"),
                         (f"{cls.next_day.isoformat()}T07:55:00", "out")):
            r = client.post("/api/punches", json={
                "employee_id": cls.emp["id"], "ts": ts, "kind": kind, "source": "manager"})
            assert r.status_code == 200, r.text

    def _month(self):
        return client.get("/api/fact/month", params={
            "year": self.day.year, "month": self.day.month}).json()

    def test_01_overnight_session_is_single_bar(self):
        data = self._month()
        row = next(r for r in data["rows"] if r["employee"]["id"] == self.emp["id"])
        night = [s for s in row["sessions"]
                 if s["start"].startswith(self.day.isoformat()) and s["start"][11:16] == "20:00"]
        self.assertEqual(len(night), 1, "одна полоса на ночную смену")
        self.assertEqual(night[0]["end"][:16], f"{self.next_day.isoformat()}T08:00",
                         "полоса НЕ разрезана полуночью")
        self.assertFalse(night[0]["open"])

    def test_02_day_window_and_dictionary_color(self):
        data = self._month()
        row = next(r for r in data["rows"] if r["employee"]["id"] == self.emp["id"])
        day = row["days"][self.day.isoformat()]
        self.assertEqual(day["window"], ["08:00", "20:00"],
                         "штриховка — стандартное окно кода Табеля (Я 12), "
                         "ночная полоса факта лежит вне его — переработка видна")
        self.assertEqual(day["color"], "#5b6bd6", "цвет NIGHT12 из словаря смен")
        off_day = next(d for d, info in row["days"].items() if info.get("tabel") == "В")
        self.assertEqual(row["days"][off_day]["color"], "#c3cdd9", "цвет вида «В»")
        self.assertIsNone(row["days"][off_day]["window"])

    def test_03_employee_sees_only_self(self):
        _login(client, "ivanov")
        data = client.get("/api/fact/month", params={
            "year": self.day.year, "month": self.day.month}).json()
        self.assertEqual(len(data["rows"]), 1)
        self.assertEqual(data["rows"][0]["employee"]["id"],
                         client.get("/api/auth/me").json()["user"]["employee_id"])
        _login(client, "admin")


class TestAbsenceLayers(unittest.TestCase):
    """Q4: из Графика — только «за счёт часов», отпуск/ДО/ОВ — коды Табеля."""

    @classmethod
    def setUpClass(cls):
        _login(client, "admin")
        cls.emp = _create_employee("norm_layers", "Слоёв Слой Слоевич")
        _fill_cycle(cls.emp["id"])
        days = _work_days(cls.emp["id"])
        cls.day, cls.next_work_day = days[0], days[1]

    def test_01_vacation_is_tabel_code(self):
        r = client.post("/api/schedule/range-absence", json={
            "employee_ids": [self.emp["id"]], "first": self.day.isoformat(),
            "last": self.day.isoformat(), "code": "ОТ", "note": "приказ №47"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertNotEqual(r.json().get("mode"), "schedule_absence")
        row = _tabel_row(self.emp["id"], self.day)
        self.assertEqual(row.code, "ОТ", "отпуск — код первичного документа")
        self.assertEqual(row.plan_minutes, 0)
        # заявление печатается из Табеля: источник — код Табеля
        data = client.get("/api/schedule/absence-period", params={
            "employee_id": self.emp["id"], "date": self.day.isoformat()}).json()
        self.assertEqual(data["source"], "tabel_code")
        self.assertEqual(data["doc_type"], "vacation_paid")

    def test_02_timeoff_stays_in_schedule(self):
        kind = _shift("TIMEOFF_HOURS")
        day = self.next_work_day       # другой рабочий день: в первом уже код отпуска
        r = client.post("/api/schedule/range-absence", json={
            "employee_ids": [self.emp["id"]], "first": day.isoformat(),
            "last": day.isoformat(), "shift_type_id": kind["id"], "workdays_only": True})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["mode"], "schedule_absence")
        row = _tabel_row(self.emp["id"], day)
        self.assertNotEqual(row.code, "", "в Табеле остаётся явка")
        self.assertGreater(row.plan_minutes, 0, "план дня отсутствие не уменьшает")


class TestFactDayGrid(unittest.TestCase):
    """T5 (Q7): слой 2 «Факт» — сетка «Номера» (GET /api/fact/day).

    Один день глазами движка: сырые отметки СКУД и их округление до шага,
    сопряжённые сессии, окно из кода Табеля (Q1 — жёстко из кода), план /
    отработано / недостача / переработка по категориям и флаги из Графика.
    Числа — из settle периода, содержащего день; шаг округления и границы
    категорий ДЯ/ДН — из настроек, интерфейс ничего не пересчитывает.
    """

    @classmethod
    def setUpClass(cls):
        _login(client, "admin")
        _login(employee_client, "ivanov")
        # сотрудник, принятый в месяце PAST_FIRST: первый период цепочки — этот месяц,
        # после посева OPENING_SEED (v7.1/R37) view_period работает без закрытий
        r = client.post("/api/employees", json={
            "full_name": "Номерова Номер Номеровна", "position": "Батлер (норматив T5)",
            "hired_at": PAST_FIRST.isoformat(), "schedule_group": "Смена 1",
            "role": "employee", "username": "norm_t5_fact", "password": "demo1234"})
        assert r.status_code == 200, r.text
        cls.emp = r.json()
        r = client.post(f"/api/employees/{cls.emp['id']}/bank-adjust", json={
            "hours": 0, "date": PAST_FIRST.isoformat(), "note": "начальный банк (тест T5)",
            "reason_code": "OPENING_SEED"})
        assert r.status_code == 200, r.text
        # цикл 2/2 покрывает месяц явками; целевой день переопределяем «Я 10,75»
        # (окно 08:00–20:00) и отмечаем 07:35 → 19:25
        _fill_cycle(cls.emp["id"], PAST_FIRST)
        cls.day = PAST_FIRST + dt.timedelta(days=4)     # прошедший день: уход 19:25 не в будущем
        r = client.put("/api/tabel/cell", json={
            "employee_id": cls.emp["id"], "date": cls.day.isoformat(),
            "code": "Я", "hours": 10.75, "note": ""})
        assert r.status_code == 200, r.text
        for ts, kind in ((f"{cls.day.isoformat()}T07:35:00", "in"),
                         (f"{cls.day.isoformat()}T19:25:00", "out")):
            r = client.post("/api/punches", json={
                "employee_id": cls.emp["id"], "ts": ts, "kind": kind,
                "source": "manager", "note": "сетка «Номера»"})
            assert r.status_code == 200, r.text

    @staticmethod
    def _rounded(hhmm: str, step: int) -> str:
        """Правило RUL-ROUND-MOMENTS: ближайшее кратное шагу от полуночи,
        ровно половина шага — вперёд. Дублирует домен для проверки ответа."""
        total = int(hhmm[:2]) * 60 + int(hhmm[3:])
        whole, rest = divmod(total, step)
        grids = whole + 1 if rest * 2 >= step else whole
        return f"{grids * step // 60:02d}:{grids * step % 60:02d}"

    def _grid(self, c=None):
        r = (c or client).get("/api/fact/day", params={"date": self.day.isoformat()})
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        row = next(x for x in d["rows"] if x["employee"]["id"] == self.emp["id"])
        return d, row

    def test_01_marks_and_rounding(self):
        """Сырые отметки, округление до шага и сопряжённая сессия — из движка."""
        d, row = self._grid()
        self.assertTrue(d["all_employees"], "менеджер видит всех трудоустроенных в дне")
        self.assertIsNone(row["error"], row["error"])
        self.assertFalse(row["out_of_staff"])
        step = d["step_minutes"]
        self.assertEqual([(m["at"], m["kind"]) for m in row["marks"]],
                         [("07:35", "in"), ("19:25", "out")])
        self.assertEqual([m["rounded"] for m in row["marks"]],
                         [self._rounded("07:35", step), self._rounded("19:25", step)],
                         "округление — то же правило, что в расчёте")
        self.assertEqual([(s["start"], s["end"], s["open"]) for s in row["segments"]],
                         [(self._rounded("07:35", step), self._rounded("19:25", step), False)])

    def test_02_card_numbers_from_engine(self):
        """Окно/план/отработано/недостача/переработка — числа settle, не клиента."""
        d, row = self._grid()
        c = row["card"]
        self.assertIsNotNone(c, row.get("error"))
        step = d["step_minutes"]
        self.assertEqual(c["timesheet_value"], "Я 10,75")
        self.assertEqual(c["window"], ["08:00", "20:00"], "окно жёстко из кода Табеля (Q1)")
        self.assertEqual(c["plan_minutes"], 720, "расчётный план = длина окна (R34)")
        to_min = lambda hhmm: int(hhmm[:2]) * 60 + int(hhmm[3:])  # noqa: E731
        start = to_min(self._rounded("07:35", step))
        end = to_min(self._rounded("19:25", step))
        self.assertEqual(c["fact_minutes"], end - start)
        self.assertEqual(c["work_minutes"], min(end, 20 * 60) - max(start, 8 * 60),
                         "рабочее = сессия ∩ окно")
        self.assertEqual(c["debt_minutes"], max(0, 720 - c["work_minutes"]))
        self.assertEqual(c["overtime_minutes"], c["fact_minutes"] - c["work_minutes"])
        self.assertEqual(sum(c["codes"].values()), c["overtime_minutes"],
                         "переработка целиком разбирается по категориям ДЯ/ДН")

    def test_03_flags_from_schedule(self):
        """Флаги — из Графика: уход раньше конца смены — РАННИЙ УХОД; опоздания нет."""
        _d, row = self._grid()
        codes = {f["code"] for f in row["card"]["flags"]}
        self.assertIn("EARLY_DEPARTURE", codes)
        self.assertNotIn("LATE", codes)
        for f in row["card"]["flags"]:
            self.assertTrue(f["title"], "человеческий текст флага")

    def test_04_employee_sees_only_self(self):
        """Не-менеджер видит в сетке только себя (как в истории сессий)."""
        r = employee_client.get("/api/fact/day", params={"date": self.day.isoformat()})
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        self.assertFalse(d["all_employees"])
        self.assertEqual(len(d["rows"]), 1)
        me = employee_client.get("/api/auth/me").json()
        self.assertEqual(d["rows"][0]["employee"]["id"], me["user"]["employee_id"])

    def test_05_day_before_employment_excluded(self):
        """День до приёма: сотрудника нет в строках сетки (R35)."""
        before = (PAST_FIRST - dt.timedelta(days=10)).isoformat()
        r = client.get("/api/fact/day", params={"date": before})
        self.assertEqual(r.status_code, 200, r.text)
        ids = [x["employee"]["id"] for x in r.json()["rows"]]
        self.assertNotIn(self.emp["id"], ids)


if __name__ == "__main__":
    unittest.main()
