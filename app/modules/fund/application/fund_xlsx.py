"""Файл фонда (§9): выгрузка снимка в Excel и разбор такого файла обратно. Чистый модуль —
БД не трогает: применение разобранного файла к черновику — отдельный шаг. Разбор никогда не
бросает исключение на плохом входе: всё уходит в список FileError (лист, строка, сообщение)."""
from __future__ import annotations

from dataclasses import dataclass, field

from app.modules.exchange.application.tables import (
    Cell,
    Column,
    Fill,
    ListValidation,
    Protect,
    Sheet,
    XlsxError,
    open_xlsx,
    write_xlsx,
)

from ..adapters.orm import UnitFlag
from .fund_versions import FundSnapshot

SHEET_CATEGORIES = "Категории"
SHEET_TREE = "Дерево"
SHEET_FLAGS = "Флаги"
SHEET_UNITS = "Объекты"
SHEET_LISTS = "Списки"      # скрытый: все пути дерева для выпадающих списков

PATH_SEP = " / "
ID_HEADER = "ID (не менять; пусто — новая запись)"
MAX_FILE_BYTES = 10 * 1024 * 1024          # сам файл
MAX_UNPACKED_BYTES = 100 * 1024 * 1024     # распакованное содержимое (защита от zip-бомбы)
MAX_ROWS = 20000                           # строк на лист
MAX_FLAG_COLUMNS = 200

GREY = Fill("D9D9D9")
EDITABLE = Protect(allow_format_columns=True, allow_format_cells=True)   # заперт только столбец ID
_TRUE = {"да", "1", "true", "yes"}
_FALSE = {"нет", "0", "false", "no"}
_UNIT_FIXED = ["номер", "категория (код)", "узел", "этаж", "из чего (ID через запятую)"]


# ---------------------------------------------------------------- результат разбора

@dataclass(frozen=True)
class FileError:
    sheet: str
    row: int          # 0 — ошибка листа/файла целиком
    message: str


@dataclass
class ParsedCategory:
    row_no: int
    id: int | None
    code: str
    title: str
    kind: str             # название вида (справочник видов); пусто — не указан
    weight: float
    escorted: bool
    sort_order: int


@dataclass
class ParsedGroup:
    row_no: int
    id: int | None
    path: tuple[str, ...]
    sort_order: int
    escorted: bool = False


@dataclass
class ParsedFlag:
    row_no: int
    id: int | None
    title: str
    color: str


@dataclass
class ParsedUnit:
    row_no: int
    id: int | None
    label: str
    category_code: str
    group_path: tuple[str, ...] | None     # None — объект без узла
    floor: str
    predecessors: list[int] = field(default_factory=list)
    flags: frozenset[str] = frozenset()     # названия флагов с «да»


@dataclass
class ParsedFund:
    categories: list[ParsedCategory]
    groups: list[ParsedGroup]
    flags: list[ParsedFlag]
    units: list[ParsedUnit]
    flag_columns: list[str] = field(default_factory=list)   # заголовки колонок флагов «Объектов»


# ---------------------------------------------------------------- выгрузка

def _yn(v: bool) -> str:
    return "да" if v else "нет"


def _sheet(title: str, headers: list[str], widths: list[int], rows: list[list],
           validations: tuple[ListValidation, ...] = ()) -> Sheet:
    """Лист файла фонда: первая колонка (ID) серая и заперта, остальные можно править."""
    assert len(headers) == len(widths)
    return Sheet(
        title,
        header=[Cell(h, bold=True, locked=(i == 1)) for i, h in enumerate(headers, start=1)],
        rows=[[Cell(v, fill=GREY, locked=True) if i == 1 else Cell(v, locked=False)
               for i, v in enumerate(values, start=1)] for values in rows],
        columns={i: Column(w, locked=(i == 1)) for i, w in enumerate(widths, start=1)},
        freeze="A2", protect=EDITABLE, validations=validations)


