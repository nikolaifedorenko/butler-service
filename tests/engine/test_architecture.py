"""Архитектурные тесты (13 п.5, base 2.1/2.4, 8.1): граф импортов, чистота домена,
независимость конвейеров вкладок. Проверяются AST'ом — без запуска приложения."""
from __future__ import annotations

import ast
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
ENGINE = ROOT / "app" / "modules" / "timesheet"   # фаза C2: бывший app/engine
DOMAIN = ENGINE / "domain"

BUSINESS_CODES = {"Я", "К", "В", "ДО", "ОТ", "ОВ", "Б", "НБ", "НН",
                  "ДЯ", "ДН", "ДЯ2", "ДН2", "Смена 1", "Смена 2", "Пятидневка"}
FORBIDDEN_DOMAIN_MODULES = ("application", "adapters", "interface", "ports")
DIRTY_CALLS = {"now", "today"}          # datetime.now() / date.today()

# Фаза C2 (EXECUTION-SPEC-v2 §7, §11.2 G3): легаси-хелперы, поглощённые модулем
# «как есть» (логика не переписывалась). Им разрешены ТРАНЗИТНЫЕ импорты:
# собственный слой adapters (ORM-модели) и ещё не перенесённые app-модули
# (groups/employment — уедут в modules/employees в фазе C4, тогда список пустеет).
# Файлы самого движка остаются полностью чистыми: закон для них не ослаблен.
TRANSIT_APPLICATION_FILES = {"base_schedule.py", "tabel_fill.py", "schedule_helpers.py",
                             "doublepay.py", "engine_common.py", "punch_plan.py"}
TRANSIT_APP_PREFIXES = ("app.groups", "app.employment")


def _py_files(root: pathlib.Path):
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def _module_of(path: pathlib.Path) -> str:
    rel = path.relative_to(ROOT).with_suffix("")
    return ".".join(rel.parts)


def _resolve(node: ast.ImportFrom, module: str) -> str:
    if node.level == 0:
        return node.module or ""
    parts = module.split(".")[:-1]                    # пакет файла
    if node.level > 1:
        parts = parts[: -(node.level - 1)]
    return ".".join(parts + ([node.module] if node.module else []))


