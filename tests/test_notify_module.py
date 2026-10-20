"""Архитектурные тесты модуля notify — «проверка эталона» (EXECUTION-SPEC-v2,
фаза 5/C3): структура 5 слоёв, правила §3 (R1 изоляция домена, слои импортов),
R6 (кросс-модульные FK строкой, relationship только внутри модуля) и публичная
граница R4. Проверяются AST'ом — без запуска приложения.

Законы движка v7.1 (tests/engine/test_architecture.py) специфичны для timesheet;
здесь — общие законы модуля, которые в C7 станут шаблоном для всех остальных
(employees, night, cars, docs, settings, access, audit).
"""
from __future__ import annotations

import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
NOTIFY = ROOT / "app" / "modules" / "notify"
LAYERS = ("domain", "application", "ports", "adapters", "interface")

# stdlib-корни, разрешённые домену/портам (всё остальное — sqlalchemy, fastapi,
# httpx, smtplib-обёртки и app.* — в домене запрещены; smtplib/httpx живут в адаптерах)
STDLIB_OK = {"__future__", "dataclasses", "datetime", "json", "re", "typing"}


def _py_files(root: pathlib.Path) -> list[pathlib.Path]:
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def _module_of(path: pathlib.Path) -> str:
    return ".".join(path.relative_to(ROOT).with_suffix("").parts)


def _resolve(node: ast.ImportFrom, module: str) -> str:
    if node.level == 0:
        return node.module or ""
    parts = module.split(".")[:-1]
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


# ── структура (термины §1: имена слоёв обязательны) ──────────────────────────

def test_module_has_five_layers_with_inits():
    for layer in LAYERS:
        assert (NOTIFY / layer).is_dir(), f"нет слоя {layer}/"
        assert (NOTIFY / layer / "__init__.py").is_file(), f"нет {layer}/__init__.py"
    assert (NOTIFY / "__init__.py").is_file(), "нет публичной границы модуля"


# ── R1 / §3: чистота домена и портов ─────────────────────────────────────────

def test_domain_is_pure():
    """domain/: только stdlib; никакого I/O (sqlalchemy/fastapi/httpx/smtplib),
    никаких app.* и вышележащих слоёв; системное время не читается."""
    offenders = []
    for path in _py_files(NOTIFY / "domain"):
        for imp in _imports(path):
            root = imp.split(".")[0]
            if root not in STDLIB_OK and not imp.startswith("app.modules.notify.domain"):
                offenders.append((str(path), imp))
            if any(part in imp.split(".") for part in
                   ("application", "adapters", "interface", "ports")):
                offenders.append((str(path), imp))
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
                if name in ("now", "today", "print", "input", "open"):
                    offenders.append((str(path), name))
    assert offenders == []


def test_ports_import_nothing_but_stdlib_domain_core():
    offenders = []
    for path in _py_files(NOTIFY / "ports"):
        for imp in _imports(path):
            root = imp.split(".")[0]
            ok = root in STDLIB_OK or imp.startswith("app.core.") \
                or imp.startswith("app.modules.notify.domain") \
                or imp.startswith("app.modules.notify.ports")
            if not ok:
                offenders.append((str(path), imp))
    assert offenders == []


# ── §3: направление зависимостей между слоями ────────────────────────────────

def test_application_does_not_import_interface():
    offenders = []
    for path in _py_files(NOTIFY / "application"):
        for imp in _imports(path):
            if "interface" in imp.split("."):
                offenders.append((str(path), imp))
    assert offenders == []


def test_adapters_do_not_import_interface_or_application():
    offenders = []
    for path in _py_files(NOTIFY / "adapters"):
        for imp in _imports(path):
            parts = imp.split(".")
            if "interface" in parts or "application" in parts:
                offenders.append((str(path), imp))
    assert offenders == []


def test_domain_and_ports_do_not_import_adapters():
    offenders = []
    for layer in ("domain", "ports"):
        for path in _py_files(NOTIFY / layer):
            for imp in _imports(path):
                if "adapters" in imp.split("."):
                    offenders.append((str(path), imp))
    assert offenders == []


# ── R6: модели — кросс-модульные FK строкой, relationship только свои ────────

def test_orm_r6_fk_strings_and_no_cross_relationships():
    """adapters/orm.py: ForeignKey(...) — только строковый литерал (FK на таблицы
    других модулей не создают python-зависимостей); relationship() у моделей
    notify нет вовсе (журнал ссылаются на службы/пользователей по id)."""
    path = NOTIFY / "adapters" / "orm.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if name == "ForeignKey":
                assert node.args and isinstance(node.args[0], ast.Constant) \
                    and isinstance(node.args[0].value, str), \
                    f"ForeignKey не строкой: {ast.dump(node)[:120]}"
            if name == "relationship":
                raise AssertionError(
                    "relationship() в notify/adapters/orm.py: кросс-модульные связи "
                    "запрещены (R6); внутри модуля relationship не используются")


# ── R4: публичная граница модуля ─────────────────────────────────────────────

def test_public_init_keeps_legacy_surface():
    """__init__ модуля сохраняет публичную поверхность бывшей app/notify —
    legacy-потребители и будущие модули импортируют с границы пакета."""
    import app.modules.notify as notify

    expected = {"DEFAULT_TEMPLATES", "DOMAIN_TITLES", "NOTIFY_KEYS", "PLACEHOLDERS",
                "NotifyConfig", "load_config", "mask_secret", "public_config",
                "render_template", "save_config", "template_of"}
    assert set(notify.__all__) == expected
    for name in expected:
        assert getattr(notify, name, None) is not None, name
