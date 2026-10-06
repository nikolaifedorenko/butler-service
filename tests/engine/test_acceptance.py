"""Приёмочные примеры Ф1–Ф39 спецификации v4 (раздел 11)."""
from __future__ import annotations

from dataclasses import replace

import pytest

from app.engine.domain.settings.types import Window, PlacementPolicy
from app.engine.domain.settings.validate import validate_settings
from app.engine.domain.types.errors import ConfigError, IncompletePeriodError

from .helpers import (EMP, H, IN, OUT, Adjustment, DeferredBlock, Period, absence, at, close_now, d, day,
                      double, flags, not_in_ut, pef, run, settings, shift, unpaid, ut)


def card(r, n, month=10):
    return next(c for c in r.cards if c.day == d(n, month))


def test_f1_daily_shift_over_midnight_double():
    st = settings(double(1), double(2))
    days = [day(1, "Я 12"), day(2, "В")]
    marks = [IN(1, 8), OUT(2, 8)]
    r = run(days, marks, st=st)
    c1, c2 = card(r, 1), card(r, 2)
    assert (c1.plan_minutes, c1.work_minutes, c1.debt_minutes) == (720, 720, 0)
    assert c1.codes == {"ДЯ 2": 120, "ДН 2": 120}
    assert (c2.plan_minutes, c2.work_minutes, c2.debt_minutes) == (0, 0, 0)
    assert c2.codes == {"ДН 2": 360, "ДЯ 2": 120}
    assert ut(r) == {d(1): {"ДЯ 2": 2, "ДН 2": 2}, d(2): {"ДН 2": 6, "ДЯ 2": 2}}
    assert r.bank_closed_minutes == 0
    sh = [shift(1, 8, 2, 8)]
    assert flags(days, marks, r, shifts=sh, st=st)[0] == []


def test_f2_evening_daily_debt_and_cascade():
    r = run([day(1, "Я 12"), day(2, "В")], [IN(1, 20), OUT(2, 20)])
    assert card(r, 1).debt_minutes == 720
    assert card(r, 1).codes == {"ДЯ": 120, "ДН": 120}
    assert card(r, 2).codes == {"ДН": 360, "ДЯ": 840}
    assert [(c.source_day, c.tariff, c.taken_minutes) for c in r.cuts] == [(d(1), "ДЯ", 120), (d(2), "ДЯ", 600)]
    assert ut(r) == {d(1): {"ДН": 2}, d(2): {"ДН": 6, "ДЯ": 4}}
    assert r.bank_closed_minutes == 0


F3_DAYS = [day(1, "Я 12"), day(2, "Я 12")]
F3_MARKS = [IN(1, 5), OUT(1, 10), IN(1, 19), OUT(2, 3), IN(2, 8), OUT(2, 23)]


def test_f3_several_sessions():
    r = run(F3_DAYS, F3_MARKS, st=settings(double(2)))
    c1, c2 = card(r, 1), card(r, 2)
    assert (c1.full_fact_minutes, c1.work_minutes, c1.debt_minutes) == (600, 180, 540)
    assert c1.codes == {"ДН": 180, "ДЯ": 240}
    assert (c2.full_fact_minutes, c2.work_minutes) == (1080, 720)
    assert c2.codes == {"ДН 2": 240, "ДЯ 2": 120}
    assert ut(r) == {d(2): {"ДН 2": 4, "ДЯ 2": 1}}
    assert r.bank_closed_minutes == 0


def test_f3b_bank_2h():
    r = run(F3_DAYS, F3_MARKS, bank=2, st=settings(double(2)))
    assert ut(r) == {d(2): {"ДН 2": 4, "ДЯ 2": 2}}
    assert r.bank_closed_minutes == 0


def test_f4_cascade_from_settings():
    days = [day(1, "Я 12"), day(2, "В"), day(3, "В")]
    marks = [IN(1, 8), OUT(1, 10), IN(2, 20), OUT(2, 24), IN(3, 21), OUT(3, 24)]
    r = run(days, marks, bank=2, st=settings(double(3)))
    assert card(r, 2).codes == {"ДЯ": 120, "ДН": 120}
    assert card(r, 3).codes == {"ДЯ 2": 60, "ДН 2": 120}
    assert r.paid_with_bank_minutes == 120
    assert [(c.tariff, c.taken_minutes, c.paid_minutes) for c in r.cuts] == [
        ("ДЯ", 120, 120), ("ДН", 120, 120), ("ДЯ 2", 60, 120), ("ДН 2", 60, 120)]
    assert ut(r) == {d(3): {"ДН 2": 1}}
    assert r.bank_closed_minutes == 0
    assert sum(c.taken_minutes for c in r.cuts) == 360 and sum(c.paid_minutes for c in r.cuts) == 480
    assert r.total_debt_minutes == r.paid_with_bank_minutes + 480 + r.residual_debt_minutes == 600


