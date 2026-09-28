#!/usr/bin/env python3
"""Сверка контракта фронтенд ↔ бэкенд.

Зачем: 120+ маршрутов API и несколько тысяч строк JS без общей типизации легко
расходятся. Скрипт находит
  * вызовы в static/js/*.js, для которых НЕТ маршрута в OpenAPI (→ 404 в интерфейсе),
  * маршруты, которые интерфейс не вызывает (кандидаты на удаление; см. docs/AUDIT).

Использование:
    python3 tools/check_api_contract.py            # проверка, код возврата 1 при битых вызовах
    python3 tools/check_api_contract.py --verbose  # + список неиспользуемых маршрутов
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
JS_DIR = BASE / "static" / "js"
if str(BASE) not in sys.path:      # запуск из tools/ без установки пакета
    sys.path.insert(0, str(BASE))

# строковые и шаблонные литералы с путями API
CALL_RE = re.compile(r"""['"`](/api/[^'"`\s]*)['"`]""")


def route_patterns() -> list[tuple[str, str, str]]:
    """[(метод, путь-шаблон, путь-пример)] из OpenAPI текущего кода.

    Пример получается подстановкой «1» вместо параметров: с ним сверяются вызовы
    интерфейса, где плейсхолдер может стоять в любом месте сегмента
    (например, `/api/night/reports/${id}/export.${fmt}`).
    """
    from app.main import app

    out = []
    for path, ops in app.openapi()["paths"].items():
        for method in ops:
            if method.lower() not in ("get", "post", "put", "patch", "delete", "head"):
                continue
            sample = re.sub(r"\{[^}]+\}", "1", path)
            out.append((method.upper(), path, sample))
    return out


def frontend_calls() -> dict[str, set[str]]:
    """{метод-или-'ANY': {путь,…}} — что реально зовёт интерфейс.

    Метод берём из соседнего `method: 'POST'` в том же вызове api(), если он есть;
    иначе считаем вызов «ANY» и сопоставляем с любым методом маршрута.
    """
    calls: dict[str, set[str]] = {}
    for js in sorted(JS_DIR.glob("*.js")):
        text = js.read_text(encoding="utf-8")
        for m in CALL_RE.finditer(text):
            raw = m.group(1)
            # ${...} в шаблонных строках → сегмент-заполнитель
            norm = re.sub(r"\$\{[^}]*\}", "{}", raw)
            norm = norm.split("?")[0].rstrip("/") or "/"
            # метод ищем только внутри этого вызова: до следующего api( / downloadBlob(
            # или 120 символов — иначе «чужой» method: 'POST' приписывается соседнему коду
            tail = text[m.end():m.end() + 120]
            tail = re.split(r"api\(|downloadBlob\(|multipartApi\(", tail)[0]
            mm = re.search(r"method:\s*['\"](\w+)['\"]", tail)
            method = mm.group(1).upper() if mm else "ANY"
            calls.setdefault(method, set()).add(norm)
    return calls


def matches(call_path: str, route_sample: str) -> bool:
    """Вызов совпадает с маршрутом, если regex вызова (плейсхолдеры → [^/]+)
    подходит к пути-примеру маршрута."""
    pattern = "^" + re.escape(call_path).replace(re.escape("{}"), "[^/]+") + "$"
    return bool(re.match(pattern, route_sample))


def main() -> int:
    verbose = "--verbose" in sys.argv
    routes = route_patterns()
    calls = frontend_calls()

    broken: list[tuple[str, str]] = []
    used: set[tuple[str, str]] = set()
    for method, paths in sorted(calls.items()):
        for path in sorted(paths):
            hit = None
            for r_method, r_path, r_sample in routes:
                if method not in ("ANY", r_method):
                    continue
                if matches(path, r_sample):
                    hit = (r_method, r_path)
                    break
            if hit is None:
                broken.append((method, path))
            else:
                used.add(hit)

    unused = sorted({(m, p) for m, p, _ in routes} - used)

    print(f"маршрутов в OpenAPI: {len(routes)}; вызовов в static/js: "
          f"{sum(len(v) for v in calls.values())}")
    if broken:
        print("\n✗ Вызовы интерфейса без маршрута на бэкенде (будет 404):")
        for method, path in broken:
            print(f"   {method:6} {path}")
    else:
        print("✓ Все вызовы интерфейса имеют маршрут на бэкенде")

    if verbose:
        print(f"\nМаршруты, которые интерфейс не вызывает ({len(unused)}) — кандидаты на удаление"
              " или на появление в UI:")
        for method, path in unused:
            print(f"   {method:6} {path}")

    return 1 if broken else 0


if __name__ == "__main__":
    raise SystemExit(main())
