"""Дизайн-система (шаг 6б): значения живут только в tokens.css; остальные стили берут их через var(--…),
каждое используемое имя определено, а тёмная тема переопределяет все цветовые роли."""
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


def test_dark_theme_overrides_every_color_role():
    tokens = (CSS / "tokens.css").read_text(encoding="utf-8")
    light = re.search(r"^:root \{(.*?)^\}", tokens, re.S | re.M).group(1)
    dark = re.search(r':root\[data-theme="dark"\] \{(.*?)^\}', tokens, re.S | re.M).group(1)
    media = re.search(r'@media \(prefers-color-scheme: dark\) \{\s*:root:not\(\[data-theme="light"\]\) \{(.*?)^  \}', tokens, re.S | re.M).group(1)
    names = lambda block: set(VAR_DEF.findall(block))     # noqa: E731
    colored = {n for n, v in re.findall(r"(--[\w-]+):\s*([^;]+);", light)
               if re.search(r"#[0-9a-fA-F]{3,8}\b|rgba?\(", v)}
    # одинаковые в обеих темах: фирменные цвета и тёмные поверхности шапки/входа
    same_in_both = {"--gold", "--gold-deep", "--navy", "--navy-2", "--accent", "--accent-dark", "--danger", "--warn", "--info",
                    "--primary-soft"}
    missing = sorted(colored - names(dark) - same_in_both)
    assert not missing, f"тёмная тема не переопределяет: {missing}"
    assert names(dark) == names(media), "блок prefers-color-scheme разошёлся с data-theme=dark"


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
