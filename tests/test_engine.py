"""Проверки движка расчёта версии 2: куски сессий, календарный контур выплаты, банк, зачёт с долгом."""
from __future__ import annotations

import datetime as dt
import unittest

from app.deps import local_date
from app.models import Employee, Punch, ScheduleEntry, ShiftType
from app.schedule_patterns import parse_custom_cycle, pattern_days
from app.timesheet import (
    DEFAULT_RULES,
    _subtract,
    coerce_rules,
    compute_day,
    pair_sessions,
    round_dt,
    settle_overtime,
    shift_window,
    split_day_night,
)


def rules(**over):
    r = dict(DEFAULT_RULES)
    r.update(over)
    return r


def make_shift(code, name, start, end, overnight=False, kind="work", tzh="Я", **kw):
    defaults = dict(is_working=kind == "work", counts_as_worked=True, is_default_off=code == "OFF")
    defaults.update(kw)
    return ShiftType(id=1, code=code, name=name, display_code=code, tzh_code=tzh, kind=kind,
                     start_time=start, end_time=end, overnight=overnight,
                     color="#ffffff", sort_order=1, **defaults)


def make_emp(emp_id=1):
    return Employee(id=emp_id, full_name="Иванов Иван Иванович", short_name="Иванов И.И.",
                    position="Батлер", balance_hours=0, schedule_group="Смена 1",
                    group_color="#8a94a6")


def make_punches(date, pairs):
    out = []
    for i, (in_hm, out_hm) in enumerate(pairs):
        h1, m1 = (int(x) for x in in_hm.split(":"))
        out.append(Punch(id=i * 2 + 1, employee_id=1,
                         ts=dt.datetime(date.year, date.month, date.day, h1, m1), kind="IN", source="web"))
        if out_hm:
            h2, m2 = (int(x) for x in out_hm.split(":"))
            end_day = date + dt.timedelta(days=1) if (h2 * 60 + m2) <= (h1 * 60 + m1) else date
            out.append(Punch(id=i * 2 + 2, employee_id=1,
                             ts=dt.datetime(end_day.year, end_day.month, end_day.day, h2, m2),
                             kind="OUT", source="web"))
    return out


def data_of(punches, date, shift, r, other_plans=None):
    """Локальный аналог day_pieces без БД: куски + календарные пересечения."""
    r = coerce_rules(r)
    ws, we = shift_window(shift, date, r) if shift and shift.kind == "work" else (None, None)
    other_plans = other_plans or {}
    sessions, warnings = pair_sessions(punches, r)
    pieces, worked, unclosed = [], [], False
    ds = dt.datetime(date.year, date.month, date.day)
    de = ds + dt.timedelta(days=1)
    for sess in sessions:
        rs = round_dt(sess["in"].ts, r["round_step_min"], r["round_mode"])
        auto = False
        if sess["out"] is None:
            if we and r["auto_close_missing_out"]:
                re_ = max(we, rs)
                auto = True
                unclosed = True
            else:
                unclosed = True
                continue
        else:
            re_ = round_dt(sess["out"].ts, r["round_step_min"], r["round_mode"])
        if re_ <= rs:
            continue
        inter = (max(rs, ds), min(re_, de))
        if inter[0] < inter[1]:
            worked.append(inter)
        windows = [(date, ws, we)] if ws else []
        for off, oshift in other_plans.items():
            ows, owe = shift_window(oshift, date + off, r) if oshift and oshift.kind == "work" else (None, None)
            if ows:
                windows.append((date + off, ows, owe))
        rem = [(rs, re_)]
        for wday, w_s, w_e in windows:
            new = []
            for a, b in rem:
                cut = (max(a, w_s), min(b, w_e))
                if cut[0] < cut[1]:
                    pieces.append({"start": cut[0], "end": cut[1], "kind": "plan", "day": wday,
                                   "sess_in": rs, "sess_out": re_, "raw_in": sess["in"].ts,
                                   "raw_out": sess["out"].ts if sess["out"] else None,
                                   "auto_closed": auto,
                                   "note": sess["out"].note if sess["out"] else ""})
                new += _subtract([(a, b)], (w_s, w_e))
            rem = new
        for a, b in rem:
            pieces.append({"start": a, "end": b, "kind": "cal", "day": rs.date(),
                           "sess_in": rs, "sess_out": re_, "raw_in": sess["in"].ts,
                           "raw_out": sess["out"].ts if sess["out"] else None,
                           "auto_closed": auto,
                           "note": sess["out"].note if sess["out"] else ""})
    for p in pieces:
        if p["kind"] != "cal":
            continue
        if ws and p["end"] <= ws and not r["count_early_arrival"]:
            p["drop"] = True
        if we and p["start"] >= we and not r["count_late_departure"]:
            p["drop"] = True
        if (p["end"] - p["start"]).total_seconds() / 60.0 < r["min_session_min"]:
            p["drop"] = True
    pieces = [p for p in pieces if not p.get("drop") and p["day"] == date]
    empty = {"entry": None, "shift": None, "ws": None, "we": None}
    plans = {date - dt.timedelta(days=1): dict(empty),
             date: {"entry": None, "shift": shift, "ws": ws, "we": we},
             date + dt.timedelta(days=1): dict(empty)}
    for off, oshift in (other_plans or {}).items():
        ows, owe = shift_window(oshift, date + off, r) if oshift and oshift.kind == "work" else (None, None)
        plans[date + off] = {"entry": None, "shift": oshift, "ws": ows, "we": owe}
    return {"pieces": pieces, "worked_cal": worked, "plans": plans,
            "warnings": warnings, "unclosed": unclosed}


