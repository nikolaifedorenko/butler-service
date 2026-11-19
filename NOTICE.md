# Сторонние компоненты

Код проекта открытой лицензией не сопровождается — продукт внутренний,
не предназначен для распространения (решение владельца от 15.10.2026).
Ниже — активы и зависимости, распространяемые на собственных условиях:
их лицензии следует соблюдать даже при внутреннем использовании
(например, не удалять уведомления из файлов шрифтов).

## Шрифты (поставляются в репозитории)

| Актив | Где используется | Лицензия |
|---|---|---|
| DejaVu Sans / DejaVu Serif (`assets/fonts/*.ttf`) | контейнер Gotenberg: шрифты с кириллицей для PDF (том `assets/fonts`, см. `docker-compose.yml`) | Bitstream Vera License (https://dejavu-fonts.github.io/License.html) — свободное использование, копирование и распространение с сохранением уведомлений; торговая марка Bitstream/AML требует согласия только при использовании наименований «Bitstream»/«Vera» |
| Manrope (`static/fonts/manrope-*.woff2`) | веб-интерфейс | SIL Open Font License 1.1, © Ivan Zhuravlev |
| Playfair Display (`static/fonts/playfair-display-*.woff2`) | веб-интерфейс | SIL Open Font License 1.1, © Claus Eggers Sørensen |

Тексты OFL 1.1 и Bitstream Vera License доступны по ссылкам выше; при
распространении бинарных сборок приложения включайте их копии.

## Зависимости Python

fastapi, uvicorn, starlette, pydantic, pydantic-settings, SQLAlchemy, alembic,
python-dotenv, openpyxl, python-docx, python-multipart — MIT; httpx — BSD-3-Clause;
prometheus-client — Apache-2.0; pillow — MIT-CMU (HPND).
Gotenberg (отдельный контейнер `gotenberg/gotenberg`, не часть образа приложения) — MIT; внутри него LibreOffice — MPL-2.0.
Точный состав и версии фиксирует `uv.lock`.

## Зависимости JavaScript (dev, `package.json`)

playwright — Apache-2.0; eslint и плагины — MIT.