F5_MARKS = [IN(1, 8), OUT(2, 8, 2)]


def test_f5_transfer_from_non_accepting_day():
    days = [day(1, "Я 12"), day(2, "ОТ"), day(3, "В")]
    r = run(days, F5_MARKS)
    assert card(r, 2).codes == {"ДН": 360, "ДЯ": 120}
    placed = [x.data for x in r.trace if x.code == "CODE_PLACED"]
    assert [(p["tariff"], p["placed_day"], p["minutes"]) for p in placed] == [("ДЯ", d(3), 120), ("ДН", d(3), 360)]
    assert ut(r) == {d(1): {"ДЯ": 2, "ДН": 2}, d(3): {"ДН": 6, "ДЯ": 2}}
    assert r.bank_closed_minutes == 0
    got, fr = flags(days, F5_MARKS, r)
    review = [f for f in fr.flags if f.code == "ACTIVITY_REQUIRES_REVIEW"]
    assert [(f.day, f.data["at_utc"]) for f in review] == [(d(2), at(2, 8, 2))]


def test_f5b_no_receiver():
    r = run([day(1, "Я 12"), day(2, "ОТ")], F5_MARKS)
    assert [(b.source_day, b.tariff, b.minutes) for b in r.deferred_blocks] == [(d(2), "ДЯ", 120), (d(2), "ДН", 360)]
    assert [e.code for e in r.exceptions] == ["NO_RECEIVER", "NO_RECEIVER"]
    assert ut(r) == {d(1): {"ДЯ": 2, "ДН": 2}}
    assert r.bank_closed_minutes == 0


def test_f6_weekend_work_not_in_schedule():
    days = [day(3, "В")]
    marks = [IN(3, 8), OUT(3, 20)]
    r = run(days, marks)
    assert ut(r) == {d(3): {"ДЯ": 12}} and r.bank_closed_minutes == 0
    got, fr = flags(days, marks, r, shifts=[])
    assert got == [(d(3), "OFF_SHIFT_ATTENDANCE")]
    assert fr.flags[0].data["first_presence_at"] == at(3, 8)


def test_f7_late_and_left_later_double():
    days = [day(1, "Я 12")]
    marks = [IN(1, 9, 15), OUT(1, 23, 35)]
    st = settings(double(1))
    r = run(days, marks, bank=6, st=st)
    c = card(r, 1)
    assert (c.full_fact_minutes, c.work_minutes, c.debt_minutes) == (900, 660, 60)
    assert c.codes == {"ДЯ 2": 120, "ДН 2": 120}
    assert r.bank_closed_minutes == 300
    assert ut(r) == {d(1): {"ДЯ 2": 2, "ДН 2": 2}}
    got, fr = flags(days, marks, r, st=st)
    assert got == [(d(1), "LATE")]
    assert fr.flags[0].data == {"expected_at": at(1, 8), "actual_at": at(1, 9, 15)}


def test_f8_debt_exceeds_bank_and_codes():
    days = [day(1, "Я 12"), day(2, "Я 12")]
    r = run(days, bank=3)
    assert r.total_debt_minutes == 1440 and r.paid_with_bank_minutes == 180
    assert r.residual_debt_minutes == 1260 and r.bank_closed_minutes == -1260
    assert flags(days, (), r)[0] == [(d(1), "MISSED_DAY"), (d(2), "MISSED_DAY")]


def test_f9_cap_24h_skips_full_day():
    days = [day(1, "ОТ"), day(2, "Я 12"), day(3, "В")]
    marks = [IN(1, 8), OUT(1, 20), IN(2, 0), OUT(2, 24)]
    r = run(days, marks)
    assert card(r, 2).plan_minutes + sum(card(r, 2).codes.values()) == 1440
    assert ut(r) == {d(2): {"ДН": 8, "ДЯ": 4}, d(3): {"ДЯ": 12}}
    got, _ = flags(days, marks, r)
    assert got.count((d(1), "ACTIVITY_REQUIRES_REVIEW")) == 2