def calc(emp, date, entry, punches, shift=None, other_plans=None, **kw):
    r = coerce_rules(rules(**kw))
    shift = shift if shift is not None else (entry.shift_type if entry else None)
    return compute_day(emp, date, entry, data_of(punches, date, shift, r, other_plans), r, shift=shift)


class TestRounding(unittest.TestCase):
    def test_round_nearest(self):
        base = dt.datetime(2026, 9, 22)
        self.assertEqual(round_dt(base.replace(hour=8, minute=12), 60, "nearest").hour, 8)
        self.assertEqual(round_dt(base.replace(hour=8, minute=30), 60, "nearest").hour, 9)
        self.assertEqual(round_dt(base.replace(hour=19, minute=50), 60, "nearest").hour, 20)

    def test_day_night_split(self):
        self.assertEqual(split_day_night(dt.datetime(2026, 9, 22, 20), dt.datetime(2026, 9, 23, 8),
                                         "22:00", "06:00"), (4.0, 8.0))
        self.assertEqual(split_day_night(dt.datetime(2026, 9, 22, 8), dt.datetime(2026, 9, 22, 20),
                                         "22:00", "06:00"), (12.0, 0.0))


class TestDayShift12(unittest.TestCase):
    def setUp(self):
        self.date = dt.date(2026, 9, 21)
        self.shift = make_shift("DAY12", "08:00–20:00", "08:00", "20:00")
        self.emp = make_emp()
        self.entry = ScheduleEntry(employee_id=1, date=self.date, shift_type=self.shift)

    def c(self, pairs, **kw):
        return calc(self.emp, self.date, self.entry, make_punches(self.date, pairs), **kw)

    def test_exact_shift(self):
        r = self.c([("08:00", "20:00")])
        self.assertEqual((r["planned_hours"], r["fact_hours"], r["status"]), (12.0, 12.0, "ok"))
        self.assertEqual((r["pay_ot_day"], r["pay_ot_night"]), (0.0, 0.0))

    def test_rounding_and_raw_marks(self):
        r = self.c([("08:12", "19:50")])
        self.assertEqual(r["fact_hours"], 12.0)
        self.assertEqual(r["fact_in"], dt.datetime(2026, 9, 21, 8, 12))   # точное время для менеджера
        self.assertEqual(r["fact_out"], dt.datetime(2026, 9, 21, 19, 50))
        self.assertEqual(r["status"], "ok")

    def test_overtime_and_payroll_split(self):
        r = self.c([("08:00", "23:00")])
        self.assertEqual(r["fact_hours"], 15.0)
        self.assertEqual(r["ot_hours"], 3.0)
        self.assertEqual((r["pay_ot_day"], r["pay_ot_night"]), (2.0, 1.0))  # 20–22 ДЯ, 22–23 ДН

    def test_late_and_early(self):
        r = self.c([("08:40", "19:10")])
        self.assertEqual(r["fact_hours"], 10.0)
        self.assertEqual(r["deficit_hours"], 2.0)
        self.assertEqual(r["late_hours"], 1.0)
        self.assertEqual(r["early_hours"], 1.0)
        self.assertEqual(r["status"], "late_early")

    def test_early_arrival_gate(self):
        self.assertEqual(self.c([("06:00", "20:00")])["fact_hours"], 12.0)
        r = self.c([("06:00", "20:00")], count_early_arrival=True)
        self.assertEqual(r["fact_hours"], 14.0)
        self.assertEqual(r["pay_ot_day"], 2.0)     # ранние часы видны в реестре в любом случае

    def test_no_punches_and_future(self):
        r = self.c([])
        self.assertEqual((r["status"], r["deficit_hours"]), ("no_punch", 12.0))
        future = local_date() + dt.timedelta(days=5)
        entry = ScheduleEntry(employee_id=1, date=future, shift_type=self.shift)
        rf = calc(self.emp, future, entry, [], shift=self.shift)
        self.assertEqual(rf["status"], "planned")

    def test_unclosed(self):
        r = self.c([("08:00", None)])
        self.assertEqual((r["status"], r["fact_hours"]), ("unclosed", 12.0))
        r2 = self.c([("08:00", None)], auto_close_missing_out=False)
        self.assertEqual(r2["fact_hours"], 0.0)

    def test_double_in_and_short_session(self):
        r = self.c([("08:00", None), ("11:00", "20:00")])
        self.assertEqual(r["fact_hours"], 12.0)
        r2 = self.c([("08:00", "20:00"), ("20:05", "20:10")])
        self.assertEqual(r2["fact_hours"], 12.0)   # 5-минутный огрызок игнорируется

    def test_ot_note(self):
        punches = make_punches(self.date, [("08:00", "22:30")])
        punches[-1].note = "Закрывал банкетный зал с Громовой"
        r = calc(self.emp, self.date, self.entry, punches, shift=self.shift)
        self.assertIn("банкетный", r["ot_note"])


