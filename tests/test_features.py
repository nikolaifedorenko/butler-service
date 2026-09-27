"""Тесты новых возможностей: периоды работы (увольнение/повторный приём), отсутствие
через границы месяцев, частичное отсутствие («отпросился»), корректировки банка,
«кто на работе», архив и ревизии словаря смен, блоки «Пятидневка»/«Другие смены»,
вид «Факт» в сетке графика."""
from __future__ import annotations

import datetime as dt
import os
import tempfile
import unittest

# если модуль запущен отдельно — своя тестовая БД; если вместе с остальными —
# app.main уже импортирован и использует общую тестовую базу
_tmp_db = os.path.join(tempfile.gettempdir(), "tt_features.db")
if "DATABASE_URL" not in os.environ:
    if os.path.exists(_tmp_db):
        os.remove(_tmp_db)
    os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_db}"
    os.environ["SECRET_KEY"] = "test-secret-key"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app, init_db  # noqa: E402
from app.deps import local_date  # noqa: E402

init_db()
client = TestClient(app)          # администратор
sup = TestClient(app)             # супервайзер
emp_client = TestClient(app)      # сотрудник

TODAY = local_date()


def _login(c: TestClient, username: str) -> None:
    r = c.post("/api/auth/login", json={"username": username, "password": "demo1234"})
    assert r.status_code == 200, r.text


def _create_employee(username: str, full_name: str, hired: dt.date, group: str = "Смена 1") -> dict:
    r = client.post("/api/employees", json={
        "full_name": full_name, "position": "Батлер (тест)",
        "hired_at": hired.isoformat(), "schedule_group": group,
        "role": "employee", "username": username, "password": "demo1234",
        "nationality": "Российская Федерация", "subdivision": "Служба управления виллами"})
    assert r.status_code == 200, r.text
    return r.json()


def _shift_by_code(code: str) -> dict:
    for s in client.get("/api/shift-types").json():
        if s["code"] == code:
            return s
    raise AssertionError(f"смена {code} не найдена")


def _grid(year: int, month: int) -> dict:
    r = client.get("/api/schedule", params={"year": year, "month": month})
    assert r.status_code == 200, r.text
    return r.json()


def _row(grid: dict, emp_id: int):
    return next((r for r in grid["rows"] if r["employee"]["id"] == emp_id), None)


def _punch_day(emp_id: int, day: dt.date, times: list[tuple[str, str]]) -> None:
    """Отметки задним числом (менеджером): [(in, out), ...] в пределах дня."""
    for t_in, t_out in times:
        r = client.post("/api/punches", json={
            "kind": "in", "employee_id": emp_id, "ts": f"{day.isoformat()}T{t_in}"})
        assert r.status_code == 200, r.text
        r = client.post("/api/punches", json={
            "kind": "out", "employee_id": emp_id, "ts": f"{day.isoformat()}T{t_out}"})
        assert r.status_code == 200, r.text


