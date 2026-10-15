# Сторонние компоненты

Код приложения — MIT License (см. `LICENSE`). Ниже — активы и зависимости,
распространяемые на собственных условиях.

## Шрифты (поставляются в репозитории)

| Актив | Где используется | Лицензия |
|---|---|---|
| DejaVu Sans / DejaVu Serif (`assets/fonts/*.ttf`) | встроенный PDF-рендер (`app/pdf_render.py`) | Bitstream Vera License (https://dejavu-fonts.github.io/License.html) — свободное использование, копирование и распространение с сохранением уведомлений; торговая марка Bitstream/AML требует согласия только при использовании наименований «Bitstream»/«Vera» |
| Manrope (`static/fonts/manrope-*.woff2`) | веб-интерфейс | SIL Open Font License 1.1, © Ivan Zhuravlev |
| Playfair Display (`static/fonts/playfair-display-*.woff2`) | веб-интерфейс | SIL Open Font License 1.1, © Claus Eggers Sørensen |

Тексты OFL 1.1 и Bitstream Vera License доступны по ссылкам выше; при
распространении бинарных сборок приложения включайте их копии.

## Зависимости Python

fastapi, uvicorn, starlette, pydantic, pydantic-settings, SQLAlchemy,
python-dotenv, openpyxl, python-docx, python-multipart — MIT; bcrypt — Apache-2.0;
reportlab (опционально, `requirements-pdf.txt`) — BSD-3-Clause.
Точный состав и версии фиксирует `requirements.lock.txt`.

## Зависимости JavaScript (dev, `package.json`)

jsdom — MIT; eslint и плагины — MIT.