class TestNightAndCalendarContour(unittest.TestCase):
    """Ночные смены: внутренний контур — к дате начала; внешний — по календарным дням."""

    def setUp(self):
        self.date = dt.date(2026, 9, 22)
        self.emp = make_emp()
        self.night = make_shift("NIGHT12", "20:00–08:00", "20:00", "08:00", overnight=True, tzh="Н")

    def test_plain_night(self):
        entry = ScheduleEntry(employee_id=1, date=self.date, shift_type=self.night)
        r = calc(self.emp, self.date, entry, make_punches(self.date, [("20:00", "08:00")]), shift=self.night)
        self.assertEqual((r["fact_hours"], r["night_hours"], r["day_hours"]), (12.0, 8.0, 4.0))
        # внешний контур: 01.09-аналог → ДЯ 2 (20–22) + ДН 2 (22–24)
        self.assertEqual((r["pay_ot_day"], r["pay_ot_night"]), (2.0, 2.0))

    def test_night_tail_lands_on_next_calendar_day(self):
        """Хвост ночной смены даёт начисления следующего календарного дня (ДН 6, ДЯ 2)."""
        nxt = self.date + dt.timedelta(days=1)
        off = make_shift("OFF", "Выходной", "", "", kind="absence", tzh="В", is_default_off=True)
        entry_next = ScheduleEntry(employee_id=1, date=nxt, shift_type=off)
        punches = make_punches(self.date, [("20:00", "08:00")])
        r_next = calc(self.emp, nxt, entry_next, punches, shift=off)
        self.assertEqual(r_next["fact_hours"], 0.0)          # внутренне день отдых
        self.assertEqual((r_next["pay_ot_day"], r_next["pay_ot_night"]), (2.0, 6.0))  # внешнему контуру — часы ночи

    def test_case1_day_plus_night(self):
        """Стоит ночь 22.09, отработал сутки: внутр. 24 ч и переработка 12 в дату начала;
        внешний контур: 22.09 ДЯ2 ДН2 + 23.09 ДН6 ДЯ2."""
        entry = ScheduleEntry(employee_id=1, date=self.date, shift_type=self.night)
        punches = make_punches(self.date, [("08:00", "08:00")])
        r = calc(self.emp, self.date, entry, punches, shift=self.night)
        # внутренние факт/банк: часы до начала ночной смены не входят (count_early_arrival=0);
        # они оплачены официальным дневным кодом, а ночные часы уходят в реестр по календарным дням
        self.assertEqual(r["fact_hours"], 12.0)
        self.assertEqual(r["ot_hours"], 0.0)
        self.assertEqual((r["pay_ot_day"], r["pay_ot_night"]), (2.0, 2.0))
        nxt = self.date + dt.timedelta(days=1)
        off = make_shift("OFF", "Выходной", "", "", kind="absence", tzh="В", is_default_off=True)
        entry_next = ScheduleEntry(employee_id=1, date=nxt, shift_type=off)
        r_next = calc(self.emp, nxt, entry_next, punches, shift=off)
        self.assertEqual((r_next["pay_ot_day"], r_next["pay_ot_night"]), (2.0, 6.0))

    def test_case2_night_then_day_back_to_back(self):
        """Ночь 22.09 + день 23.09 без перерыва: оба дня по 12 ч, без опозданий и переработок;
    ночные часы оформляются в реестре по календарным дням (ДЯ2 ДН2 / ДН6 ДЯ2)."""
        nxt = self.date + dt.timedelta(days=1)
        day = make_shift("DAY12", "08:00–20:00", "08:00", "20:00")
        entry_n = ScheduleEntry(employee_id=1, date=self.date, shift_type=self.night)
        entry_d = ScheduleEntry(employee_id=1, date=nxt, shift_type=day)
        punches = make_punches(self.date, [("20:00", "20:00")])   # уход следующие сутки в 20:00
        r1 = calc(self.emp, self.date, entry_n, punches, shift=self.night,
                  other_plans={dt.timedelta(days=1): day})
        r2 = calc(self.emp, nxt, entry_d, punches, shift=day,
                  other_plans={dt.timedelta(days=-1): self.night})
        self.assertEqual((r1["fact_hours"], r1["status"]), (12.0, "ok"))
        self.assertEqual((r2["fact_hours"], r2["status"]), (12.0, "ok"))
        self.assertEqual(r1["ot_hours"], 0.0)
        self.assertEqual(r2["ot_hours"], 0.0)
        # внешний контур: начисления по календарным дням…
        self.assertEqual((r1["pay_ot_day"], r1["pay_ot_night"]), (2.0, 2.0))
        self.assertEqual((r2["pay_ot_day"], r2["pay_ot_night"]), (2.0, 6.0))
        # …но официальное окно 01.09 (08:00–20:00) не отработано целиком = 12 ч списания,
        # которые в зачёте гасят эти начисления до нуля (кейс 2: переработок нет)
        self.assertEqual(r1["unused_hours"], 12.0)
        self.assertEqual(r2["unused_hours"], 0.0)
        log, remain, totals = settle_overtime(
            [{"date": "2026-09-01", "dya": r1["pay_ot_day"], "dn": r1["pay_ot_night"]},
             {"date": "2026-09-02", "dya": r2["pay_ot_day"], "dn": r2["pay_ot_night"]}],
            [{"date": "2026-09-01", "hours": r1["unused_hours"], "kind": "не отработано в окне"}])
        self.assertEqual(totals["pay_total"], 0.0)
        self.assertEqual(remain, [])