def _imports(path: pathlib.Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            out.append(_resolve(node, _module_of(path)))
    return out


# ── граф импортов: домен не знает никого (2.1) ────────────────────────────────

def test_domain_imports_nothing_above():
    offenders = []
    for path in _py_files(DOMAIN):
        for imp in _imports(path):
            if any(part in imp.split(".") for part in FORBIDDEN_DOMAIN_MODULES):
                offenders.append((str(path), imp))
    assert offenders == []


def test_application_does_not_import_adapters_or_interface():
    offenders = []
    for path in _py_files(ENGINE / "application"):
        transit = path.name in TRANSIT_APPLICATION_FILES
        for imp in _imports(path):
            parts = imp.split(".")
            if "interface" in parts or "adapters" in parts and not transit or imp.startswith("app.") and "timesheet" not in parts \
                    and not imp.startswith("app.core.") \
                    and not (transit and imp.startswith(TRANSIT_APP_PREFIXES)):
                offenders.append((str(path), imp))
    assert offenders == []


def test_ports_import_only_typing_and_domain():
    offenders = []
    for path in _py_files(ENGINE / "ports"):
        for imp in _imports(path):
            parts = imp.split(".")
            if imp.startswith("app.modules.timesheet") and "domain" not in parts and "ports" not in parts:
                offenders.append((str(path), imp))
    assert offenders == []


# ── чистота домена (2.4) ──────────────────────────────────────────────────────

def test_domain_has_no_system_time_io_print():
    offenders = []
    for path in _py_files(DOMAIN):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                fn = node.func
                name = getattr(fn, "attr", None) or getattr(fn, "id", None)
                if name in DIRTY_CALLS:
                    offenders.append((str(path), name))
                if name in ("print", "input", "open"):
                    offenders.append((str(path), name))
        for imp in _imports(path):
            if imp.split(".")[0] in ("logging", "os", "sys", "random", "socket",
                                     "sqlalchemy", "fastapi", "requests"):
                offenders.append((str(path), imp))
    assert offenders == []


def test_domain_has_no_business_code_literals():
    """Литералы бизнес-кодов — только settings/defaults.py (12.4)."""
    allowed = DOMAIN / "settings" / "defaults.py"
    offenders = []
    for path in _py_files(DOMAIN):
        if path == allowed:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if node.value in BUSINESS_CODES:
                    offenders.append((str(path), node.value))
    assert offenders == []


# ── независимость конвейеров (2.1, 16.1) ──────────────────────────────────────

def test_settle_does_not_import_flags():
    imports = _imports(DOMAIN / "pipeline" / "settle.py")
    assert not any(".flags" in imp or imp.endswith("flags") for imp in imports)


def test_flags_do_not_import_daycard_or_settleresult():
    for path in _py_files(DOMAIN / "flags"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                names = [a.name for a in node.names]
                assert "DayCard" not in names, str(path)
                assert "SettleResult" not in names, str(path)
                resolved = _resolve(node, _module_of(path))
                assert "day_card" not in resolved.split("."), (str(path), resolved)


def test_flags_input_from_hours_pipeline_is_mapping_only():
    """Единственный вход из часового конвейера — plan_equals_fact: Mapping[date, bool]
    (6.6, 13 п.5): в сигнатуре evaluate_flags нет карточек/банка/кодов/долга."""
    source = (DOMAIN / "flags" / "evaluate_flags.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "evaluate_flags")
    params = [a.arg for a in fn.args.args]
    assert params == ["period", "days", "plan_equals_fact", "marks", "opening_mark",
                      "shifts", "absences", "st", "now"]


def test_board_and_sessions_are_independent():
    forbidden = ("pipeline", "placement", "bank", "day_card", "flags")
    for folder in ("board", "sessions"):
        for path in _py_files(DOMAIN / folder):
            for imp in _imports(path):
                parts = imp.split(".")
                assert not any(f in parts for f in forbidden), (str(path), imp)


def test_board_uses_only_schedule_from_domain():
    for path in _py_files(DOMAIN / "board"):
        for imp in _imports(path):
            if imp.startswith("app.modules.timesheet.domain"):
                tail = imp.split(".")
                assert tail[-2] in ("board", "schedule", "settings", "time", "types",
                                    "codes_registry"), (str(path), imp)


# ── интерфейс: человекочитаемые тексты только здесь (2.4) ────────────────────

def test_domain_produces_no_human_text():
    """В домене нет русских строк вне defaults.py и docstring/комментариев:
    проверяем строковые константы — только коды реестров и технические значения."""
    allowed_files = {DOMAIN / "settings" / "defaults.py"}
    offenders = []
    for path in _py_files(DOMAIN):
        if path in allowed_files:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        docstrings = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                body = getattr(node, "body", [])
                if body and isinstance(body[0], ast.Expr) \
                        and isinstance(body[0].value, ast.Constant) \
                        and isinstance(body[0].value.value, str):
                    docstrings.add(id(body[0].value))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                    and id(node) not in docstrings:
                value = node.value
                if any("\u0400" <= ch <= "\u04ff" for ch in value):
                    offenders.append((str(path), value))
    assert offenders == []


def test_every_domain_function_file_is_small():
    """Инженерная дисциплина (2.2): файл домена — одна функция/класс; грубая проверка
    размера против функций-комбайнов (12.1). Модули типов и справочников — исключение
    («Dataclass-структуры объединяются в модули», 2.9)."""
    exempt = {DOMAIN / "types" / "entities.py", DOMAIN / "types" / "results.py",
              DOMAIN / "types" / "errors.py", DOMAIN / "types" / "immutable.py",
              DOMAIN / "settings" / "types.py", DOMAIN / "settings" / "defaults.py"}
    big = []
    for path in _py_files(DOMAIN):
        if path in exempt:
            continue
        lines = len(path.read_text(encoding="utf-8").splitlines())
        if lines > 120:
            big.append((str(path.relative_to(ROOT)), lines))
    assert big == [], f"слишком большие файлы домена: {big}"


@pytest.mark.parametrize("folder", ["types", "codes_registry", "settings", "validation",
                                    "time", "sessions", "presence", "day_card", "placement",
                                    "opening", "bank", "schedule", "flags", "board",
                                    "checks", "reports", "pipeline"])
def test_catalog_folders_exist(folder):
    assert (DOMAIN / folder).is_dir(), folder
