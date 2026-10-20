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

from app.core.time import local_date  # noqa: E402
from app.main import app, init_db  # noqa: E402

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

    # ── 1. отсутствие на период через границу месяцев: коды Табеля (v7.1) ──
    def test_01_range_absence_cross_month(self):
        emp = _create_employee("feat_range", "Ранжев Роман Ранжевич", TODAY - dt.timedelta(days=90))
        nxt_first = (TODAY.replace(day=1) + dt.timedelta(days=32)).replace(day=1)
        start = nxt_first - dt.timedelta(days=3)
        end = nxt_first + dt.timedelta(days=4)
        r = client.post("/api/schedule/range-absence", json={
            "employee_ids": [emp["id"]], "first": start.isoformat(), "last": end.isoformat(),
            "code": "ОТ", "note": "отпуск через границу месяца"})
        self.assertEqual(r.status_code, 200, r.text)
        data = r.json()
        self.assertEqual(data["written"], 8)

        g1 = _grid(start.year, start.month)
        g2 = _grid(end.year, end.month)
        row1, row2 = _row(g1, emp["id"]), _row(g2, emp["id"])
        self.assertIsNotNone(row1)
        self.assertIsNotNone(row2)
        d = start
        while d <= end:
            row = row1 if (d.year, d.month) == (start.year, start.month) else row2
            cell = row["cells"][d.isoformat()]
            self.assertEqual(cell["tabel"]["code"], "ОТ", f"не назначено на {d}")
            self.assertEqual(cell["shifts"], [], f"смена в день отпуска должна исчезнуть: {d}")
            d += dt.timedelta(days=1)

        # непрерывный период для печати находится ЦЕЛИКОМ, даже из дня другого месяца
        r = client.get("/api/schedule/absence-period",
                       params={"employee_id": emp["id"], "date": end.isoformat()})
        self.assertEqual(r.status_code, 200, r.text)
        p = r.json()
        self.assertEqual(p["start"], start.isoformat())
        self.assertEqual(p["end"], end.isoformat())
        self.assertEqual(p["days"], 8)
        self.assertEqual(p["shift"]["code"], "ОТ",
                         "краткая справка отсутствия — код Табеля и его название")

    # ── 1b. «НБ» — артефакт: код исключён из справочника (16.10.2026) ──
    def test_01b_sick_unpaid_code_removed(self):
        """16.10.2026: «Неоплачиваемого больничного» не существует — код «НБ» изъят
        из справочника (REMOVED_DAY_CODES), вид SICK_UNPAID удалён миграцией,
        назначение отсутствия с таким кодом отклоняется."""
        codes = {c["code"] for c in client.get("/api/shift-types/tabel-codes").json()["codes"]}
        self.assertNotIn("НБ", codes)
        kinds = {s["code"] for s in client.get("/api/shift-types?include_archived=true").json()}
        self.assertNotIn("SICK_UNPAID", kinds)
        emp = _create_employee("feat_sick_unpaid", "Небольсин Роман Романович",
                               TODAY - dt.timedelta(days=90))
        start = TODAY.replace(day=1)
        r = client.post("/api/schedule/range-absence", json={
            "employee_ids": [emp["id"]], "first": start.isoformat(), "last": start.isoformat(),
            "code": "НБ", "note": "артефактный код"})
        self.assertEqual(r.status_code, 422, r.text)
        self.assertIn("CFG-DAY-CODES", r.json()["detail"])

    # ── 2. «только рабочие дни» для периода (по Табелю) ──
    def test_02_range_absence_only_work_days(self):
        emp = _create_employee("feat_workonly", "Онлир Работ Работович", TODAY - dt.timedelta(days=90))
        start = TODAY - dt.timedelta(days=20)
        end = TODAY - dt.timedelta(days=11)
        # сначала Табель заполняется из циклов — «рабочие дни» определяются по нему
        for month_first in sorted({(d.year, d.month) for d in (start, end)}):
            r = client.post("/api/tabel/fill-from-cycles", json={
                "year": month_first[0], "month": month_first[1],
                "employee_ids": [emp["id"]], "overwrite": True})
            self.assertEqual(r.status_code, 200, r.text)
        r = client.post("/api/schedule/range-absence", json={
            "employee_ids": [emp["id"]], "first": start.isoformat(), "last": end.isoformat(),
            "shift_type_id": _shift_by_code("TIMEOFF_HOURS")["id"],
            "note": "отгулы", "workdays_only": True})
        self.assertEqual(r.status_code, 200, r.text)
        data = r.json()
        self.assertGreater(data["written"], 0)
        self.assertEqual(data["written"] + data["skipped"], 10)
        # норматив 12.10.2026: у вида «Выходной за часы» нет кода Табеля — отсутствие
        # пишется в График (согласованное отсутствие), Табель остаётся явкой (EX-29)
        self.assertEqual(data["mode"], "schedule_absence")
        # Диапазон «сегодня−20 … сегодня−11» пересекает границу месяца, а число
        # рабочих дней зависит от заполнения Табеля (на него влияют другие тесты
        # прогона): раньше проверялся только месяц начала диапазона, и если все
        # рабочие дни попадали в следующий месяц, тест падал на ровном месте.
        # Смотрим оба месяца диапазона.
        assigned = []
        for y, m in sorted({(d.year, d.month) for d in (start, end)}):
            row = _row(_grid(y, m), emp["id"])
            assigned += [(row, iso) for iso, cell in row["cells"].items()
                         if any(a["kind"] and a["kind"]["code"] == "TIMEOFF_HOURS"
                                for a in cell["absences"])]
        self.assertTrue(assigned)
        # Табель не переписан: в назначенные дни по-прежнему явка с часами
        for row, iso in assigned:
            cell = row["cells"][iso]
            self.assertIsNotNone(cell["tabel"], iso)
            self.assertIn(cell["tabel"]["code"], ("Я", "К"), iso)
            self.assertGreater(cell["tabel"]["hours"], 0, iso)
            self.assertEqual(cell["planned_hours"], cell["tabel"]["hours"], iso)

    # ── 3. «отпросился (выходной за часы)»: согласованное отсутствие — логический
    #       разрез Графика; точка ввода «интервал» единой сущности (Q3, 12.10.2026) ──
    def test_03_partial_absence(self):
        emp = _create_employee("feat_partial", "Отпрос Петр Отпросович", TODAY - dt.timedelta(days=90))
        away = _shift_by_code("TIMEOFF_HOURS")
        day = TODAY - dt.timedelta(days=2)
        # план: «Я 12» в Табеле → смена 08:00–20:00 генерируется из Табеля (16.3)
        r = client.put("/api/tabel/cell", json={
            "employee_id": emp["id"], "date": day.isoformat(), "code": "Я", "hours": 12})
        self.assertEqual(r.status_code, 200, r.text)
        cell = _row(_grid(day.year, day.month), emp["id"])["cells"][day.isoformat()]
        self.assertEqual([(x["start_hm"], x["end_hm"]) for x in cell["shifts"]],
                         [("08:00", "20:00")])
        # «пропуск/отлучка» 14:00–16:00
        r = client.post("/api/schedule/absence", json={
            "employee_id": emp["id"], "date": day.isoformat(),
            "from_time": "14:00", "until_time": "16:00", "kind_id": away["id"],
            "note": "отпросился к врачу"})
        self.assertEqual(r.status_code, 200, r.text)
        absence_id = r.json()["id"]
        cell = _row(_grid(day.year, day.month), emp["id"])["cells"][day.isoformat()]
        self.assertEqual(len(cell["absences"]), 1)
        self.assertEqual((cell["absences"][0]["start_hm"], cell["absences"][0]["end_hm"]),
                         ("14:00", "16:00"))
        # хранимая смена физически НЕ делится (v7/R17) — разрез логический
        self.assertEqual([(x["start_hm"], x["end_hm"]) for x in cell["shifts"]],
                         [("08:00", "20:00")])
        # план строки Табеля отсутствие не меняет (RUL-ABSENCE-ONLY-FLAGS)
        self.assertEqual(cell["tabel"]["hours"], 12.0)
        # факт: работал 08–14 и 16–20
        _punch_day(emp["id"], day, [("08:00", "14:00"), ("16:00", "20:00")])
        # удаление отсутствия восстанавливает отображение
        r = client.delete(f"/api/schedule/absence/{absence_id}")
        self.assertEqual(r.status_code, 200, r.text)
        cell = _row(_grid(day.year, day.month), emp["id"])["cells"][day.isoformat()]
        self.assertEqual(cell["absences"], [])
        # отсутствие через полночь допустимо (≤ 24 ч)
        r = client.post("/api/schedule/absence", json={
            "employee_id": emp["id"], "date": day.isoformat(),
            "from_time": "22:00", "until_time": "06:00", "next_day": True})
        self.assertEqual(r.status_code, 200, r.text)
        # длина > 24 ч отклоняется (CHK-ABSENCE-LENGTH)
        r = client.post("/api/schedule/absence", json={
            "employee_id": emp["id"], "date": day.isoformat(),
            "from_time": "08:00", "until_time": "09:00", "next_day": True})
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

        # строку Табеля на день вне трудоустройства поставить нельзя (R35)
        r = client.put("/api/tabel/cell", json={
            "employee_id": emp["id"], "date": TODAY.isoformat(), "code": "Я", "hours": 12})
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

    # ── 6. ручные корректировки банка + посев OPENING_SEED (v7.1/R37) ──
    def test_06_bank_adjust(self):
        hired = TODAY - dt.timedelta(days=40)
        emp = _create_employee("feat_bank", "Банков Банк Банкович", hired)
        r = sup.post(f"/api/employees/{emp['id']}/bank-adjust",
                     json={"hours": 5, "note": "проба супервайзера"})
        self.assertEqual(r.status_code, 403)
        r = client.post(f"/api/employees/{emp['id']}/bank-adjust",
                        json={"hours": 4, "date": TODAY.isoformat(),
                              "note": "премия за подмену 12.09"})
        self.assertEqual(r.status_code, 200, r.text)
        # банк экрана = итог последнего ЗАКРЫТОГО периода (живой расчёт — только в УТ)
        self.assertEqual(r.json()["bank_now"], 0.0)
        r = client.post(f"/api/employees/{emp['id']}/bank-adjust", json={"hours": -1.5, "note": ""})
        self.assertEqual(r.status_code, 422, "причина обязательна")
        items = client.get(f"/api/employees/{emp['id']}/bank-adjustments").json()["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["note"], "премия за подмену 12.09")
        self.assertEqual(items[0]["reason_code"], "manual")
        # посев OPENING_SEED: в первый период (месяц приёма) — можно, в прочие — нельзя
        r = client.post(f"/api/employees/{emp['id']}/bank-adjust", json={
            "hours": 6, "date": TODAY.isoformat(), "note": "посев не в первый период",
            "reason_code": "OPENING_SEED"})
        self.assertEqual(r.status_code, 409)
        first_month_day = hired.replace(day=1)
        r = client.post(f"/api/employees/{emp['id']}/bank-adjust", json={
            "hours": 6, "date": first_month_day.isoformat(), "note": "начальный банк",
            "reason_code": "OPENING_SEED"})
        self.assertEqual(r.status_code, 200, r.text)
        # удаление корректировки (с аудитом)
        items = client.get(f"/api/employees/{emp['id']}/bank-adjustments").json()["items"]
        manual = next(i for i in items if i["reason_code"] == "manual")
        r = client.delete(f"/api/employees/{emp['id']}/bank-adjustments/{manual['id']}")
        self.assertEqual(r.status_code, 200)

    # ── 7. доска «Отметки» доступна всем ролям (16.2) ──
    def test_07_onwork(self):
        r = emp_client.get("/api/presence/board")
        self.assertEqual(r.status_code, 200, r.text)
        data = r.json()
        for key in ("at_work_now", "expected_now", "open_session_cards", "yet_to_come"):
            self.assertIn(key, data)
        r = client.get("/api/presence/board")
        self.assertEqual(r.status_code, 200)

    # ── 8. словарь смен: архив вместо удаления, ревизии истории ──
    def test_08_shift_archive_and_revisions(self):
        r = client.post("/api/shift-types", json={
            "code": "FEAT_TMP", "name": "07:00–15:00 (8 ч)", "short_code": "7–15",
            "kind": "work", "start_time": "07:00", "end_time": "15:00", "color": "#888888",
            "sort_order": 900, "is_working": True, "counts_as_worked": True,
            "is_default_off": False})
        self.assertEqual(r.status_code, 200, r.text)
        st = r.json()

        # меняем часы: значения фиксируются ревизиями
        recent_from = TODAY - dt.timedelta(days=20)
        r = client.put(f"/api/shift-types/{st['id']}", json={
            "code": "FEAT_TMP", "name": "07:00–16:00 (9 ч)", "short_code": "7–16",
            "kind": "work", "start_time": "07:00", "end_time": "16:00", "color": "#888888",
            "sort_order": 900, "is_working": True, "counts_as_worked": True,
            "is_default_off": False, "effective_from": recent_from.isoformat()})
        self.assertEqual(r.status_code, 200, r.text)
        revs = client.get(f"/api/shift-types/{st['id']}/revisions").json()["revisions"]
        self.assertGreaterEqual(len(revs), 2)
        self.assertEqual(revs[0]["end_time"], "15:00")   # прежние значения зафиксированы
        self.assertEqual(revs[-1]["end_time"], "16:00")

        # удаление = архив: в списке нет, в архиве есть, возврат работает
        r = client.delete(f"/api/shift-types/{st['id']}")
        self.assertEqual(r.status_code, 200, r.text)
        codes = [x["code"] for x in client.get("/api/shift-types").json()]
        self.assertNotIn("FEAT_TMP", codes)
        codes_arch = [x["code"] for x in
                      client.get("/api/shift-types", params={"include_archived": "true"}).json()]
        self.assertIn("FEAT_TMP", codes_arch)
        r = client.post(f"/api/shift-types/{st['id']}/restore")
        self.assertEqual(r.status_code, 200)
        codes = [x["code"] for x in client.get("/api/shift-types").json()]
        self.assertIn("FEAT_TMP", codes)
        client.delete(f"/api/shift-types/{st['id']}")

        # «выходной по умолчанию» архивировать нельзя
        # 18.10.2026: вида «выходной по умолчанию» в словаре нет: выходной день
        # Графика — код «В» из Табеля; предохранитель «единственный default_off»
        # остаётся в модели, но в демо-словаре недостижим
        kinds = client.get("/api/shift-types", params={"include_archived": "true"}).json()
        self.assertFalse(any(k["is_default_off"] for k in kinds))

    # ── 9. блоки: Пятидневка (свои выходные) и Другие смены (цикл 3/3) → Табель ──
    def test_09_groups_and_patterns(self):
        choices = client.get("/api/group-choices").json()
        names = [g["name"] for g in choices]
        self.assertEqual(names, ["Смена 1", "Смена 2", "Пятидневка", "Другие смены"])
        kinds = {g["name"]: g["kind"] for g in choices}
        self.assertEqual(kinds["Пятидневка"], "week5")
        self.assertEqual(kinds["Другие смены"], "cycle")

        # пятидневка с выходными вс/пн
        emp5 = _create_employee("feat_week5", "Пятиднев Петр Недельнович",
                                TODAY - dt.timedelta(days=90), group="Пятидневка")
        r = client.post(f"/api/employees/{emp5['id']}/block-change", json={
            "group": "Пятидневка", "date": (TODAY - dt.timedelta(days=90)).isoformat(),
            "kind": "week5", "off_weekdays": [6, 0], "value": "Я 9",
            "label": "5/2, выходные вс и пн"})
        self.assertEqual(r.status_code, 200, r.text)
        r = client.post("/api/tabel/fill-from-cycles", json={
            "year": TODAY.year, "month": TODAY.month, "employee_ids": [emp5["id"]],
            "overwrite": True})
        self.assertEqual(r.status_code, 200, r.text)
        # воскресенье внутри текущего месяца (Табель заполнен на весь месяц, включая будущие дни)
        d = TODAY.replace(day=1)
        while d.weekday() != 6:
            d += dt.timedelta(days=1)
        sunday = d
        g = _grid(sunday.year, sunday.month)
        row = _row(g, emp5["id"])
        for day, expect_off in ((sunday, True), (sunday + dt.timedelta(days=1), True),
                                (sunday - dt.timedelta(days=1), False)):
            if (day.year, day.month) != (sunday.year, sunday.month):
                continue
            code = (row["cells"][day.isoformat()]["tabel"] or {}).get("code")
            self.assertEqual(code, "В" if expect_off else "Я",
                             f"{day} weekday={day.weekday()} code={code}")
        labels = [b.get("pattern_label") for b in row["blocks"]]
        self.assertTrue(any(labels), "у блока пятидневки должна быть подпись шаблона")

        # другие смены: цикл 3/3 дневные от опорной даты — фаза видна в Табеле
        emp3 = _create_employee("feat_cycle", "Циклёв Цикл Циклович",
                                TODAY - dt.timedelta(days=90), group="Другие смены")
        anchor = TODAY.replace(day=1)
        r = client.post(f"/api/employees/{emp3['id']}/block-change", json={
            "group": "Другие смены", "date": anchor.isoformat(), "kind": "cycle",
            "cycle": "3/3", "value": "Я 12", "anchor": anchor.isoformat(),
            "label": "3/3 дневные"})
        self.assertEqual(r.status_code, 200, r.text)
        r = client.post("/api/tabel/fill-from-cycles", json={
            "year": anchor.year, "month": anchor.month, "employee_ids": [emp3["id"]],
            "overwrite": True})
        self.assertEqual(r.status_code, 200, r.text)
        g = _grid(anchor.year, anchor.month)
        row = _row(g, emp3["id"])
        checked = 0
        for iso, cell in row["cells"].items():
            d = dt.date.fromisoformat(iso)
            if not cell["employed"] or d > TODAY:
                continue
            idx = (d - anchor).days % 6
            expect_work = idx < 3
            code = (cell["tabel"] or {}).get("code")
            self.assertEqual(code == "Я", expect_work, f"цикл 3/3 сломан на {d}: {code}")
            checked += 1
        self.assertGreater(checked, 5)

    # ── 10. вкладка «Факт»: история сессий (16.4) ──
    def test_10_fact_view(self):
        emp = _create_employee("feat_fact", "Фактов Факт Фактович", TODAY - dt.timedelta(days=60))
        day = TODAY - dt.timedelta(days=3)
        client.put("/api/tabel/cell", json={
            "employee_id": emp["id"], "date": day.isoformat(), "code": "Я", "hours": 12})
        # пришёл в 06:00 (раньше), перерыв 12–13, ушёл в 20:00
        for kind, t in (("in", "06:00"), ("out", "12:00"), ("in", "13:00"), ("out", "20:00")):
            r = client.post("/api/punches", json={
                "kind": kind, "employee_id": emp["id"], "ts": f"{day.isoformat()}T{t}"})
            self.assertEqual(r.status_code, 200, r.text)
        r = client.get("/api/fact/sessions", params={
            "employee_id": emp["id"], "first": day.isoformat(), "last": day.isoformat()})
        self.assertEqual(r.status_code, 200, r.text)
        data = r.json()
        sessions = data["sessions"]
        self.assertEqual(len(sessions), 2)
        self.assertEqual(sessions[0]["start_local"][11:16], "06:00")
        self.assertEqual(sessions[0]["end_local"][11:16], "12:00")
        self.assertEqual(sessions[1]["minutes"], 420)
        self.assertFalse(sessions[0]["open"])
        # визуализация — фронтенд: бэкенд отдаёт только исходные моменты
        self.assertIn("start_utc", sessions[0])

    # ── 11. карточка: гражданство/служба попадают в документ ──
    def test_11_doc_values(self):
        emp = _create_employee("feat_doc", "Документов Док Документович",
                               TODAY - dt.timedelta(days=60))
        away = _shift_by_code("TIMEOFF_HOURS")
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