class TestAbsencesAndWorkOff(unittest.TestCase):
    def setUp(self):
        self.date = dt.date(2026, 9, 21)
        self.emp = make_emp()

    def test_work_on_day_off(self):
        off = make_shift("OFF", "Выходной", "", "", kind="absence", tzh="В", is_default_off=True)
        entry = ScheduleEntry(employee_id=1, date=self.date, shift_type=off)
        r = calc(self.emp, self.date, entry, make_punches(self.date, [("09:00", "21:00")]), shift=off)
        self.assertEqual((r["fact_hours"], r["ot_hours"], r["status"]), (12.0, 12.0, "work_off"))
        self.assertEqual((r["pay_ot_day"], r["pay_ot_night"]), (12.0, 0.0))

    def test_work_on_timeoff_cancels_writeoff(self):
        to = make_shift("TIMEOFF_HOURS", "Выходной за часы", "", "", kind="absence", tzh="НВ")
        entry = ScheduleEntry(employee_id=1, date=self.date, shift_type=to)
        r = calc(self.emp, self.date, entry, make_punches(self.date, [("08:00", "20:00")]), shift=to)
        self.assertEqual(r["timeoff_hours"], 0.0)
        self.assertEqual(r["status"], "work_off")

    def test_sick_punches_ignored(self):
        sick = make_shift("SICK", "Больничный", "", "", kind="absence", tzh="Б")
        entry = ScheduleEntry(employee_id=1, date=self.date, shift_type=sick)
        r = calc(self.emp, self.date, entry, make_punches(self.date, [("10:00", "14:00")]), shift=sick)
        self.assertEqual((r["fact_hours"], r["status"], r["pay_ot_day"]), (0.0, "absence", 0.0))

    def test_work_without_schedule(self):
        r = calc(self.emp, self.date, None, make_punches(self.date, [("09:00", "18:00")]))
        self.assertEqual((r["fact_hours"], r["code"], r["status"]), (9.0, "НЕ", "work_no_plan"))