def test_f9b_wrong_window_length():
    st = settings()
    bad = dict(st.windows)
    bad["Я 12"] = Window("Я", 720, ((480, 840),))
    with pytest.raises(ConfigError) as e:
        validate_settings(replace(st, windows=bad))
    assert any(code == "V2" for code, _ in e.value.violations)


def test_f10_plan_equals_fact():
    r = run([day(1, "Я 12")], st=settings(pef(1)))
    c = card(r, 1)
    assert (c.plan_minutes, c.debt_minutes, c.codes, c.plan_equals_fact_applied) == (0, 0, {}, True)
    assert [x.code for x in r.trace] == ["PLAN_EQUALS_FACT"]
    assert flags([day(1, "Я 12")], (), r, st=settings(pef(1)))[0] == []
    r2 = run([day(1, "Я 12")], [IN(1, 8), OUT(1, 20)], st=settings(pef(1)))
    assert card(r2, 1).plan_minutes == 720
    r3 = run([day(1, "Я 12")], [], st=settings(pef(1)), opening=IN(30, 20, month=9))
    assert card(r3, 1).plan_minutes == 720 and not card(r3, 1).plan_equals_fact_applied
    r4 = run([day(1, "К 12")])
    assert card(r4, 1).plan_minutes == 0
    r5 = run([day(1, "Я 12", group="Пятидневка")], st=settings(group="Пятидневка"))
    assert card(r5, 1).plan_minutes == 0


def test_f11_period_boundary():
    sep = run([day(30, "Н 4", month=9)], [IN(30, 20, month=9)], mode="view", now=at(1, 9),
              period=Period(d(30, 9), d(30, 9)))
    c = sep.cards[0]
    assert (c.work_minutes, c.debt_minutes, c.open_at_end) == (240, 0, True)
    octo = run([day(1, "Н 8")], [OUT(1, 8)], opening=IN(30, 20, month=9))
    c = octo.cards[0]
    assert (c.open_at_start, c.work_minutes, c.debt_minutes) == (True, 480, 0)
    assert octo.deferred_blocks == ()


def test_f12_new_tabel_value_is_settings_row():
    st0 = settings()
    codes = {k: v for k, v in st0.day_codes.items() if k != "Н"}
    windows = {k: v for k, v in st0.windows.items() if not k.startswith("Н ")}
    bare = replace(st0, day_codes=codes, windows=windows)
    with pytest.raises(Exception):
        run([day(1, "Н 4")], st=bare)
    st = replace(bare, day_codes=st0.day_codes, windows={**windows, "Н 4": st0.windows["Н 4"],
                                                          "Н 8": st0.windows["Н 8"]})
    validate_settings(st)
    r = run([day(1, "Н 4"), day(2, "Н 8")], [IN(1, 20), OUT(2, 8)], st=st)
    assert [c.debt_minutes for c in r.cards] == [0, 0]
    r2 = run([day(1, "Н 4"), day(2, "Н 8")], [IN(1, 20), OUT(2, 10)], st=st)
    assert ut(r2) == {d(2): {"ДЯ": 2}}


def test_f13_unpaid_overtime_to_bank_by_weight():
    r = run([day(1, "В")], [IN(1, 8), OUT(1, 20)], st=settings(double(1), unpaid(1)))
    assert ut(r) == {} and r.bank_closed_minutes == 24 * H
    assert r.credited_to_bank_minutes == 24 * H


def test_f13b_unpaid_covers_other_day_debt():
    days = [day(1, "В"), day(2, "Я 12")]
    st = settings(double(1), unpaid(1))
    r = run(days, [IN(1, 8), OUT(1, 20)], st=st)
    assert ut(r) == {} and r.bank_closed_minutes == 12 * H and r.paid_with_bank_minutes == 12 * H
    assert flags(days, [IN(1, 8), OUT(1, 20)], r, st=st)[0] == [(d(1), "OFF_SHIFT_ATTENDANCE"), (d(2), "MISSED_DAY")]


