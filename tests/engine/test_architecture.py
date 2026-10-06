"""Архитектурные законы: граф импортов, чистота домена, нет литералов бизнес-кодов (13.5)."""
from __future__ import annotations

import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2] / "app" / "engine"
DOMAIN = ROOT / "domain"
BUSINESS = {"Я", "К", "В", "ДО", "ОТ", "ОВ", "Б", "НБ", "НН", "Н", "ДЯ", "ДН", "ДЯ 2", "ДН 2",
            "Смена 1", "Смена 2", "Пятидневка", "Другие смены"}


def _files(base):
    return [p for p in base.rglob("*.py")]


def _imports(path):
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            yield ("." * node.level) + (node.module or "")
        elif isinstance(node, ast.Import):
            yield from (a.name for a in node.names)


def test_domain_imports_nothing_outside():
    for p in _files(DOMAIN):
        for mod in _imports(p):
            parts = set(mod.lstrip(".").split("."))
            assert not parts & {"application", "adapters", "interface", "ports", "sqlalchemy", "fastapi", "app"}, (p, mod)
            assert not mod.startswith("...."), (p, mod)


def test_ports_only_protocols_and_domain():
    for p in _files(ROOT / "ports"):
        for mod in _imports(p):
            assert not any(x in mod for x in ("adapters", "application", "interface", "sqlalchemy")), (p, mod)


def test_application_does_not_know_adapters():
    for p in _files(ROOT / "application"):
        for mod in _imports(p):
            assert "adapters" not in mod and "sqlalchemy" not in mod, (p, mod)


def test_no_clock_io_print_logging_in_domain():
    banned = ("datetime.now", "date.today", "print(", "logging", "open(", "os.environ", ".utcnow")
    for p in _files(DOMAIN):
        text = p.read_text()
        for b in banned:
            assert b not in text, (p, b)


def test_no_business_literals_in_domain_comparisons():
    for p in _files(DOMAIN):
        if p.name == "defaults.py":
            continue
        tree = ast.parse(p.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                assert node.value not in BUSINESS, (p, node.value)


def test_settle_does_not_import_flags():
    text = (DOMAIN / "pipeline" / "settle.py").read_text()
    assert "flags" not in "".join(l for l in text.splitlines() if l.startswith(("from", "import")))


def test_one_public_function_per_file():
    allowed_multi = {"entities.py", "results.py", "errors.py", "types.py", "defaults.py", "codes.py",
                     "reason_codes.py", "flag_codes.py", "invariant_codes.py", "settle.py",
                     "evaluate_flags.py", "shift_segments.py", "resolve_modifier.py"}
    for p in _files(DOMAIN):
        if p.name in allowed_multi or p.name == "__init__.py":
            continue
        tree = ast.parse(p.read_text())
        public = [n.name for n in tree.body if isinstance(n, ast.FunctionDef) and not n.name.startswith("_")]
        assert len(public) <= 1, (p, public)


def test_function_size_and_nesting():
    for p in _files(DOMAIN):
        if p.name in ("settle.py", "evaluate_flags.py", "codes.py", "defaults.py"):
            continue
        tree = ast.parse(p.read_text())
        for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
            body_lines = fn.end_lineno - fn.lineno
            assert body_lines <= 22, (p, fn.name, body_lines)