class TestSettleWithDebt(unittest.TestCase):
    def test_day_first_within_month(self):
        credits = [{"date": "2026-09-01", "dya": 2.0, "dn": 2.0}, {"date": "2026-09-02", "dya": 2.0, "dn": 0.0}]
        debits = [{"date": "2026-09-05", "hours": 2.0, "kind": "Ранний уход"}]
        log, remain, totals = settle_overtime(credits, debits)
        self.assertEqual(log[0]["credit_date"], "2026-09-01")
        self.assertEqual(log[0]["from"], "ДЯ")
        self.assertEqual(totals["pay_dya"], 2.0)
        self.assertEqual(totals["pay_dn"], 2.0)

    def test_debt_carries_to_next_month(self):
        credits = [{"date": "2026-10-05", "dya": 3.0, "dn": 0.0}]
        debits = [{"date": "2026-09-10", "hours": 2.0, "kind": "Ранний уход"}]
        log, remain, totals = settle_overtime(credits, debits)
        self.assertEqual(totals["pay_dya"], 1.0)          # сентябрьский долг съел 2 ч октябрьской переработки
        self.assertEqual(totals["debt_out"], 0.0)
        self.assertTrue(any(x["kind"] == "Долг" for x in log))

    def test_extended_night_day_day(self):
        """День+ночь+день: начисления 01.09 ДЯ2 ДН2 и 02.09 ДЯ2 ДН6, списаний нет."""
        credits = [{"date": "2026-09-01", "dya": 2.0, "dn": 2.0},
                   {"date": "2026-09-02", "dya": 2.0, "dn": 6.0}]
        log, remain, totals = settle_overtime(credits, [])
        self.assertEqual(totals["pay_dya"], 4.0)
        self.assertEqual(totals["pay_dn"], 8.0)
        self.assertEqual([(r["date"], r["dya"], r["dn"]) for r in remain],
                         [("2026-09-01", 2.0, 2.0), ("2026-09-02", 2.0, 6.0)])

    def test_plain_night_day_no_entries(self):
        """Обычная ночная смена: официальное окно дня не отработано → начисления гасятся полностью."""
        credits = [{"date": "2026-09-01", "dya": 2.0, "dn": 2.0},
                   {"date": "2026-09-02", "dya": 2.0, "dn": 6.0}]
        debits = [{"date": "2026-09-01", "hours": 12.0, "kind": "не отработано в окне"}]
        _, remain, totals = settle_overtime(credits, debits)
        self.assertEqual(totals["pay_total"], 0.0)

    def test_uncovered_debt_becomes_debt(self):
        credits = []
        debits = [{"date": "2026-09-10", "hours": 2.0, "kind": "Опоздание"}]
        _, _, totals = settle_overtime(credits, debits)
        self.assertEqual(totals["debt_out"], 2.0)         # долг уйдёт в следующий месяц