def test_f14_manual_bank_adjustment():
    r = run([day(1, "Я 12")], [IN(1, 8), OUT(1, 20)], adjustments=[Adjustment(-4 * H, "manual")])
    assert r.bank_closed_minutes == -4 * H
    base = run([day(1, "Я 12")], [IN(1, 8), OUT(1, 20)])
    assert base.cards == r.cards


def test_f15_empty_day_inside_open_session():
    days = [day(5, "В"), day(6, "В"), day(7, "В")]
    r = run(days, [IN(5, 20), OUT(7, 8)])
    assert card(r, 5).codes == {"ДЯ": 120, "ДН": 120}
    assert card(r, 6).codes == {"ДН": 480, "ДЯ": 960}
    assert card(r, 7).codes == {"ДН": 360, "ДЯ": 120}
    assert card(r, 6).open_at_start and card(r, 7).open_at_start
    assert r.bank_closed_minutes == 0


def test_f16_view_vs_close():
    days, marks = [day(1, "Я 12"), day(2, "В")], [IN(1, 20), OUT(2, 20)]
    v, c = run(days, marks, mode="view"), run(days, marks, mode="close")
    assert ut(v) == {d(1): {"ДЯ": 2, "ДН": 2}, d(2): {"ДЯ": 14, "ДН": 6}}
    assert ut(c) == {d(1): {"ДН": 2}, d(2): {"ДЯ": 4, "ДН": 6}}
    assert v.residual_debt_minutes == 720 and v.cuts == ()
    assert sum(x.taken_minutes for x in c.cuts) == 720
    assert v.bank_closed_minutes == c.bank_closed_minutes == 0


def test_f17_granule_more_expensive_than_rest():
    r = run([day(1, "Я 12"), day(2, "В")], [IN(1, 8), OUT(1, 19), IN(2, 22), OUT(2, 24)], st=settings(double(2)))
    assert r.cuts == () and ut(r) == {d(2): {"ДН 2": 2}}
    assert r.residual_debt_minutes == 60 and r.bank_closed_minutes == -60


def test_f18_granule_fits_exactly():
    r = run([day(1, "Я 12"), day(2, "В")], [IN(1, 8), OUT(1, 18), IN(2, 20), OUT(2, 21)], st=settings(double(2)))
    assert [(c.taken_minutes, c.paid_minutes) for c in r.cuts] == [(60, 120)]
    assert ut(r) == {} and r.residual_debt_minutes == 0 and r.bank_closed_minutes == 0


def test_f18b_debt_3_codes_2():
    r = run([day(1, "Я 12"), day(2, "В")], [IN(1, 8), OUT(1, 17), IN(2, 20), OUT(2, 22)], st=settings(double(2)))
    assert ut(r) == {d(2): {"ДЯ 2": 1}} and r.bank_closed_minutes == -60


def test_f19_queue_t6_decides():
    days = [day(1, "Я 12"), day(2, "В"), day(3, "В")]
    marks = [IN(1, 8), OUT(1, 18), IN(2, 20), OUT(2, 22), IN(3, 20), OUT(3, 21)]
    r = run(days, marks, st=settings(double(3)))
    assert [(c.source_day, c.tariff, c.taken_minutes) for c in r.cuts] == [(d(2), "ДЯ", 120)]
    assert ut(r) == {d(3): {"ДЯ 2": 1}} and r.bank_closed_minutes == 0


def test_f20_negative_bank_on_input():
    days = [day(1, "Я 12")]
    r = run(days, bank=-1)
    assert (r.total_debt_minutes, r.paid_with_bank_minutes, r.residual_debt_minutes) == (780, 0, 780)
    assert r.bank_closed_minutes == -780
    assert flags(days, (), r)[0] == [(d(1), "MISSED_DAY")]


def test_f21_cheap_and_expensive_code():
    days = [day(1, "Я 12"), day(2, "В"), day(3, "В")]
    marks = [IN(1, 8), OUT(1, 19), IN(2, 20), OUT(2, 21), IN(3, 20), OUT(3, 21)]
    r = run(days, marks, st=settings(double(3)))
    assert [(c.source_day, c.tariff, c.taken_minutes) for c in r.cuts] == [(d(2), "ДЯ", 60)]
    assert ut(r) == {d(3): {"ДЯ 2": 1}} and r.bank_closed_minutes == 0


