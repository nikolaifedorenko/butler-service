"""Архитектурные тесты ВСЕХ модулей (EXECUTION-SPEC-v2, DoD фазы 9/C7):
структура 5 слоёв, правила §3 (R1 изоляция домена, направления слоёв),
R6 (кросс-модульные FK строкой; relationship — только внутри модуля или
на core; кросс-модульных связей нет — allowlist пуст с 20.10.2026) и публичная граница notify (R4).

Обобщение эталонных проверок модуля notify (tests/test_notify_module.py, фаза
C3) на все 9 модулей + core. Законы расчётного движка v7.1 (чистота домена,
независимость конвейеров, размер файлов) — в tests/engine/test_architecture.py;
они строже этих и остаются там (спецификация overtime_spec_v7_1_final.md, 13 п.5).

Проверяются AST'ом — без запуска приложения.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
# модули — по манифестам (ADR-0012): новый модуль попадает в проверки без правки этого файла
MODULES = tuple(sorted(p.parent.name for p in (ROOT / "app" / "modules").glob("*/manifest.py")))
LAYERS = ("domain", "application", "ports", "adapters", "interface")

# stdlib-корни, разрешённые домену/портам (sqlalchemy/fastapi/httpx/smtplib —
# только в адаптерах и выше)
STDLIB_OK = {"__future__", "dataclasses", "datetime", "json", "re", "types",
             "typing", "unicodedata", "collections", "zoneinfo"}

# ORM-файлы для проверок R6 (модели живут только здесь + core)
ORM_FILES = [
    "app/core/identity.py",
    "app/core/audit.py",
    "app/core/media.py",
    "app/core/settings_store.py",
    "app/modules/timesheet/adapters/orm.py",
    "app/modules/employees/adapters/orm.py",
    "app/modules/night/adapters/orm.py",
    "app/modules/cars/adapters/orm.py",
    "app/modules/notify/adapters/orm.py",
]

# R6 (батч 20.10.2026 — долг ЗАКРЫТ): кросс-модульных relationship() больше нет.
# Допустимы: связи внутри своего unit (модуль; для core — весь core как одна
# инфраструктурная единица) и связи модуль → core (core импортируется всеми
# легально; R5 ограничивает лишь обратное направление). Список ниже ПУСТ и
# обязан таким оставаться: новая кросс-модульная связь падает тестом.
CROSS_RELATIONSHIPS: dict[tuple[str, str], str] = {}

# Исключения СВОЕГО модуля (не кросс-модульные — те легальны по R3 и прикрыты
# private-контрактами import-linter). Всё — изначальная архитектура движка v7.1,
# перенесённая «как есть» (§4: логика не переписывается); собственные AST-законы
# движка (tests/engine/test_architecture.py) адаптеры исторически не проверяли:
#   factory.py        — собирает порты через application.context (composition
#                       адаптерной фабрики — так было в app/engine);
#   sql_bank/sql_closings — month_period из application.months;
#   sql_closings      — serialize/deserialize сохранённых срезов периода
#                       (хранилище знает формат представления);
#   sql_timesheet     — чистые хелперы базового графика (долг C2, §12).
# Кандидаты на распутывание в продуктовом батче «порты/DTO» (после C7).
ADAPTERS_TO_APPLICATION_EXCEPTIONS = {
    "timesheet": {"sql_timesheet.py", "factory.py", "sql_bank.py", "sql_closings.py"},
}
ADAPTERS_TO_INTERFACE_EXCEPTIONS = {"timesheet": {"sql_closings.py"}}


def _mod_root(name: str) -> pathlib.Path:
    return ROOT / "app" / "modules" / name


def _py_files(root: pathlib.Path) -> list[pathlib.Path]:
    if not root.exists():
        return []
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


# ── структура: 5 слоёв у каждого модуля (§1: имена слоёв обязательны) ────────

@pytest.mark.parametrize("mod", MODULES)
def test_module_has_five_layers_with_inits(mod):
    root = _mod_root(mod)
    for layer in LAYERS:
        assert (root / layer).is_dir(), f"{mod}: нет слоя {layer}/"
        assert (root / layer / "__init__.py").is_file(), f"{mod}: нет {layer}/__init__.py"
    assert (root / "__init__.py").is_file(), f"{mod}: нет публичной границы"


# ── §3/R1: чистота домена и портов ───────────────────────────────────────────

@pytest.mark.parametrize("mod", MODULES)
def test_domain_is_pure(mod):
    """domain/: stdlib (+ app.core.errors по §3) и свой домен; без I/O,
    без системного времени, без вышележащих слоёв."""
    offenders = []
    own = f"app.modules.{mod}.domain"
    for path in _py_files(_mod_root(mod) / "domain"):
        for imp in _imports(path):
            root = imp.split(".")[0]
            ok = root in STDLIB_OK or imp.startswith(own) or imp == "app.core.errors"
            if not ok:
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


@pytest.mark.parametrize("mod", MODULES)
def test_ports_import_only_stdlib_domain_core(mod):
    offenders = []
    for path in _py_files(_mod_root(mod) / "ports"):
        for imp in _imports(path):
            root = imp.split(".")[0]
            ok = (root in STDLIB_OK or imp.startswith("app.core")
                  or imp.startswith(f"app.modules.{mod}.domain")
                  or imp.startswith(f"app.modules.{mod}.ports"))
            if not ok:
                offenders.append((str(path), imp))
    assert offenders == []


# ── §3: направления между слоями ─────────────────────────────────────────────

@pytest.mark.parametrize("mod", MODULES)
def test_application_does_not_import_interface(mod):
    offenders = []
    for path in _py_files(_mod_root(mod) / "application"):
        for imp in _imports(path):
            if "interface" in imp.split("."):
                offenders.append((str(path), imp))
    assert offenders == []


@pytest.mark.parametrize("mod", MODULES)
def test_adapters_do_not_import_own_interface(mod):
    """Кросс-модульные interface-импорты запрещают private-контракты lint-imports;
    здесь — закон СВОЕГО модуля (кроме задокументированных исключений движка)."""
    allowed = ADAPTERS_TO_INTERFACE_EXCEPTIONS.get(mod, set())
    own = f"app.modules.{mod}.interface"
    offenders = []
    for path in _py_files(_mod_root(mod) / "adapters"):
        if path.name in allowed:
            continue
        for imp in _imports(path):
            if imp.startswith(own):
                offenders.append((str(path), imp))
    assert offenders == []


@pytest.mark.parametrize("mod", MODULES)
def test_adapters_do_not_import_own_application(mod):
    """Кросс-модульный импорт чужого application из adapters — R3-легально
    (публичная граница); запрещён только СВОЙ application (слой ниже), кроме
    задокументированных исключений движка."""
    allowed = ADAPTERS_TO_APPLICATION_EXCEPTIONS.get(mod, set())
    own = f"app.modules.{mod}.application"
    offenders = []
    for path in _py_files(_mod_root(mod) / "adapters"):
        if path.name in allowed:
            continue
        for imp in _imports(path):
            if imp.startswith(own):
                offenders.append((str(path), imp))
    assert offenders == []


@pytest.mark.parametrize("mod", MODULES)
def test_domain_and_ports_do_not_import_adapters(mod):
    offenders = []
    for layer in ("domain", "ports"):
        for path in _py_files(_mod_root(mod) / layer):
            for imp in _imports(path):
                if "adapters" in imp.split("."):
                    offenders.append((str(path), imp))
    assert offenders == []


# ── R6: модели — кросс-модульные FK строкой, relationship по allowlist ───────

def _unit_of(path: pathlib.Path) -> str:
    parts = path.relative_to(ROOT).parts
    if parts[1] == "core":
        return "core"
    return parts[2]  # app/modules/<mod>/...


def test_r6_fk_are_strings_and_relationships_allowlisted():
    found_cross: dict[tuple[str, str], str] = {}
    # классы unit'а: core — все core-файлы (одна инфраструктурная единица),
    # модуль — его orm; цели «свой unit» и «core» легальны для всех
    unit_classes: dict[str, set] = {}
    for rel in ORM_FILES:
        tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
        unit_classes.setdefault(_unit_of(ROOT / rel), set()).update(
            n.name for n in tree.body if isinstance(n, ast.ClassDef))
    core_classes = unit_classes.get("core", set())
    for rel in ORM_FILES:
        path = ROOT / rel
        tree = ast.parse(path.read_text(encoding="utf-8"))
        unit = _unit_of(path)
        local = unit_classes[unit] | core_classes
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
                if name == "ForeignKey":
                    assert node.args and isinstance(node.args[0], ast.Constant) \
                        and isinstance(node.args[0].value, str), \
                        f"{rel}: ForeignKey не строкой: {ast.dump(node)[:120]}"
        for cls in [n for n in tree.body if isinstance(n, ast.ClassDef)]:
            for st in cls.body:
                if not (isinstance(st, ast.AnnAssign) and isinstance(st.value, ast.Call)):
                    continue
                fname = getattr(st.value.func, "id", None) or getattr(st.value.func, "attr", None)
                if fname != "relationship":
                    continue
                ann = ast.unparse(st.annotation)
                target = ann
                for wrap in ("Mapped[", "list[", "Optional[", "]"):
                    target = target.replace(wrap, "")
                if target in local:
                    continue
                found_cross[(unit, f"{cls.name}.{st.target.id}")] = target
    assert found_cross == CROSS_RELATIONSHIPS, (
        "появились кросс-модульные relationship (R6 закрыт батчем 20.10.2026 — "
        f"список обязан быть пустым): {found_cross}")


# ── R4: публичная граница notify сохраняет поверхность бывшей app/notify ─────

def test_notify_public_init_keeps_legacy_surface():
    import app.modules.notify as notify

    expected = {"DEFAULT_TEMPLATES", "DOMAIN_TITLES", "NOTIFY_KEYS", "PLACEHOLDERS",
                "NotifyConfig", "load_config", "mask_secret", "public_config",
                "render_template", "save_config", "template_of"}
    assert set(notify.__all__) == expected
    for name in expected:
        assert getattr(notify, name, None) is not None, name


# ── DoD «TZ/now — только core/time.py»: системное время в модулях запрещено ──

# Единственное разрешённое чтение системного времени в модулях: now_utc() —
# composition-параметр движка (§5.1/F-15: `now` снимается здесь и передаётся
# в use case'ы параметром). Всё остальное — local_date()/now_local()/utc_to_local()
# из app.core.time (TZ объекта из APP_TZ, а не TZ сервера).
SYSTEM_TIME_ALLOWLIST = {
    "app/modules/timesheet/application/engine_common.py": {"now"},
}


@pytest.mark.parametrize("mod", MODULES)
def test_no_system_time_reads_in_modules(mod):
    offenders = []
    for path in _py_files(_mod_root(mod)):
        allowed = SYSTEM_TIME_ALLOWLIST.get(path.relative_to(ROOT).as_posix(), set())
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                    and node.func.attr in ("now", "today") \
                    and node.func.attr not in allowed:
                offenders.append((path.relative_to(ROOT).as_posix(), node.func.attr,
                                  node.lineno))
    assert offenders == [], (
        "системное время мимо core/time (долг №3 закрыт 20.10.2026 — не открывать): "
        f"{offenders}")


# ── ADR-0012: каждый модуль описан манифестом, и регистрация берёт всё из него ──

def test_every_module_has_manifest_and_registers_itself():
    from app.bootstrap import modules, registry
    from app.core import manifest
    from app.core.permissions import ALL_KEYS

    registry.wire()

    packages = {p.name for p in (ROOT / "app" / "modules").iterdir()
                if p.is_dir() and (p / "__init__.py").exists()}
    assert set(MODULES) == packages, "у модуля нет manifest.py"
    found = modules.discover()
    assert {m.name for m in found} == packages | {"core"}
    keys = [p.key for m in found for p in m.permissions]
    assert len(keys) == len(set(keys)), "одно право объявлено двумя модулями"
    assert keys == ALL_KEYS and manifest.registered() == found


def test_menu_and_settings_screens_match_frontend():
    """Шаг 5.4: пункты меню и экраны Настроек объявлены в манифестах. Их права есть в каталоге,
    id не повторяются, экраны одной группы идут подряд, и у каждого пункта есть регистрация
    во фронтенде (registerModule) — иначе пункт открыл бы заглушку «Раздел не найден»."""
    import itertools
    import re

    from app.bootstrap import registry
    from app.core import manifest
    from app.core.permissions import ALL_KEYS

    registry.wire()
    ui = manifest.ui_for(set(ALL_KEYS))
    menu, screens = ui["menu"], ui["settings_screens"]
    used = {p for i in menu for p in i["perms"]} | {s["perm"] for s in screens if s["perm"]}
    assert used <= set(ALL_KEYS), used - set(ALL_KEYS)
    groups = [g for g, _ in itertools.groupby(s["group"] for s in screens)]
    assert len(groups) == len(set(groups)), f"группа экранов разорвана: {groups}"
    js = "".join(p.read_text(encoding="utf-8") for p in (ROOT / "static" / "js").rglob("*.js"))
    calls = "".join(re.findall(r"registerModule\(\{.*?\}\);", js, re.S))
    for kind, items in (("views", menu), ("screens", screens)):
        ids = [i["id"] for i in items]
        assert len(ids) == len(set(ids)), f"{kind}: повтор id"
        missing = [i for i in ids if not re.search(rf"\b{i}\s*:", calls)]
        assert not missing, f"{kind} без registerModule во фронтенде: {missing}"