class TestExtras(unittest.TestCase):
    def setUp(self):
        self.date = dt.date(2026, 9, 21)
        self.shift = make_shift("DAY12", "08:00–20:00", "08:00", "20:00")
        self.emp = make_emp()
        self.entry = ScheduleEntry(employee_id=1, date=self.date, shift_type=self.shift)

    def test_floor_rounding(self):
        r = calc(self.emp, self.date, self.entry, make_punches(self.date, [("08:12", "19:50")]),
                 shift=self.shift, round_mode="floor")
        self.assertEqual(r["fact_hours"], 11.0)
        self.assertEqual(r["deficit_hours"], 1.0)

    def test_grace_and_raw_late(self):
        r = calc(self.emp, self.date, self.entry, make_punches(self.date, [("08:03", "20:00")]), shift=self.shift)
        self.assertEqual(r["status"], "ok")
        r2 = calc(self.emp, self.date, self.entry, make_punches(self.date, [("08:03", "20:00")]),
                  shift=self.shift, grace_minutes=0, late_by_raw_time=True)
        self.assertEqual(r2["status"], "late")
        self.assertEqual(r2["fact_hours"], 12.0)

    def test_two_sessions_sum(self):
        r = calc(self.emp, self.date, self.entry,
                 make_punches(self.date, [("08:00", "12:00"), ("13:00", "20:00")]), shift=self.shift)
        self.assertEqual(r["fact_hours"], 11.0)
        self.assertEqual(r["deficit_hours"], 1.0)

    def test_timeoff_and_paid_off_absences(self):
        to = make_shift("TIMEOFF_HOURS", "Выходной за часы", "", "", kind="absence", tzh="НВ")
        e1 = ScheduleEntry(employee_id=1, date=self.date, shift_type=to)
        r1 = calc(self.emp, self.date, e1, [], shift=to)
        self.assertEqual((r1["timeoff_hours"], r1["status"]), (8.0, "absence"))
        po = make_shift("PAID_OFF", "Выходной оплачиваемый", "", "", kind="absence", tzh="ОВ")
        e2 = ScheduleEntry(employee_id=1, date=self.date, shift_type=po)
        r2 = calc(self.emp, self.date, e2, [], shift=po)
        self.assertEqual((r2["timeoff_hours"], r2["status"]), (0.0, "absence"))


class TestPatterns(unittest.TestCase):
    def test_nm_and_custom(self):
        self.assertEqual(pattern_days("4/3", dt.date(2026, 9, 1), 7),
                         [True, True, True, True, False, False, False])
        self.assertEqual(pattern_days("custom", dt.date(2026, 9, 1), 8, cycle="ВВРРРРВВ"),
                         [False, False, True, True, True, True, False, False])
        self.assertEqual(parse_custom_cycle("1 1 0 0"), [True, True, False, False])
        with self.assertRaises(ValueError):
            parse_custom_cycle("абракадабра")

    def test_5_2_custom_weekends(self):
        self.assertEqual(pattern_days("5/2", dt.date(2026, 9, 21), 7, off_weekdays=[0, 1]),
                         [False, False, True, True, True, True, True])


if __name__ == "__main__":
    unittest.main(verbosity=2)
