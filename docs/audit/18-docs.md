# 18. Устаревшая документация

Источник правды — код. Битые ссылки собраны скриптом `docs/audit/scripts/doc_links.py`: 102 в
`*.md`, из них 83 в историческом журнале (`CHANGES-*`, `EXECUTION-SPEC-v2`, `PROPOSAL-*` —
нормально, это история) и **19 в «живых» документах**. ID → [REPORT.md](REPORT.md).

## 18.1. Утверждение → факт → что исправить
| Документ:строка | Утверждение | Факт в коде | Исправить |
|---|---|---|---|
| `docs/architecture/ARCHITECTURE.md:10` | «полный прогон тестов (436 тестов)» | там же `:107` «767 тестов»; фактически 803 passed + 3 skipped (`commands.md`) | одна цифра со ссылкой «на дату» или без цифры |
| `ARCHITECTURE.md:5-6` | ссылки на `app/timesheet.py`, `docs/archive/AUDIT-2026-09-27.md` | файлов нет | убрать |
| `README.md:12,24` | `docs/archive/overtime_ai_tz_v3.md` | нет папки `docs/archive/` | убрать или создать архив |
| `SECURITY.md:25,39` | `app/permissions.py`, `docs/CHANGES-2026-10-14-security.md` | `app/core/permissions.py`; CHANGES-14.10 нет | обновить пути |
| `docs/AUTH.md:25,62,67` | `app/security.py`, `app/permissions.py`, `app/auth.py` | `app/core/…` | обновить |
| `deploy/README.md:78`, `docs/adr/0002…:6` | `app/migrations.py` (~500 строк) | `app/bootstrap/migrations.py`, 771 строка | обновить |
| `docs/adr/0002…:20` | «план перехода зафиксирован в ROADMAP (п. P0-3)» | ROADMAP в репозитории нет | ссылку на TARGET-ARCHITECTURE/PLAN или новый ADR |
| `docs/adr/0006…:7,16,30` | `app/engine/`, `app/cars.py`, `app/photos.py` | ADR помечен «заменён ADR-0010» (`:3`), поэтому устаревание допустимо | не править (история), но в шапке дать ссылку на новые пути |
| `docs/adr/0008-frontend-bez-sborki.md:17-35` | «новый раздел — новым файлом `section_<раздел>.js`», `app.js` 369 строк | файлы `static/js/modules/<раздел>.js`; `app.js` — 30,6 КБ | дополнить ADR актуальным правилом (`modules/<name>.js`) |
| `docs/adr/0010…:6,14,19` | `app/api`, `app/engine/`, `app/notify` | так ADR описывает прошлое («было»), это нормально | — |
| `docs/SPEC.md:148,185,197-198` | `app/tabel_fill.py`, `section_settings.js`, `section_night.js`, `section_cars.js` | `modules/timesheet/application/tabel_fill.py`, `static/js/modules/*.js` | обновить |
| `docs/INSTALL.md:92` | `tools/smoke_ui.py` | нет файла | убрать |
| `NOTICE.md:13` | `app/pdf_render.py` | `app/core/render.py` | обновить |
| `deploy/nginx.conf:30,51` (комментарии) | «бланки — до 5 МБ», `app/pdf_render.py` | лимит медиа 12/50 МБ; `core/render.py` | исправить вместе с OPS-01 |
| `static/js/core.js:14` | «специфичное — в `sections/<раздел>.js`» | `modules/` | обновить комментарий |
| `app/core/permissions.py:49-51` | «вторым стражем [имперсонации] остаётся `can_manage_user`» | `impersonate()` его не вызывает (`auth_routes.py:227-240`) | **опасная неточность**: исправить код (AUTHZ-01) или комментарий |
| `app/core/auth.py:105-115` | «в модулях обращений к `is_manager` не осталось» | `core/media.py:414` использует `is_manager`; 7 мест проверяют `principal.role` строками | уточнить (AUTHZ-05) |
| `app/main.py:165` (комментарий) | «Сервисы (`app/services/*`) …» | папки `app/services` нет | обновить |
| `docs/adr/0006…:32` | «независимость 17 api-модулей» | ADR заменён; сейчас 18 роутеров в 9 модулях | — |
| `.env.example` | перечень переменных | нет `SESSION_TTL_HOURS`, `NIGHT_SYNC_ENABLED`, `NIGHT_SYNC_SECONDS`, `CSRF_ENABLED`, `ALLOW_INSECURE_DEV_SECRET` (упомянута в комментарии), `UVICORN_WORKERS` | дополнить (DOC-04) |
| `docs/INSTALL.md:205` | «войдите под `admin`, смените демо-пароли» | инструкция есть в INSTALL, но **нет** в `deploy/README.md` для прод-профиля; сид создаёт демо-учётки и на PostgreSQL (SEC-02) | перенести в deploy/README как обязательный шаг, а лучше убрать сид из прода |
| `requirements.txt` про bcrypt (зацепка промпта) | — | комментария больше нет | — |
| `docs/openapi.json` | соответствует коду | `export_openapi.py --check` ✓ | — |

## 18.2. Один источник на тему (предложение)
| Тема | Сейчас | Предлагаемый единственный источник | В архив (`docs/archive/`) |
|---|---|---|---|
| Что это и как запустить | README (56 КБ), INSTALL | **README** — коротко (что это, запуск, ссылки); **INSTALL** — установка | — |
| Прод-развёртывание | deploy/README, INSTALL §прод, комментарии compose | **deploy/README** | дубли из INSTALL |
| Архитектура и правила слоёв | ARCHITECTURE.md, EXECUTION-SPEC-v2.md (54 КБ), ADR-0006/0010, `.importlinter`, README §структура | **ARCHITECTURE.md** (живой) + ADR (решения) | EXECUTION-SPEC-v2 (выполнен), ADR-0006 оставить как «заменён» |
| Аутентификация и права | AUTH.md, SECURITY.md, комментарии `permissions.py` | **AUTH.md** (модель прав), **SECURITY.md** (политика, контакты) | — |
| Бизнес-правила расчёта | `overtime_spec_v7_1_final.md` (459 КБ), SPEC.md | спецификация v7.1 (норматив) + SPEC.md (продукт) | — |
| История изменений | 19 файлов `CHANGES-*` | один `CHANGELOG.md` с разделами по датам и ссылками на PR | старые `CHANGES-*` |
| Прототипы | `docs/prototypes/*` | — | целиком |

Защита от дрейфа: добавить `doc_links.py` в CI для живых документов (README, INSTALL, AUTH,
SECURITY, deploy, ADR, ARCHITECTURE). Цифры «N тестов, M маршрутов» в документах не писать
руками, а генерировать или не писать совсем.