def test_f22_cascade_bank_code_rest():
    r = run([day(1, "Я 12"), day(2, "В")], [IN(1, 8), OUT(1, 13), IN(2, 21), OUT(2, 23)], bank=4,
            st=settings(double(2)))
    assert card(r, 2).codes == {"ДЯ 2": 60, "ДН 2": 60}
    assert ut(r) == {d(2): {"ДН 2": 1}} and r.bank_closed_minutes == -60
    assert (r.paid_with_bank_minutes, sum(c.paid_minutes for c in r.cuts), r.residual_debt_minutes) == (240, 120, 60)


def test_f23_no_out_mark():
    days = [day(1, "Я 12")]
    a = run(days, [IN(1, 8)], mode="view", now=at(2, 9))
    c = a.cards[0]
    assert (c.full_fact_minutes, c.work_minutes, c.debt_minutes) == (960, 720, 0)
    assert ut(a) == {d(1): {"ДЯ": 2, "ДН": 2}} and a.open_session_since_utc == at(1, 8)
    got, _ = flags(days, [IN(1, 8)], a, now=at(2, 9))
    assert (d(1), "SESSION_OPEN") in got
    b = run(days, [IN(1, 8)], mode="view", now=at(1, 18))
    c = b.cards[0]
    assert (c.full_fact_minutes, c.work_minutes, c.debt_minutes) == (600, 600, 120)
    got, _ = flags(days, [IN(1, 8)], b, now=at(1, 18))
    assert (d(1), "SESSION_OPEN") in got


def test_f24_day_off_for_hours():
    days = [day(5, "Я 12")]
    r = run(days, mode="view")
    assert (r.cards[0].debt_minutes) == 720
    assert flags(days, (), r, absences=[absence(5, 8, 20)])[0] == []
    assert run(days).bank_closed_minutes == -720


def test_f24b_came_anyway():
    days, marks = [day(5, "Я 12")], [IN(5, 8), OUT(5, 20)]
    r = run(days, marks)
    c = r.cards[0]
    assert (c.full_fact_minutes, c.work_minutes, c.debt_minutes, c.codes) == (720, 720, 0, {})
    got, fr = flags(days, marks, r, absences=[absence(5, 8, 20)])
    assert got == [(d(5), "OFF_SHIFT_ATTENDANCE")]
    assert fr.flags[0].data["absence_intervals"] == ((480, 1200),)


def test_f25_absence_in_middle_of_shift():
    days = [day(5, "Я 12")]
    marks = [IN(5, 8), OUT(5, 11, 40), IN(5, 15, 30), OUT(5, 20)]
    r = run(days, marks)
    c = r.cards[0]
    assert (c.full_fact_minutes, c.work_minutes, c.debt_minutes, c.overtime_minutes) == (480, 480, 240, 0)
    got, fr = flags(days, marks, r, absences=[absence(5, 12, 15)])
    assert sorted(code for _, code in got) == ["ABSENCE_GAP", "EARLY_DEPARTURE", "LATE"]
    by = {f.code: f.data for f in fr.flags}
    assert by["ABSENCE_GAP"] == {"gap_start": 720, "expected_return": 900}
    assert by["EARLY_DEPARTURE"]["actual_at"] == at(5, 11, 40)
    assert by["LATE"] == {"expected_at": at(5, 15), "actual_at": at(5, 15, 30)}


def test_f26_several_absences():
    days = [day(5, "Я 12")]
    marks = [IN(5, 8), OUT(5, 20)]
    got, _ = flags(days, [IN(5, 8), OUT(5, 10), IN(5, 11), OUT(5, 14), IN(5, 15), OUT(5, 20)],
                   absences=[absence(5, 10, 11), absence(5, 14, 15)])
    assert got.count((d(5), "ABSENCE_GAP")) == 2
    assert not any(c in ("LATE", "EARLY_DEPARTURE") for _, c in got)
    got, _ = flags(days, [IN(5, 9), OUT(5, 9, 30)], absences=[absence(5, 10, 11), absence(5, 14, 15)])
    assert got.count((d(5), "LATE")) == 1 and got.count((d(5), "EARLY_DEPARTURE")) == 1
    assert marks


def test_f27_did_not_come():
    days = [day(1, "Я 12")]
    r = run(days)
    assert r.cards[0].debt_minutes == 720 and r.bank_closed_minutes == -720
    assert flags(days, (), r)[0] == [(d(1), "MISSED_DAY")]