def fund_sheets(snapshot: FundSnapshot, flags: list[UnitFlag]) -> list[Sheet]:
    used = {f for u in snapshot.units.values() for f in u.flags}
    cols = sorted((f for f in flags if not f.archived or f.id in used), key=lambda f: (f.sort_order, f.id))
    groups = sorted(snapshot.groups.values(), key=lambda g: ([snapshot.groups[i].sort_order for i in g.path], g.id))
    # Скрытый «Списки»: все пути в порядке дерева; на них ссылаются списки «Родитель» и «Узел».
    # Ссылка на диапазон, а не перечисление в формуле — лимит Excel в 255 знаков её не касается.
    source = f"$A$2:$A${max(len(groups) + 1, 2)}"

    def path_list(column: str) -> tuple[ListValidation, ...]:
        return (ListValidation(f"{column}2:{column}{MAX_ROWS + 1}", SHEET_LISTS, source),)

    categories = _sheet(
        SHEET_CATEGORIES, [ID_HEADER, "код", "название", "вид", "вес", "сопровождение (да/нет)", "порядок"],
        [16, 14, 28, 14, 8, 22, 10],
        [[c.id, c.code, c.title, c.kind_title, c.weight, _yn(c.escorted), c.sort_order]
         for c in sorted(snapshot.categories.values(), key=lambda c: (c.sort_order, c.id))])

    tree_rows = []
    for g in groups:
        parent = PATH_SEP.join(snapshot.path_titles(g.parent_id)) if g.parent_id in snapshot.groups else ""
        tree_rows.append([g.id, g.title, parent, _yn(g.escorted), g.sort_order])
    tree = _sheet(SHEET_TREE, [ID_HEADER, "название", "родитель", "сопровождение (да/нет)", "порядок"],
                  [16, 28, 50, 22, 10], tree_rows, path_list("C"))

    flag_sheet = _sheet(SHEET_FLAGS, [ID_HEADER, "название", "цвет"], [16, 28, 12],
                        [[f.id, f.title, f.color] for f in cols])

    unit_rows = []
    for u in sorted(snapshot.units.values(), key=lambda u: (u.label, u.id)):
        cat = snapshot.categories.get(u.category_id)
        path = PATH_SEP.join(snapshot.path_titles(u.group_id)) if u.group_id in snapshot.groups else ""
        # «Из чего» — история, а не состояние фонда: выгрузка оставляет колонку пустой (§9.1).
        unit_rows.append([u.id, u.label, cat.code if cat else "", path, u.floor, "",
                          *[_yn(f.id in u.flags) for f in cols]])
    units = _sheet(SHEET_UNITS, [ID_HEADER, *_UNIT_FIXED, *[f.title for f in cols]],
                   [16, 12, 18, 40, 8, 22, *[14] * len(cols)], unit_rows, path_list("D"))

    lists = Sheet(SHEET_LISTS, header=["путь"], rows=[[PATH_SEP.join(snapshot.path_titles(g.id))] for g in groups],
                  columns={1: Column(60)}, protect=Protect(), hidden=True)
    return [categories, tree, flag_sheet, units, lists]


def export_fund(snapshot: FundSnapshot, flags: list[UnitFlag]) -> bytes:
    return write_xlsx(fund_sheets(snapshot, flags))


# ---------------------------------------------------------------- разбор

class _Ctx:
    def __init__(self) -> None:
        self.errors: list[FileError] = []

    def err(self, sheet: str, row: int, msg: str) -> None:
        self.errors.append(FileError(sheet, row, msg))


