"""Дизайн-система (шаг 6б): значения живут только в tokens.css; остальные стили берут их через var(--…),
каждое используемое имя определено, а адаптивные цветовые роли объявлены одной парой."""
from __future__ import annotations

import re
from pathlib import Path

CSS = Path(__file__).resolve().parent.parent / "static" / "css"
HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")
VAR_USE = re.compile(r"var\(\s*(--[\w-]+)")
VAR_DEF = re.compile(r"(--[\w-]+)\s*:")


def _strip_comments(text: str) -> str:
    return re.sub(r"/\*.*?\*/", "", text, flags=re.S)


def _without_data_uris(text: str) -> str:
    return re.sub(r'url\("data:[^"]*"\)', "", text)


def test_no_hard_coded_colors_outside_tokens():
    """Цвета в base/components/app — только через токены. Исключения — вокруг тёмной подложки входа и
    цветных рамок-выделений, не зависящих от темы (их значение не меняется между темами)."""
    allowed = {"app.css": {"#1a2130", "#10141d", "#c9a55a", "#e05a5a", "#e8a317"}}
    bad: list[str] = []
    for name in ("base.css", "components.css", "app.css"):
        text = _without_data_uris(_strip_comments((CSS / name).read_text(encoding="utf-8")))
        for m in HEX.finditer(text):
            if m.group(0).lower() not in allowed.get(name, set()):
                line = text.count("\n", 0, m.start()) + 1
                bad.append(f"{name}: {m.group(0)} (строка ≈{line})")
    assert not bad, "цвета вне tokens.css:\n" + "\n".join(bad[:15])


def test_every_used_variable_is_defined():
    tokens = (CSS / "tokens.css").read_text(encoding="utf-8")
    defined = set(VAR_DEF.findall(tokens))
    used: dict[str, str] = {}
    for name in ("base.css", "components.css", "app.css", "tokens.css"):
        for v in VAR_USE.findall(_strip_comments((CSS / name).read_text(encoding="utf-8"))):
            used.setdefault(v, name)
    # локальные переменные экранов (--c, --w …) объявляются самими правилами
    local = set()
    for name in ("base.css", "components.css", "app.css"):
        local |= set(VAR_DEF.findall(_strip_comments((CSS / name).read_text(encoding="utf-8"))))
    from_js = {"--days", "--depth"}      # задаются из скриптов через style="--days: 7"
    missing = sorted(v for v in used if v not in defined and v not in local and v not in from_js)
    assert not missing, f"переменные без определения: {missing}"


def test_each_semantic_role_has_one_definition():
    tokens = _strip_comments((CSS / "tokens.css").read_text(encoding="utf-8"))
    names = [name for name in VAR_DEF.findall(tokens) if name not in {"--if-light", "--if-dark"}]
    assert len(names) == len(set(names)), "семантическая роль определена повторно"
    shared = {
        "--gold", "--gold-deep", "--navy", "--navy-2", "--navy-deep", "--accent", "--accent-dark",
        "--danger", "--warn", "--info", "--on-navy", "--on-navy-muted", "--on-solid", "--ink-on-gold",
        "--warn-fg-soft", "--shadow-surface",
    }
    for name, value in re.findall(r"(--[\w-]+):\s*([^;]+);", tokens):
        if re.search(r"#[0-9a-fA-F]{3,8}\b|rgba?\(", value) and name not in shared:
            assert "var(--if-light," in value and "var(--if-dark," in value, f"для {name} нужна пара значений темы"


def test_motion_tokens_are_single_authority_for_transitions():
    tokens = _strip_comments((CSS / "tokens.css").read_text(encoding="utf-8"))
    assert len(re.findall(r"--ease\s*:", tokens)) == 1
    assert re.search(r"--ease:\s*cubic-bezier\(\.2,\s*\.7,\s*\.2,\s*1\);", tokens)
    assert re.search(r"--dur-1:\s*150ms;", tokens)
    assert re.search(r"--dur-2:\s*250ms;", tokens)

    for name in ("components.css", "app.css"):
        css = _strip_comments((CSS / name).read_text(encoding="utf-8"))
        declarations = re.findall(r"transition\s*:\s*([^;]+);", css)
        assert declarations, f"в {name} не найдены transitions"
        for declaration in declarations:
            assert "var(--dur-" in declaration, f"{name}: transition без duration token: {declaration}"
            assert "var(--ease)" in declaration, f"{name}: transition без easing token: {declaration}"