def test_f28_night_shift_codes_stuck_in_vacation_day():
    days = [day(1, "Н 4"), day(2, "ОТ"), day(3, "В")]
    marks = [IN(1, 20), OUT(2, 8)]
    r = run(days, marks)
    assert card(r, 1).codes == {} and card(r, 1).debt_minutes == 0
    assert ut(r) == {d(3): {"ДН": 6, "ДЯ": 2}} and r.bank_closed_minutes == 0
    got, _ = flags(days, marks, r)
    assert (d(2), "ACTIVITY_REQUIRES_REVIEW") in got


def test_f29_day_debt_paid_by_bank_codes_stay():
    days = [day(1, "Я 12"), day(2, "ОТ"), day(3, "В")]
    r = run(days, [IN(1, 20), OUT(2, 8)], bank=20, st=settings(double(1)))
    assert ut(r) == {d(1): {"ДЯ 2": 2, "ДН 2": 2}, d(3): {"ДН": 6, "ДЯ": 2}}
    assert r.bank_closed_minutes == 8 * H and r.cuts == ()


def test_f30_deferred_from_previous_period():
    days = [day(1, "Я 12"), day(2, "В"), day(3, "В")]
    r = run(days, [IN(1, 8), OUT(1, 20)], deferred=[DeferredBlock(d(29, 9), "ДН", 360, "NO_RECEIVER")])
    assert ut(r) == {d(1): {"ДН": 6}} and r.bank_closed_minutes == 0 and r.deferred_blocks == ()


def test_f31_deferred_without_receiver():
    days = [day(1, "Я 12"), day(2, "Я 12")]
    r = run(days, [IN(1, 0), OUT(2, 24)], deferred=[DeferredBlock(d(29, 9), "ДН", 720, "NO_RECEIVER")])
    assert [(b.source_day, b.tariff, b.minutes) for b in r.deferred_blocks] == [(d(29, 9), "ДН", 720)]
    assert [e.code for e in r.exceptions] == ["NO_RECEIVER"]
    assert ut(r) == {d(1): {"ДН": 8, "ДЯ": 4}, d(2): {"ДН": 8, "ДЯ": 4}} and r.bank_closed_minutes == 0


def test_f32_mark_beyond_period_after_rounding():
    days = [day(31, "В")]
    p = Period(d(31), d(31))
    marks = [IN(31, 20), OUT(1, 0, 20, month=11)]
    r = run(days, marks, period=p, now=at(1, 12, month=11))
    c = r.cards[0]
    assert c.codes == {"ДЯ": 120, "ДН": 120} and not c.open_at_end and r.open_session_since_utc is None
    bad = run(days, marks[:1], period=p, now=at(1, 12, month=11))
    assert bad.cards[0].open_at_end and bad.open_session_since_utc == at(31, 20)


def test_f33_now_rounding():
    days = [day(1, "Я 12")]
    a = run(days, [IN(1, 15, 40)], mode="view", now=at(1, 15, 45))
    assert (a.cards[0].full_fact_minutes, a.cards[0].debt_minutes) == (0, 720)
    got, fr = flags(days, [IN(1, 15, 40)], a, now=at(1, 15, 45))
    assert sorted(c for _, c in got) == ["LATE", "SESSION_OPEN"]
    by = {f.code: f.data for f in fr.flags}
    assert by["LATE"]["actual_at"] == at(1, 15, 40) and by["SESSION_OPEN"]["open_since"] == at(1, 15, 40)
    b = run(days, [IN(1, 15, 40)], mode="view", now=at(1, 23, 40))
    c = b.cards[0]
    assert (c.full_fact_minutes, c.work_minutes, c.debt_minutes, c.codes) == (480, 240, 480, {"ДЯ": 120, "ДН": 120})
    with pytest.raises(IncompletePeriodError):
        run(days, [IN(1, 15, 40)], mode="close", now=at(1, 23, 40))


def test_f34_night_flags_by_raw_presence():
    days = [day(1, "Н 4"), day(2, "Н 8")]
    sh = [shift(1, 20, 2, 8)]
    marks = [IN(1, 20, 3), OUT(2, 7, 58)]
    r = run(days, marks)
    assert [c.debt_minutes for c in r.cards] == [0, 0] and [c.full_fact_minutes for c in r.cards] == [240, 480]
    assert flags(days, marks, r, shifts=sh)[0] == []
    marks2 = [IN(1, 20, 20), OUT(2, 7, 58)]
    r2 = run(days, marks2)
    assert r2.cards == r.cards
    assert flags(days, marks2, r2, shifts=sh)[0] == [(d(1), "LATE")]


