"""Граница будущих модулей внутри ``stays`` (ADR-0013, шаг 5): fund → guests → stays → board.

Файлы прикладного слоя, предметной области и портов разнесены по четырём группам — будущим
модулям. Группа импортирует только свою и нижние: так деление на модули (5б–5г) сводится к
переносу файлов, а не к разрыву зависимостей. Тест уйдёт, когда группы станут настоящими
модулями и их слои закрепит import-linter.
"""
from __future__ import annotations

import ast
from pathlib import Path

STAYS = Path(__file__).resolve().parents[2] / "app" / "modules" / "stays"

ORDER = {"fund": 0, "guests": 1, "stays": 2, "board": 3}

GROUPS: dict[str, str] = {}


def _group(group: str, names: str) -> None:
    for name in names.split():
        GROUPS[name] = group


# ── fund: объекты, категории, версии фонда, файл фонда ──────────────────────
_group("fund", "application/fund application/fund_versions application/fund_drafts application/fund_xlsx "
               "application/fund_forms application/fund_screen application/fund_draft_edit "
               "application/fund_dictionaries application/catalog application/locking domain/halfday")
# ── guests: профили, связи, пожелания, VIP-коды, настраиваемые поля ─────────
_group("guests", "application/guests application/vip_codes application/family application/guest_forms "
                 "application/guest_fields domain/kinship domain/prefs")
# ── stays: брони, блоки, OOO, размещение, покрытие, начальная загрузка ──────
_group("stays", "application/allocation application/blocks application/block_edit application/ooo "
                "application/ooo_edit application/reservations application/reservation_edit "
                "application/reservation_forms application/coverage application/coverage_edit "
                "application/coverage_forms application/context application/preview application/previewed "
                "application/stays_directories application/stays_catalog application/fund_reset "
                "application/fund_admin application/fund_publish application/demo application/guest_edit "
                "application/guest_access application/guest_card application/guest_merge application/mine "
                "application/history application/guests_list application/visibility application/view_filters "
                "domain/allocate domain/blocks domain/candidates domain/coverage domain/escort domain/load "
                "domain/types domain/warnings ports/duty")
# ── board: представления только для чтения ──────────────────────────────────
_group("board", "application/views application/boards application/bookings application/booking_screen "
                "application/export application/export_screen application/board_screen "
                "application/mine_screen application/view_screen application/guest_screen")


def _imports(path: Path, rel: str):
    package = rel.split("/")[0]
    for node in ast.walk(ast.parse(path.read_text())):
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.level == 1 and node.module:                 # from .name import x
            yield f"{package}/{node.module.split('.')[0]}"
        elif node.level == 1:                               # from . import name
            yield from (f"{package}/{a.name}" for a in node.names)
        elif node.level == 2 and node.module:               # from ..domain.name import x
            parts = node.module.split(".")
            if parts[0] in ("domain", "ports", "application") and len(parts) > 1:
                yield f"{parts[0]}/{parts[1]}"
            elif parts[0] in ("domain", "ports", "application"):
                yield from (f"{parts[0]}/{a.name}" for a in node.names)


def _files():
    for sub in ("application", "domain", "ports"):
        for path in sorted((STAYS / sub).glob("*.py")):
            if path.stem != "__init__":
                yield f"{sub}/{path.stem}", path


def test_every_file_has_a_group():
    missing = [rel for rel, _ in _files() if rel not in GROUPS]
    assert missing == [], f"добавьте файлы в группы: {missing}"
    stale = sorted(set(GROUPS) - {rel for rel, _ in _files()})
    assert stale == [], f"в группах есть несуществующие файлы: {stale}"


def test_groups_import_only_themselves_and_lower_ones():
    wrong = []
    for rel, path in _files():
        for target in _imports(path, rel):
            if target in GROUPS and ORDER[GROUPS[target]] > ORDER[GROUPS[rel]]:
                wrong.append(f"{rel} ({GROUPS[rel]}) → {target} ({GROUPS[target]})")
    assert wrong == [], "нижняя группа не импортирует верхнюю:\n" + "\n".join(sorted(wrong))
