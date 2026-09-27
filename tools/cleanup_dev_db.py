#!/usr/bin/env python3
"""Одноразовая чистка dev-базы timetrack.db от остатков смоук-тестов (аудит 27.09.2026).

Удаляет:
  1. bank_adjustments id=1 — корректировка «−2 ч Иванову» (остаток смоука, искажала банк);
  2. soft-deleted тестовых сотрудников id 11/13/14 («Демонов», «Временев», «Тестов Отмет»)
     вместе с их punches / timesheet_rows / schedule_entries / users / employment_periods /
     block_assignments / position_history / emergency_contacts / bank_adjustments;
  3. архивную тестовую смену TMP_TEST (id 15) и её ревизии.

Перед изменениями делает резервную копию файла БД. Каждое удаление сверяет с ожидаемыми
данными из аудита — при любом расхождении прекращает работу без изменений.
"""
import shutil
import sqlite3
import sys
import time

DB = "timetrack.db"

EXPECT_EMPLOYEES = {11: "Демонов", 13: "Временев", 14: "Тестов"}
EXPECT_ADJ = (1, 4, -2.0)   # id, employee_id, hours
EXPECT_TMP_SHIFT = (15, "TMP_TEST")


def main() -> int:
    backup = f"{DB}.bak-{time.strftime('%Y%m%d-%H%M%S')}"
    shutil.copyfile(DB, backup)
    print(f"резервная копия: {backup}")

    con = sqlite3.connect(DB)
    con.execute("PRAGMA foreign_keys=ON")
    cur = con.cursor()

    # ── сверка ожидаемого состояния ──
    adj = cur.execute("SELECT id, employee_id, hours FROM bank_adjustments WHERE id=1").fetchone()
    if adj and adj != EXPECT_ADJ:
        print(f"СТОП: bank_adjustments id=1 = {adj}, ожидалось {EXPECT_ADJ}")
        return 1
    emps = dict(cur.execute("SELECT id, full_name FROM employees WHERE id IN (11,13,14)").fetchall())
    for eid, frag in EXPECT_EMPLOYEES.items():
        if eid in emps and frag not in emps[eid]:
            print(f"СТОП: сотрудник {eid} = {emps[eid]!r}, ожидалось вхождение {frag!r}")
            return 1
    tmp = cur.execute("SELECT id, code FROM shift_types WHERE code='TMP_TEST'").fetchone()
    if tmp and tuple(tmp) != EXPECT_TMP_SHIFT:
        print(f"СТОП: TMP_TEST = {tmp}, ожидалось {EXPECT_TMP_SHIFT}")
        return 1

    ids = [eid for eid in EXPECT_EMPLOYEES if eid in emps]
    qm = ",".join("?" * len(ids)) if ids else "NULL"

    deleted = {}

    def wipe(table: str, where: str, params: list) -> None:
        n = cur.execute(f"DELETE FROM {table} WHERE {where}", params).rowcount
        if n:
            deleted[table] = deleted.get(table, 0) + n

    if ids:
        for t in ("punches", "timesheet_rows", "schedule_entries", "employment_periods",
                  "block_assignments", "position_history", "emergency_contacts",
                  "bank_adjustments", "shift_revisions", "vip_double_pay"):
            cols = [c[1] for c in cur.execute(f"PRAGMA table_info({t})")]
            if "employee_id" in cols:
                wipe(t, f"employee_id IN ({qm})", ids)
        # аудит тестовых пользователей: обнуляем ссылку, историю оставляем
        cur.execute(f"UPDATE audit_log SET actor_id=NULL "
                    f"WHERE actor_id IN (SELECT id FROM users WHERE employee_id IN ({qm}))", ids)
        wipe("users", f"employee_id IN ({qm})", ids)
        wipe("employees", f"id IN ({qm})", ids)

    if adj:
        wipe("bank_adjustments", "id=?", [1])
    if tmp:
        wipe("shift_revisions", "shift_type_id=?", [tmp[0]])
        wipe("shift_types", "id=?", [tmp[0]])

    con.commit()
    cur.execute("VACUUM")
    con.commit()

    print("удалено строк по таблицам:")
    for t, n in sorted(deleted.items()):
        print(f"  {t}: {n}")
    left = cur.execute("SELECT COUNT(*) FROM employees WHERE deleted_at IS NOT NULL").fetchone()[0]
    print(f"soft-deleted сотрудников осталось: {left}")
    print(f"bank_adjustments осталось: {cur.execute('SELECT COUNT(*) FROM bank_adjustments').fetchone()[0]}")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