F35_DAYS = [day(1, "ОТ"), day(2, "Я 12")]
F35_MARKS = [IN(1, 18), OUT(1, 24), IN(2, 2), OUT(2, 24)]


def test_f35_blocks_compete_for_capacity():
    r = run(F35_DAYS, F35_MARKS)
    assert card(r, 1).codes == {"ДЯ": 240, "ДН": 120}
    assert card(r, 2).codes == {"ДН": 360, "ДЯ": 240}
    assert ut(r) == {d(2): {"ДН": 6, "ДЯ": 6}}
    assert [(b.source_day, b.tariff, b.minutes) for b in r.deferred_blocks] == [(d(1), "ДЯ", 120), (d(1), "ДН", 120)]
    assert [e.code for e in r.exceptions] == ["NO_RECEIVER", "NO_RECEIVER"]
    st = settings()
    st = replace(st, placement=PlacementPolicy(("ДН", "ДЯ", "ДЯ 2", "ДН 2")))
    r2 = run(F35_DAYS, F35_MARKS, st=st)
    assert ut(r2) == {d(2): {"ДН": 8, "ДЯ": 4}}
    assert [(b.source_day, b.tariff, b.minutes) for b in r2.deferred_blocks] == [(d(1), "ДЯ", 240)]


def test_f36_excluded_from_ut_goes_to_bank():
    days = [day(4, "В"), day(5, "Б")]
    marks = [IN(4, 8), OUT(4, 12), IN(5, 10), OUT(5, 12)]
    r = run(days, marks, st=settings(not_in_ut(4)))
    assert ut(r) == {} and r.bank_closed_minutes == 6 * H
    assert [x.code for x in r.trace].count("UNPAID_CREDITED") == 2
    got, _ = flags(days, marks, r, st=settings(not_in_ut(4)))
    assert got.count((d(5), "ACTIVITY_REQUIRES_REVIEW")) == 2
    r2 = run(days, marks, st=settings(not_in_ut(4), double(4)))
    assert r2.bank_closed_minutes == 10 * H


def test_f37_foreign_block_skips_excluded_day():
    days = [day(1, "ОТ"), day(2, "В"), day(3, "В")]
    r = run(days, [IN(1, 20), OUT(1, 22)], st=settings(not_in_ut(2)))
    assert ut(r) == {d(3): {"ДЯ": 2}} and r.bank_closed_minutes == 0


def test_f38_window_off_grid():
    st = settings()
    w = dict(st.windows)
    w["Я 9"] = Window("Я", 540, ((570, 1110),))
    with pytest.raises(ConfigError) as e:
        validate_settings(replace(st, windows=w))
    assert {c for c, _ in e.value.violations} == {"V10"}
    validate_settings(replace(st, windows=w, step_minutes=30))


F39_DAYS = [day(1, "Я 12"), day(2, "ОТ"), day(3, "Я 12")]
F39_MARKS = [IN(1, 8), OUT(1, 18), IN(2, 22), OUT(2, 24), IN(3, 0), OUT(3, 24)]


def test_f39_replacement_after_cascade():
    c = run(F39_DAYS, F39_MARKS)
    assert ut(c) == {d(3): {"ДН": 10, "ДЯ": 2}} and c.deferred_blocks == () and c.bank_closed_minutes == 0
    after = [x.data for x in c.trace if x.code == "CODE_PLACED" and x.data["pass"] == "after_cascade"]
    assert [(a["source_day"], a["placed_day"], a["minutes"]) for a in after] == [(d(2), d(3), 120)]
    v = run(F39_DAYS, F39_MARKS, mode="view")
    assert ut(v) == {d(3): {"ДН": 8, "ДЯ": 4}}
    assert [(b.source_day, b.tariff, b.minutes) for b in v.deferred_blocks] == [(d(2), "ДН", 120)]
    assert v.total_debt_minutes == 120


def test_close_now_helper():
    assert close_now(Period(d(1), d(1))) == at(2, 0)
    assert EMP and H