def _text(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    s = str(v).strip()
    if len(s) > 1 and s[0] == "'" and s[1] in "=+-@\t\r":   # снимаем защиту safe_sheet_cell
        s = s[1:]
    return s


def _int(raw, ctx: _Ctx, sheet: str, row: int, what: str, *, default: int | None = None) -> int | None:
    s = _text(raw)
    if not s:
        return default
    try:
        n = int(s)
    except ValueError:
        ctx.err(sheet, row, f"{what}: «{s}» — не целое число")
        return default
    if n < 0 or n > 2**31 - 1:
        ctx.err(sheet, row, f"{what}: «{s}» вне допустимого диапазона")
        return default
    return n


def _bool(raw, ctx: _Ctx, sheet: str, row: int, what: str) -> bool:
    s = _text(raw).lower()
    if not s or s in _FALSE:
        return False
    if s in _TRUE:
        return True
    ctx.err(sheet, row, f"{what}: «{_text(raw)}» — ожидается да или нет")
    return False


def _path(s: str) -> tuple[str, ...]:
    return tuple(p.strip() for p in s.split(PATH_SEP.strip()))


def _read_sheet(wb, name: str, width: int, ctx: _Ctx) -> tuple[list[str], list[tuple[int, tuple]]] | None:
    """(заголовок, [(номер строки, значения)]) без пустых строк; None — листа нет/слишком велик."""
    if name not in wb.sheets:
        ctx.err(name, 0, f"в файле нет листа «{name}»")
        return None
    rows = wb.rows(name, max_col=width + MAX_FLAG_COLUMNS + 1)
    header: list[str] | None = None
    out: list[tuple[int, tuple]] = []
    for n, vals in enumerate(rows, start=1):
        if n == 1:
            header = [_text(v) for v in vals]
            continue
        if n - 1 > MAX_ROWS:
            ctx.err(name, 0, f"слишком много строк: больше {MAX_ROWS}")
            return None
        if all(v is None or _text(v) == "" for v in vals):
            continue
        out.append((n, vals + (None,) * max(0, width - len(vals))))
    if header is None or len(header) < width:
        ctx.err(name, 1, f"заголовок листа неполный: ожидается {width} колонок")
        return None
    return header, out


def _dup_ids(items: list, sheet: str, ctx: _Ctx) -> None:
    seen: dict[int, int] = {}
    for it in items:
        if it.id is None:
            continue
        if it.id in seen:
            ctx.err(sheet, it.row_no, f"ID {it.id} повторяется (первый раз в строке {seen[it.id]})")
        else:
            seen[it.id] = it.row_no


def _dup_keys(items: list, key, sheet: str, what: str, ctx: _Ctx) -> None:
    seen: dict = {}
    for it in items:
        k = key(it)
        if k in (None, "", ()):
            continue
        if k in seen:
            ctx.err(sheet, it.row_no, f"{what} «{k if isinstance(k, str) else PATH_SEP.join(k)}» повторяется "
                                      f"(первый раз в строке {seen[k]})")
        else:
            seen[k] = it.row_no


_FILE_ERRORS = {
    "too_large": f"файл больше {MAX_FILE_BYTES // 1024 // 1024} МБ",
    "unpacked_too_large": "файл слишком велик после распаковки",
    "not_xlsx": "не файл Excel (.xlsx)",
    "unreadable": "не удалось прочитать файл Excel (.xlsx)",
}


def parse_fund(data: bytes, known_unit_ids: set[int] | None = None) -> tuple[ParsedFund | None, list[FileError]]:
    """Разбор файла фонда. known_unit_ids — id объектов текущего фонда: если передан, «Из чего»
    с неизвестным id — ошибка; иначе проверяется только формат."""
    ctx = _Ctx()
    try:
        wb = open_xlsx(data, max_bytes=MAX_FILE_BYTES, max_unpacked_bytes=MAX_UNPACKED_BYTES)
    except XlsxError as e:
        return None, [FileError("", 0, _FILE_ERRORS[e.kind])]
    try:
        return _parse(wb, known_unit_ids, ctx)
    except Exception:  # noqa: BLE001 — неожиданная структура файла это ошибка файла, а не сбой
        return None, [*ctx.errors, FileError("", 0, "файл повреждён или имеет неожиданную структуру")]
    finally:
        wb.close()


def _parse(wb, known_unit_ids: set[int] | None, ctx: _Ctx) -> tuple[ParsedFund | None, list[FileError]]:
    if SHEET_TREE in wb.sheets:           # прежний формат: «ID | путь узла | порядок» без «Родителя»
        head = next(wb.rows(SHEET_TREE, max_row=1, max_col=4), ())
        if len(head) < 3 or not _text(head[2]).lower().startswith("родитель"):
            ctx.err(SHEET_TREE, 1, "старый формат файла: нет колонки «Родитель» — выгрузите фонд заново")
            return None, ctx.errors
    cats_raw = _read_sheet(wb, SHEET_CATEGORIES, 7, ctx)
    tree_raw = _read_sheet(wb, SHEET_TREE, 4, ctx)
    flags_raw = _read_sheet(wb, SHEET_FLAGS, 3, ctx)
    units_raw = _read_sheet(wb, SHEET_UNITS, 6, ctx)
    if cats_raw is None or tree_raw is None or flags_raw is None or units_raw is None:
        return None, ctx.errors

    cats: list[ParsedCategory] = []
    for n, v in cats_raw[1]:
        code, title = _text(v[1]), _text(v[2])
        if not code:
            ctx.err(SHEET_CATEGORIES, n, "не указан код категории")
        if not title:
            ctx.err(SHEET_CATEGORIES, n, "не указано название категории")
        w = _text(v[4]).replace(",", ".")
        try:
            weight = float(w) if w else 1.0
        except ValueError:
            ctx.err(SHEET_CATEGORIES, n, f"вес: «{w}» — не число")
            weight = 1.0
        cats.append(ParsedCategory(
            n, _int(v[0], ctx, SHEET_CATEGORIES, n, "ID"), code, title, _text(v[3]), weight,
            _bool(v[5], ctx, SHEET_CATEGORIES, n, "сопровождение"),
            _int(v[6], ctx, SHEET_CATEGORIES, n, "порядок", default=100) or 0))
    _dup_ids(cats, SHEET_CATEGORIES, ctx)
    _dup_keys(cats, lambda c: c.code, SHEET_CATEGORIES, "код", ctx)

    # Узел — «Название» + «Родитель» (полный путь родителя; пусто — корень). Строки в любом порядке:
    # родитель может стоять ниже ребёнка, поэтому наличие родителя проверяется по всему листу.
    # Колонка «Сопровождение» необязательна: в файле прежней выгрузки её нет, порядок тогда четвёртый.
    has_esc = len(tree_raw[0]) > 3 and _text(tree_raw[0][3]).lower().startswith("сопровождение")
    order_col = 4 if has_esc else 3
    groups: list[ParsedGroup] = []
    for n, v in tree_raw[1]:
        v = v + (None,) * (order_col + 1 - len(v))
        title, parent = _text(v[1]), _text(v[2])
        pp = _path(parent) if parent else ()
        if not title:
            ctx.err(SHEET_TREE, n, "не указано название узла")
            continue
        if "/" in title:
            ctx.err(SHEET_TREE, n, "в названии узла нельзя использовать «/»")
            continue
        if any(not x for x in pp):
            ctx.err(SHEET_TREE, n, "родитель содержит пустое звено")
            continue
        groups.append(ParsedGroup(n, _int(v[0], ctx, SHEET_TREE, n, "ID"), (*pp, title),
                                  _int(v[order_col], ctx, SHEET_TREE, n, "порядок", default=100) or 0,
                                  _bool(v[3], ctx, SHEET_TREE, n, "сопровождение") if has_esc else False))
    _dup_ids(groups, SHEET_TREE, ctx)
    _dup_keys(groups, lambda g: g.path, SHEET_TREE, "путь", ctx)
    paths = {g.path for g in groups}
    for g in groups:
        if len(g.path) > 1 and g.path[:-1] not in paths:
            ctx.err(SHEET_TREE, g.row_no, f"нет узла-родителя «{PATH_SEP.join(g.path[:-1])}»")

    flags: list[ParsedFlag] = []
    for n, v in flags_raw[1]:
        title = _text(v[1])
        if not title:
            ctx.err(SHEET_FLAGS, n, "не указано название флага")
            continue
        flags.append(ParsedFlag(n, _int(v[0], ctx, SHEET_FLAGS, n, "ID"), title, _text(v[2])))
    _dup_ids(flags, SHEET_FLAGS, ctx)
    _dup_keys(flags, lambda f: f.title, SHEET_FLAGS, "флаг", ctx)

    # Колонки флагов листа «Объекты»: новая колонка создаёт флаг (§9.1).
    uheader, urows = units_raw
    flag_cols = [(i, t) for i, t in enumerate(uheader) if i >= 6 and t]
    if len(uheader) > 6 + MAX_FLAG_COLUMNS and any(uheader[6 + MAX_FLAG_COLUMNS:]):
        ctx.err(SHEET_UNITS, 1, f"слишком много колонок флагов: больше {MAX_FLAG_COLUMNS}")
    known_titles = {f.title for f in flags}
    seen_cols: set[str] = set()
    for _, t in flag_cols:
        if t in seen_cols:
            ctx.err(SHEET_UNITS, 1, f"колонка флага «{t}» повторяется")
        seen_cols.add(t)
        if t not in known_titles:
            flags.append(ParsedFlag(0, None, t, ""))
            known_titles.add(t)
    # Заголовок «ID…» / фиксированные колонки — позиционные; проверим, что первая — ID.
    if not uheader[0].lower().startswith("id"):
        ctx.err(SHEET_UNITS, 1, "первая колонка должна быть ID")

    cat_codes = {c.code for c in cats}
    units: list[ParsedUnit] = []
    for n, v in urows:
        label = _text(v[1])
        if not label:
            ctx.err(SHEET_UNITS, n, "не указан номер объекта")
        code = _text(v[2])
        if not code or code not in cat_codes:
            ctx.err(SHEET_UNITS, n, f"неизвестная категория «{code}»" if code else "не указана категория")
        gs = _text(v[3])
        gpath = _path(gs) if gs else None
        if gpath is not None and gpath not in paths:
            ctx.err(SHEET_UNITS, n, f"неизвестный узел «{gs}»")
        preds: list[int] = []
        for part in _text(v[5]).replace(";", ",").split(","):
            if not part.strip():
                continue
            pid = _int(part, ctx, SHEET_UNITS, n, "«Из чего»")
            if pid is None:
                continue
            if known_unit_ids is not None and pid not in known_unit_ids:
                ctx.err(SHEET_UNITS, n, f"«Из чего»: неизвестный ID {pid}")
            preds.append(pid)
        uid = _int(v[0], ctx, SHEET_UNITS, n, "ID")
        if uid is not None and preds:
            ctx.err(SHEET_UNITS, n, "«Из чего» заполняется только у новых строк (ID пуст)")
        on = frozenset(t for i, t in flag_cols
                       if i < len(v) and _bool(v[i], ctx, SHEET_UNITS, n, f"флаг «{t}»"))
        units.append(ParsedUnit(n, uid, label, code, gpath,
                                _text(v[4]), preds, on))
    _dup_ids(units, SHEET_UNITS, ctx)
    _dup_keys(units, lambda u: u.label, SHEET_UNITS, "номер", ctx)

    if ctx.errors:
        return None, ctx.errors
    return ParsedFund(cats, groups, flags, units, [t for _, t in flag_cols]), []