class TestNewFeatures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _login(client, "admin")
        _login(sup, "gromova")
        _login(emp_client, "ivanov")

    # ── 1. отсутствие на период через границу месяцев (баг №1) ──
    def test_01_range_absence_cross_month(self):
        emp = _create_employee("feat_range", "Ранжев Роман Ранжевич", TODAY - dt.timedelta(days=90))
        vac = _shift_by_code("VACATION")
        nxt_first = (TODAY.replace(day=1) + dt.timedelta(days=32)).replace(day=1)
        start = nxt_first - dt.timedelta(days=3)
        end = nxt_first + dt.timedelta(days=4)
        r = client.post("/api/schedule/range-absence", json={
            "employee_ids": [emp["id"]], "start": start.isoformat(), "end": end.isoformat(),
            "shift_type_id": vac["id"], "note": "отпуск через границу месяца"})
        self.assertEqual(r.status_code, 200, r.text)
        data = r.json()
        self.assertEqual(data["updated"], 8)
        self.assertEqual(len(data["months"]), 2)     # период накрыл два месяца

        # оба месяца содержат назначенные дни
        g1 = _grid(start.year, start.month)
        g2 = _grid(end.year, end.month)
        row1, row2 = _row(g1, emp["id"]), _row(g2, emp["id"])
        self.assertIsNotNone(row1)
        self.assertIsNotNone(row2)
        d = start
        while d <= end:
            g = g1 if (d.year, d.month) == (start.year, start.month) else g2
            row = row1 if g is g1 else row2
            cell = row["cells"][d.isoformat()]
            self.assertEqual(cell["shift"]["code"], "VACATION", f"не назначено на {d}")
            d += dt.timedelta(days=1)

        # непрерывный период для печати находится ЦЕЛИКОМ, даже из дня другого месяца
        r = client.get("/api/schedule/absence-period",
                       params={"employee_id": emp["id"], "date": end.isoformat()})
        self.assertEqual(r.status_code, 200, r.text)
        p = r.json()
        self.assertEqual(p["start"], start.isoformat())
        self.assertEqual(p["end"], end.isoformat())
        self.assertEqual(p["days"], 8)
        self.assertEqual(p["shift"]["code"], "VACATION")

    # ── 2. «только рабочие дни» для периода ──
    def test_02_range_absence_only_work_days(self):
        emp = _create_employee("feat_workonly", "Онлир Работ Работович", TODAY - dt.timedelta(days=90))
        day12 = _shift_by_code("DAY12")
        start = TODAY - dt.timedelta(days=20)
        end = TODAY - dt.timedelta(days=11)
        r = client.post("/api/schedule/range-absence", json={
            "employee_ids": [emp["id"]], "start": start.isoformat(), "end": end.isoformat(),
            "shift_type_id": _shift_by_code("TIMEOFF_HOURS")["id"],
            "note": "отгулы", "only_work_days": True})
        self.assertEqual(r.status_code, 200, r.text)
        data = r.json()
        self.assertGreater(data["updated"], 0)
        self.assertEqual(data["updated"] + data["skipped_off"], 10 * 1)
        # все назначенные дни были рабочими по базовому циклу (2/2)
        g = _grid(start.year, start.month)
        row = _row(g, emp["id"])
        for iso, cell in row["cells"].items():
            if cell["shift"] and cell["shift"]["code"] == "TIMEOFF_HOURS":
                self.assertNotEqual(cell["auto"], None)
        self.assertIsNotNone(day12)

    # ── 3. частичное отсутствие: «отпросился с 14:00 до 16:00» ──
    def test_03_partial_absence(self):
        emp = _create_employee("feat_partial", "Отпрос Петр Отпросович", TODAY - dt.timedelta(days=90))
        day12 = _shift_by_code("DAY12")          # 08:00–20:00, 12 ч
        away = _shift_by_code("AWAY_HOURS")
        day = TODAY - dt.timedelta(days=2)
        # план: рабочая смена + согласованное окно 14:00–16:00
        r = client.put("/api/schedule/cell", json={
            "employee_id": emp["id"], "date": day.isoformat(),
            "shift_type_id": day12["id"], "note": "отпросился к врачу",
            "partial_shift_id": away["id"], "from_time": "14:00", "until_time": "16:00"})
        self.assertEqual(r.status_code, 200, r.text)
        cell = r.json()["cell"]
        self.assertEqual(cell["partial"]["hours"], 2.0)
        self.assertEqual(cell["partial"]["reason"]["code"], "AWAY_HOURS")
        # факт: работал 08–14 и 16–20 (ровно план минус окно)
        _punch_day(emp["id"], day, [("08:00", "14:00"), ("16:00", "20:00")])

        g = _grid(day.year, day.month)
        row = _row(g, emp["id"])
        fact = row["cells"][day.isoformat()]["fact"]
        self.assertIsNotNone(fact)
        self.assertFalse(fact["attention"], f"факт требует внимания: {fact}")
        self.assertEqual(fact["late_hours"], 0.0)
        self.assertEqual(fact["early_hours"], 0.0)
        self.assertEqual(fact["gap_hours"], 0.0)         # согласованное окно — не «перерыв»
        self.assertEqual(fact["counted_hours"], 10.0)    # 12 − 2 часа отсутствия
        # 2 часа списаны с банка (deduct_from_bank у AWAY_HOURS)
        r = client.get(f"/api/employees/{emp['id']}/bank-adjustments")
        self.assertEqual(r.json()["bank_now"], -2.0)

        # частичное отсутствие нельзя поставить на день без рабочей смены
        off_day = None
        for i in range(3, 12):
            d = TODAY - dt.timedelta(days=i)
            gg = _grid(d.year, d.month)
            cc = _row(gg, emp["id"])["cells"][d.isoformat()]
            base_ok = cc["shift"] and cc["shift"]["kind"] == "work"
            if not base_ok and cc["employed"]:
                off_day = d
                break
        if off_day:
            r = client.put("/api/schedule/cell", json={
                "employee_id": emp["id"], "date": off_day.isoformat(), "shift_type_id": None,
                "partial_shift_id": away["id"], "from_time": "14:00", "until_time": "16:00"})
            self.assertEqual(r.status_code, 422)

    # ── 4. увольнение → неактивные дни → повторный приём ──
    def test_04_dismiss_and_rehire(self):
        emp = _create_employee("feat_rehire", "Увольнов Уволь Увольнович",
                               TODAY - dt.timedelta(days=60))
        dis = TODAY - dt.timedelta(days=10)
        r = client.post(f"/api/employees/{emp['id']}/dismiss", json={"date": dis.isoformat()})
        self.assertEqual(r.status_code, 200, r.text)

        g = _grid(dis.year, dis.month)
        row = _row(g, emp["id"])
        self.assertIsNotNone(row, "уволенный в этом месяце сотрудник должен быть виден в сетке")
        self.assertTrue(row["cells"][dis.isoformat()]["employed"],
                        "дата увольнения — последний рабочий день (включительно)")
        after = dis + dt.timedelta(days=1)
        if after.isoformat() in row["cells"]:
            self.assertFalse(row["cells"][after.isoformat()]["employed"])

        # ячейку на неактивный день поставить нельзя
        r = client.put("/api/schedule/cell", json={
            "employee_id": emp["id"], "date": TODAY.isoformat(), "note": "нельзя"})
        self.assertEqual(r.status_code, 409)

        # повторный приём сегодня
        r = client.post(f"/api/employees/{emp['id']}/rehire", json={"date": TODAY.isoformat()})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json()["active"])
        self.assertIsNone(r.json()["dismissed_at"])

        h = client.get(f"/api/employees/{emp['id']}/history").json()
        self.assertEqual(len(h["employment"]), 2)
        self.assertIsNone(h["employment"][1]["end"])

        g = _grid(TODAY.year, TODAY.month)
        row = _row(g, emp["id"])
        self.assertTrue(row["cells"][TODAY.isoformat()]["employed"])
        mid = dis + dt.timedelta(days=5)
        if mid.isoformat() in row["cells"] and mid < TODAY:
            self.assertFalse(row["cells"][mid.isoformat()]["employed"],
                             "дни между периодами работы неактивны")

    # ── 5. отметки вне периодов работы запрещены ──
    def test_05_punch_guard(self):
        emp = _create_employee("feat_punch", "Отметкин Отмет Отметкович",
                               TODAY - dt.timedelta(days=40))
        dis = TODAY - dt.timedelta(days=6)
        client.post(f"/api/employees/{emp['id']}/dismiss", json={"date": dis.isoformat()})
        ts = (TODAY - dt.timedelta(days=2)).isoformat() + "T10:00"
        r = client.post("/api/punches", json={"kind": "in", "employee_id": emp["id"], "ts": ts})
        self.assertEqual(r.status_code, 409)
        ts = (TODAY - dt.timedelta(days=10)).isoformat() + "T10:00"
        r = client.post("/api/punches", json={"kind": "in", "employee_id": emp["id"], "ts": ts})
        self.assertEqual(r.status_code, 200, r.text)
        client.post(f"/api/employees/{emp['id']}/rehire", json={"date": TODAY.isoformat()})

    # ── 6. ручные корректировки банка: admin/manager можно, supervisor нельзя ──
    def test_06_bank_adjust(self):
        emp = _create_employee("feat_bank", "Банков Банк Банкович", TODAY - dt.timedelta(days=40))
        r = sup.post(f"/api/employees/{emp['id']}/bank-adjust",
                     json={"hours": 5, "note": "проба супервайзера"})
        self.assertEqual(r.status_code, 403)
        r = client.post(f"/api/employees/{emp['id']}/bank-adjust",
                        json={"hours": 4, "date": TODAY.isoformat(),
                              "note": "премия за подмену 12.09"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["bank_now"], 4.0)
        r = client.post(f"/api/employees/{emp['id']}/bank-adjust", json={"hours": -1.5, "note": ""})
        self.assertEqual(r.status_code, 422, "причина обязательна")
        items = client.get(f"/api/employees/{emp['id']}/bank-adjustments").json()["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["note"], "премия за подмену 12.09")
        # удаление корректировки (с аудитом)
        r = client.delete(f"/api/employees/{emp['id']}/bank-adjustments/{items[0]['id']}")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["bank_now"], 0.0)

    # ── 7. «Кто на работе» доступен всем ролям ──
    def test_07_onwork(self):
        r = emp_client.get("/api/punches/onwork")
        self.assertEqual(r.status_code, 200, r.text)
        data = r.json()
        self.assertIn("items", data)
        self.assertIn("count", data)
        r = client.get("/api/punches/onwork")
        self.assertEqual(r.status_code, 200)

    # ── 8. словарь смен: архив вместо удаления, ревизии не ломают прошлое ──
    def test_08_shift_archive_and_revisions(self):
        emp = _create_employee("feat_shift", "Словарёв Словар Словаревич",
                               TODAY - dt.timedelta(days=90))
        r = client.post("/api/shift-types", json={
            "code": "FEAT_TMP", "name": "07:00–15:00 (8 ч)", "short_code": "7–15",
            "kind": "work", "start_time": "07:00", "end_time": "15:00", "color": "#888888",
            "sort_order": 900, "is_working": True, "counts_as_worked": True,
            "is_default_off": False})
        self.assertEqual(r.status_code, 200, r.text)
        st = r.json()

        past_day = TODAY - dt.timedelta(days=40)
        r = client.put("/api/schedule/cell", json={
            "employee_id": emp["id"], "date": past_day.isoformat(),
            "shift_type_id": st["id"], "note": ""})
        self.assertEqual(r.status_code, 200, r.text)
        g = _grid(past_day.year, past_day.month)
        self.assertEqual(_row(g, emp["id"])["cells"][past_day.isoformat()]["planned_hours"], 8.0)

        # меняем часы: новое значение действует с recent_from, прошлое остаётся прежним
        recent_from = TODAY - dt.timedelta(days=20)
        r = client.put(f"/api/shift-types/{st['id']}", json={
            "code": "FEAT_TMP", "name": "07:00–16:00 (9 ч)", "short_code": "7–16",
            "kind": "work", "start_time": "07:00", "end_time": "16:00", "color": "#888888",
            "sort_order": 900, "is_working": True, "counts_as_worked": True,
            "is_default_off": False, "effective_from": recent_from.isoformat()})
        self.assertEqual(r.status_code, 200, r.text)

        g = _grid(past_day.year, past_day.month)
        self.assertEqual(_row(g, emp["id"])["cells"][past_day.isoformat()]["planned_hours"], 8.0,
                         "отработанный день в прошлом должен остаться 8-часовым")
        recent_day = TODAY - dt.timedelta(days=10)
        r = client.put("/api/schedule/cell", json={
            "employee_id": emp["id"], "date": recent_day.isoformat(),
            "shift_type_id": st["id"], "note": ""})
        self.assertEqual(r.status_code, 200, r.text)
        g = _grid(recent_day.year, recent_day.month)
        self.assertEqual(_row(g, emp["id"])["cells"][recent_day.isoformat()]["planned_hours"], 9.0)

        revs = client.get(f"/api/shift-types/{st['id']}/revisions").json()["revisions"]
        self.assertGreaterEqual(len(revs), 2)
        self.assertEqual(revs[0]["end_time"], "15:00")   # прежние значения зафиксированы
        self.assertEqual(revs[-1]["end_time"], "16:00")

        # удаление = архив: в списке нет, в прошлой сетке смена осталась
        r = client.delete(f"/api/shift-types/{st['id']}")
        self.assertEqual(r.status_code, 200, r.text)
        codes = [x["code"] for x in client.get("/api/shift-types").json()]
        self.assertNotIn("FEAT_TMP", codes)
        codes_arch = [x["code"] for x in
                      client.get("/api/shift-types", params={"include_archived": "true"}).json()]
        self.assertIn("FEAT_TMP", codes_arch)
        g = _grid(past_day.year, past_day.month)
        cell = _row(g, emp["id"])["cells"][past_day.isoformat()]
        self.assertIsNotNone(cell["shift"])
        self.assertTrue(cell["shift"]["archived"])
        # возврат из архива
        r = client.post(f"/api/shift-types/{st['id']}/restore")
        self.assertEqual(r.status_code, 200)
        codes = [x["code"] for x in client.get("/api/shift-types").json()]
        self.assertIn("FEAT_TMP", codes)
        client.delete(f"/api/shift-types/{st['id']}")

        # «выходной по умолчанию» архивировать нельзя
        off = _shift_by_code("OFF")
        r = client.delete(f"/api/shift-types/{off['id']}")
        self.assertEqual(r.status_code, 409)

    # ── 9. блоки: Пятидневка (свои выходные) и Другие смены (цикл 3/3) ──
    def test_09_groups_and_patterns(self):
        choices = client.get("/api/group-choices").json()
        names = [g["name"] for g in choices]
        self.assertEqual(names, ["Смена 1", "Смена 2", "Пятидневка", "Другие смены"])
        kinds = {g["name"]: g["kind"] for g in choices}
        self.assertEqual(kinds["Пятидневка"], "week5")
        self.assertEqual(kinds["Другие смены"], "cycle")

        # пятидневка с выходными вс/пн (у начальника)
        emp5 = _create_employee("feat_week5", "Пятиднев Петр Недельнович",
                                TODAY - dt.timedelta(days=90), group="Пятидневка")
        r = client.post(f"/api/employees/{emp5['id']}/block-change", json={
            "group": "Пятидневка", "date": (TODAY - dt.timedelta(days=90)).isoformat(),
            "kind": "week5", "off_weekdays": [6, 0], "shift_code": "DAY9",
            "label": "5/2, выходные вс и пн"})
        self.assertEqual(r.status_code, 200, r.text)
        # найдём ближайшее воскресенье и понедельник: оба должны быть выходными
        d = TODAY - dt.timedelta(days=14)
        while d.weekday() != 6:
            d += dt.timedelta(days=1)
        sunday, monday = d, d + dt.timedelta(days=1)
        saturday = sunday - dt.timedelta(days=1)
        for day, expect_off in ((sunday, True), (monday, True), (saturday, False)):
            if day > TODAY:
                continue
            g = _grid(day.year, day.month)
            row = _row(g, emp5["id"])
            if row is None:
                continue
            cell = row["cells"][day.isoformat()]
            is_off = bool(cell["shift"] and cell["shift"].get("is_default_off"))
            self.assertEqual(is_off, expect_off, f"{day} weekday={day.weekday()}")
        g = _grid(sunday.year, sunday.month)
        row = _row(g, emp5["id"])
        if row:
            labels = [b.get("pattern_label") for b in row["blocks"]]
            self.assertTrue(any(labels), "у блока пятидневки должна быть подпись шаблона")

        # другие смены: цикл 3/3 ночные от опорной даты
        emp3 = _create_employee("feat_cycle", "Циклёв Цикл Циклович",
                                TODAY - dt.timedelta(days=90), group="Другие смены")
        anchor = (TODAY - dt.timedelta(days=90)).isoformat()
        r = client.post(f"/api/employees/{emp3['id']}/block-change", json={
            "group": "Другие смены", "date": anchor, "kind": "cycle", "cycle": "3/3",
            "shift_code": "NIGHT12", "anchor": anchor, "label": "3/3 ночные"})
        self.assertEqual(r.status_code, 200, r.text)
        g = _grid(TODAY.year, TODAY.month)
        row = _row(g, emp3["id"])
        self.assertIsNotNone(row)
        # фаза цикла: от anchor каждые 3 дня — рабочие
        anchor_d = dt.date.fromisoformat(anchor)
        checked = 0
        for iso, cell in row["cells"].items():
            d = dt.date.fromisoformat(iso)
            if not cell["employed"] or d > TODAY:
                continue
            idx = (d - anchor_d).days % 6
            expect_work = idx < 3
            got_work = bool(cell["shift"] and cell["shift"]["kind"] == "work")
            self.assertEqual(got_work, expect_work, f"цикл 3/3 сломан на {d}")
            checked += 1
        self.assertGreater(checked, 5)

    # ── 10. вид «Факт»: интервалы работы в ячейке ──
    def test_10_fact_view(self):
        emp = _create_employee("feat_fact", "Фактов Факт Фактович", TODAY - dt.timedelta(days=60))
        day12 = _shift_by_code("DAY12")
        day = TODAY - dt.timedelta(days=3)
        client.put("/api/schedule/cell", json={
            "employee_id": emp["id"], "date": day.isoformat(),
            "shift_type_id": day12["id"], "note": ""})
        # пришёл в 06:00 (раньше), перерыв 12–13 без согласования, ушёл в 20:00
        r = client.post("/api/punches", json={
            "kind": "in", "employee_id": emp["id"], "ts": f"{day.isoformat()}T06:00"})
        self.assertEqual(r.status_code, 200, r.text)
        client.post("/api/punches", json={
            "kind": "out", "employee_id": emp["id"], "ts": f"{day.isoformat()}T12:00"})
        client.post("/api/punches", json={
            "kind": "in", "employee_id": emp["id"], "ts": f"{day.isoformat()}T13:00"})
        client.post("/api/punches", json={
            "kind": "out", "employee_id": emp["id"], "ts": f"{day.isoformat()}T20:00"})
        g = _grid(day.year, day.month)
        fact = _row(g, emp["id"])["cells"][day.isoformat()]["fact"]
        self.assertIsNotNone(fact)
        self.assertTrue(fact["intervals"], "в ячейке должны быть интервалы работы")
        self.assertEqual(fact["intervals"][0][0], "06:00")
        self.assertEqual(fact["gap_hours"], 1.0)         # несогласованный перерыв 12–13
        self.assertTrue(fact["attention"])               # день требует внимания
        # по умолчанию часы ДО начала смены не засчитываются (count_early_arrival = 0):
        # 08:00–12:00 = 4 ч и 13:00–20:00 = 7 ч ⇒ 11 ч, хотя интервалы показаны целиком
        self.assertEqual(fact["counted_hours"], 11.0)
        self.assertEqual([i for i in fact["intervals"]], [["06:00", "12:00"], ["13:00", "20:00"]])

        # включили «засчитывать ранний приход» — ранние 2 ч добавились к факту и банку
        self.assertEqual(client.put("/api/settings", json=[
            {"key": "count_early_arrival", "value": "1"}]).status_code, 200)
        self.assertEqual(client.post("/api/settings/recalc-all", params={
            "year": day.year, "month": day.month}).status_code, 200)
        fact = _row(_grid(day.year, day.month), emp["id"])["cells"][day.isoformat()]["fact"]
        self.assertEqual(fact["counted_hours"], 13.0)

        # возвращаем настройку обратно, чтобы не влиять на другие тесты
        client.put("/api/settings", json=[{"key": "count_early_arrival", "value": "0"}])
        client.post("/api/settings/recalc-all", params={"year": day.year, "month": day.month})

    # ── 11. карточка: гражданство/служба попадают в документ ──
    def test_11_doc_values(self):
        emp = _create_employee("feat_doc", "Документов Док Документович",
                               TODAY - dt.timedelta(days=60))
        away = _shift_by_code("AWAY_HOURS")
        day12 = _shift_by_code("DAY12")
        day = TODAY - dt.timedelta(days=4)
        client.put("/api/schedule/cell", json={
            "employee_id": emp["id"], "date": day.isoformat(),
            "shift_type_id": day12["id"], "partial_shift_id": away["id"],
            "from_time": "14:00", "until_time": "16:00", "note": "по семейным обстоятельствам"})
        r = client.post("/api/docs/render", json={
            "type": "time_off_request", "employee_id": emp["id"],
            "date_from": day.isoformat(), "date_to": day.isoformat(), "format": "docx",
            "from_time": "14:00", "until_time": "16:00", "hours": 2,
            "reason": away["name"], "note": "по семейным обстоятельствам"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.content.startswith(b"PK"))     # docx — это zip
        # PDF: 200, если есть LibreOffice или reportlab; иначе честный 501 с подсказкой
        r = client.post("/api/docs/render", json={
            "type": "time_off_request", "employee_id": emp["id"],
            "date_from": day.isoformat(), "date_to": day.isoformat(), "format": "pdf",
            "from_time": "14:00", "until_time": "16:00", "hours": 2})
        self.assertIn(r.status_code, (200, 501), r.text)
        if r.status_code == 200:
            self.assertTrue(r.content.startswith(b"%PDF"))
        else:
            self.assertIn("DOCX", r.json()["detail"])

    # ── 12. сетка: уволенный в прошлом месяце не виден в текущем ──
    def test_12_dismissed_not_in_later_months(self):
        emp = _create_employee("feat_gone", "Пропалов Пропал Пропалович",
                               TODAY - dt.timedelta(days=120))
        dis = TODAY - dt.timedelta(days=45)
        client.post(f"/api/employees/{emp['id']}/dismiss", json={"date": dis.isoformat()})
        g = _grid(TODAY.year, TODAY.month)
        self.assertIsNone(_row(g, emp["id"]),
                          "в месяце, где сотрудник уже не работал, его строки быть не должно")
        g2 = _grid(dis.year, dis.month)
        self.assertIsNotNone(_row(g2, emp["id"]),
                             "в месяце увольнения сотрудник виден (смены до увольнения)")


if __name__ == "__main__":
    unittest.main()
