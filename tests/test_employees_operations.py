"""Сотрудники и документы — операции прикладного слоя (ADR-0013, раздел 4)."""
from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.core import errors
from app.core.identity import User
from app.modules.docs.application import statements
from app.modules.docs.application.catalog import StatementKind
from app.modules.employees.application import directory, lifecycle
from app.modules.people.application import Employee

NAME = "Проверкин Откат Транзакциевич"


@pytest.fixture()
def admin(db):
    from app.core.auth import Principal

    return Principal(db.scalar(select(User).where(User.username == "admin")), None)


def _count(app_stack, model, *where) -> int:
    with app_stack["SessionLocal"]() as other:        # другая сессия видит только зафиксированное
        return other.scalar(select(func.count()).select_from(model).where(*where))


def _hide(db, admin, employee_id: int) -> None:
    lifecycle.dismiss(db, admin, employee_id, None)
    directory.delete_employee(db, admin, employee_id)


def test_hiring_is_all_or_nothing(app_stack, db, admin, monkeypatch):
    """Приём создаёт сотрудника, учётную запись, должность, блок и период работы. Сбой на
    последнем шаге не оставляет ни одной из этих записей."""
    def broken_audit(*args, **kwargs):
        raise RuntimeError("журнал недоступен")

    users_before = _count(app_stack, User)
    monkeypatch.setattr(directory, "audit", broken_audit)
    with pytest.raises(RuntimeError):
        directory.create_employee(db, admin, directory.EmployeeIn(
            full_name=NAME, position="Батлер", schedule_group="Смена 1", username="proverkin_otkat"))
    monkeypatch.undo()
    assert _count(app_stack, Employee, Employee.full_name == NAME) == 0
    assert _count(app_stack, User) == users_before
    assert _count(app_stack, User, User.username == "proverkin_otkat") == 0


def test_hiring_returns_generated_password_once(app_stack, db, admin):
    created = directory.create_employee(db, admin, directory.EmployeeIn(full_name=NAME, position="Батлер"))
    try:
        assert created["username"] and created["role"] == "employee"
        assert len(created["initial_password"]) == 12
        own = directory.create_employee(db, admin, directory.EmployeeIn(full_name=NAME, password="Свой-Пароль-1"))
        try:
            assert own["initial_password"] is None and own["username"] != created["username"]
        finally:
            _hide(db, admin, own["id"])
        listed = next(e for e in directory.list_employees(db) if e["id"] == created["id"])
        assert "initial_password" not in listed
    finally:
        _hide(db, admin, created["id"])
    assert all(e["id"] != created["id"] for e in directory.list_employees(db))
    assert any(e["id"] == created["id"] and e["deleted"] for e in directory.list_employees(db, include_deleted=True))


@pytest.mark.parametrize("call, error, text", [
    (lambda db, p: directory.create_employee(db, p, directory.EmployeeIn(full_name="x", password="123")),
     errors.Validation, "Пароль слишком короткий"),
    (lambda db, p: directory.create_employee(db, p, directory.EmployeeIn(full_name="x", department_id=10**9)),
     errors.Validation, "Департамент не найден"),
    (lambda db, p: directory.create_employee(db, p, directory.EmployeeIn(full_name="x", role="нет-такой")),
     errors.Validation, "Неизвестная роль"),
    (lambda db, p: directory.update_employee(db, p, 10**9, directory.EmployeeIn(full_name="x")),
     errors.NotFound, "Сотрудник не найден"),
    (lambda db, p: directory.employee_history(db, 10**9), errors.NotFound, "Сотрудник не найден"),
    (lambda db, p: directory.delete_employee(db, p, 10**9), errors.NotFound, "Сотрудник не найден"),
    (lambda db, p: directory.create_department(db, p, directory.DepartmentIn(name=" ")),
     errors.Validation, "не может быть пустым"),
    (lambda db, p: directory.rename_subdivision(db, p, 10**9, directory.SubdivisionIn(name="x")),
     errors.NotFound, "Служба не найдена"),
    (lambda db, p: lifecycle.position_change(db, p, 10**9, "Батлер", None), errors.NotFound, "Сотрудник не найден"),
    (lambda db, p: statements.create_kind(db, p, statements.KindIn(code="1 плохой", name="x")),
     errors.Validation, "Код вида"),
    (lambda db, p: statements.update_kind(db, p, 10**9, statements.KindUpdate(name="x")),
     errors.NotFound, "Вид заявления не найден"),
    (lambda db, p: statements.sample(db, "нет"), errors.Validation, "Неизвестный вид заявления"),
    (lambda db, p: statements.upload_template(db, p, "vacation_paid", b"0" * (statements.TEMPLATE_MAX_BYTES + 1), "a.docx"),
     errors.PayloadTooLarge, "больше 5 МБ"),
    (lambda db, p: statements.render(db, p, statements.RenderIn(type="vacation_paid", employee_id=10**9,
                                                                 date_from="2026-11-20", date_to="2026-11-21")),
     errors.NotFound, "Сотрудник не найден"),
])
def test_refusal_is_typed_error(db, admin, call, error, text):
    with pytest.raises(error, match=text):
        call(db, admin)


def test_rejected_template_changes_nothing(app_stack, db, admin):
    """Файл, который не является .docx, отклоняется: бланка нет, записи аудита нет."""
    from app.core.audit import AuditLog
    from app.modules.docs.application.doc_render import template_path

    code = "proverka_blanka"
    statements.create_kind(db, admin, statements.KindIn(code=code, name="Проверка бланка"))
    kind_id = db.scalar(select(StatementKind.id).where(StatementKind.code == code))
    try:
        before = _count(app_stack, AuditLog, AuditLog.action == "doc_template_upload")
        with pytest.raises(errors.Validation, match="корректным .docx"):
            statements.upload_template(db, admin, code, b"ne docx", "z.txt")
        assert template_path(code) is None
        assert _count(app_stack, AuditLog, AuditLog.action == "doc_template_upload") == before
        content, name = statements.sample(db, code)
        meta = statements.upload_template(db, admin, code, content, "blank.docx")
        assert meta["type"] == code and template_path(code) is not None
        assert _count(app_stack, AuditLog, AuditLog.action == "doc_template_upload") == before + 1
    finally:
        statements.delete_kind(db, admin, kind_id)
    assert template_path(code) is None          # бланк удалён вместе с видом
    assert _count(app_stack, StatementKind, StatementKind.code == code) == 0


def test_pdf_failure_is_not_supported_and_still_audited(app_stack, db, admin, monkeypatch):
    from app.core.audit import AuditLog

    monkeypatch.setattr(statements, "docx_to_pdf", lambda docx, name: (None, "нет средства сборки"))
    employee_id = db.scalar(select(Employee.id).where(Employee.active.is_(True)).order_by(Employee.id))
    before = _count(app_stack, AuditLog, AuditLog.action == "doc_render")
    with pytest.raises(errors.NotSupported, match="PDF собрать не удалось") as exc:
        statements.render(db, admin, statements.RenderIn(type="vacation_paid", employee_id=employee_id,
                                                         date_from="2026-11-20", date_to="2026-11-21", format="pdf"))
    assert exc.value.status_code == 501
    assert _count(app_stack, AuditLog, AuditLog.action == "doc_render") == before + 1
