# 13. Безопасность

Канонические формулировки находок — в [REPORT.md](REPORT.md). Здесь лежат доказательства и
статус каждой «зацепки» из промпта.

## 13.1. Статус зацепок промпта
| Зацепка | Статус в `main` `3801abf` | Доказательство |
|---|---|---|
| Два механизма авторизации (`require_manager` и т.п.) | **частично исправлено**: зависимости удалены (`core/auth.py:105-115`), все 160 маршрутов с правом идут через `require_perm`. Но **8 проверок роли строками** в теле остались (AUTHZ-05) | 03-perm-matrix.md; EXP-ROLEGRANT: supervisor с явным allow `settings.edit` получает 403 на `/api/doublepay/days` |
| `settings_api`, `doublepay`, `docs_api`, `notify_api`, `employees-for-demo` на `require_manager` | исправлено: `require_perm("settings.*")`, `employees.impersonate`. Исключение — `doublepay._guard` (роль) | 01-routes.md |
| IDOR фото | **подтверждено** (AUTHZ-07) | EXP-PHOTO |
| IDOR отметки | нет: без `punches.view_all` журнал только свой (`punches.py:351-367`); комментарий к чужой отметке требует права (`set_punch_note`) | чтение кода |
| IDOR ночные отчёты и кары | по замыслу общие для всех с `night.view` и `cars.view`; изменения обхода не требуют даже `night.view` (AUTHZ-06) | EXP-NIGHTVIEW |
| IDOR заявления (документы) | `render` требует `settings.view` (supervisor+); сотрудник себе заявление не печатает | `docs_api.py:234-245` |
| Mass assignment | `EmployeeIn` не содержит `is_active`, `token_version`, `employee_id`, автора; роль проходит через `can_manage_user`. Но отсутствующее поле `role` равно `employee` (AUTHZ-03), и пароль задаётся без требований | `employees.py:133-155,264-316`; EXP-ROLE |
| Impersonation | аудит пишется, но `actor_name` содержит **имя сотрудника**, а не того, кто вошёл (`core/audit.py:45`); `can_manage_user` не применяется, хотя комментарий `permissions.py:49-51` утверждает обратное (AUTHZ-01); блокировка сотрудника не прерывает сессию (AUTHZ-10) | EXP-IMP-1 |
| Токен | HMAC-SHA256, усечённый до 128 бит — достаточно; `exp` проверяется; `token_version` сверяется на каждом запросе (`core/auth.py:85-90`). Смена `SECRET_KEY` разлогинивает всех — ожидаемо | `core/security.py:57-80` |
| `cookie_secure=False` по умолчанию | прод-compose ставит `COOKIE_SECURE: "1"`; SQLite-compose по умолчанию `0` (если его открыть по HTTPS через внешний прокси, cookie уйдёт и по HTTP) | `docker-compose.yml`, `docker-compose.prod.yml:46` |
| Исключения CSRF | только вход (login-CSRF осознанно, ADR-0004). Проверка до вызова обработчика, сравнение байтов | `core/observability.py:27-72` |
| SSRF и утечка токена бота | **подтверждено чтением** (SEC-03) | `notify/application/config.py:24-26,111-150`; `telegram.py:49-51` |
| Загрузки | тип по содержимому, потоковая запись, лимиты; zip-лимиты для DOCX; python-docx не разрешает сущности; имя файла на диске — uuid; SPA-fallback защищён `is_relative_to` (`main.py:337-349`). Слабые места: картинка с нераспознанным содержимым принимается по расширению (`media.py:136-137`), nginx режет на 8 МБ (OPS-01) | чтение кода |
| raw SQL с f-строками | в `migrations.py:146,632,761-771` подставляются имена из констант и int из БД — **не инъекция** (bandit B608 — ложная тревога) | чтение кода |
| XSS (`innerHTML`, 113 присваиваний) | эвристика нашла 292 интерполяции без явного `esc()`; ручная проверка всех текстовых полей — **уязвимостей не найдено**: текст идёт через `esc()`, цвета через `cssColor()`, коды берутся из серверных констант | `docs/audit/scripts/xss_scan.py` |
| CSV/XLSX-инъекции | `safe_sheet_cell` применяется к именам, комментариям и payload во всех выгрузках (`schedule.py:1289-1290`, `mgmt_api.py:229-236`, `audit_api.py:99-100`, `notify_api.py:262-267`). Не обёрнуты `target` и `channel_title` в CSV рассылок (`notify_api.py:263`), но их задаёт `settings.edit` | Low |
| CSP, HSTS | CSP строгая (`script-src 'self'`, `style-src 'unsafe-inline'` — ADR-0004), HSTS только по TLS (`observability.py:82-108`) | — |
| `/metrics` | закрыт в nginx (`deploy/nginx.conf:39-41`) | — |
| `/api/docs`, `/api/openapi.json`, **`/redoc`** открыты в проде | подтверждено (OPS-04). `redoc_url` не отключён — FastAPI по умолчанию отдаёт `/redoc` | `main.py:157-158`; `app.routes` содержит `/redoc` и `/docs/oauth2-redirect` |
| `--forwarded-allow-ips "*"`, `TRUST_PROXY_HEADERS=1` | вместе с `$proxy_add_x_forwarded_for` в nginx позволяют клиенту подставить свой IP (SEC-01) | EXP-XFF |
| Контейнер от root | подтверждено: нет `USER` (OPS-02) | `Dockerfile` |
| Бэкапы `pg_dumpall` без шифрования | подтверждено, лежат на том же хосте (OPS-03) | `docker-compose.prod.yml:88-116` |
| `demo1234` в сиде | **подтверждено**: сид создаёт `admin` и 11 демо-учёток на любой пустой базе, в том числе боевой PostgreSQL (SEC-02) | `bootstrap/seed.py:44,110-165`; `main.py:86-93` |
| Утечки в логах и ответах | JSON-лог пишет путь без query, IP, request-id (`observability.py:150-156`); `/api/health` отдаёт тип исключения БД без текста; 500 без стектрейса. `/api/selfcheck` без входа отдаёт только ok и подсказку | — |
| Зависимости | `pip-audit` по lock: уязвимостей нет. В `requirements.txt` только нижние границы, а **Dockerfile ставит `requirements.txt`, а не lock** (OPS-02). `python-dotenv` напрямую не импортируется (DEAD-04). Комментария про bcrypt больше нет | `commands.md` |

## 13.2. Последствия ролевых проверок для каждой роли (AUTHZ-05)
| Место | admin | manager | supervisor | employee | Что ломается при индивидуальных правах |
|---|---|---|---|---|---|
| `timesheet/interface/doublepay.py:44-48` (дни двойной оплаты) | ✔ | ✔ | ✘ | ✘ | supervisor с allow `settings.edit` всё равно 403 (EXP-ROLEGRANT) |
| `employees.py:389-392` (корректировка банка) | ✔ | ✔ | ✘ | ✘ | allow `employees.edit` бесполезен для банка; deny `employees.edit` у manager закрывает маршрут через `require_perm` — это корректно |
| `cars.py:241,294` (передать или вернуть чужой кар) | ✔ | ✔ | ✔ | ✘ | выдать сотруднику «право супервайзера по карам» нельзя: `cars.issue` эту ветку не открывает |
| `cars.py:353,356` (обслуживание кара) | ✔ | ✔ | ✘ | ✘ | supervisor с `cars.issue` не снимет кар с обслуживания, но может «выдать» его (BUG-02) |
| `cars_api.py:150` (неактивные места) | ✔ | ✔ | ✔ | ✘ | — |
| `night_api.py:948` (переоткрыть закрытую область) | ✔ | ✔ | ✔ | только свою | `night.close` эту ветку не открывает |
| `core/media.py:414` (удалить чужое фото) | ✔ | ✔ | ✔ | своё | в режиме «как сотрудник» менеджер удаляет только свои фото |

## 13.3. Эксперименты безопасности (Факт)
Вывод `experiments.py` — в [commands.md](commands.md): EXP-XFF, EXP-IMP-1, EXP-PWD, EXP-ROLE,
EXP-ROLEGRANT, EXP-PUNCHOTHER, EXP-PHOTO, EXP-NIGHTVIEW, EXP-DISPATCH, EXP-PHOTODEL.

## 13.4. Меры усиления имперсонации (решение владельца не оспаривается)
1. В `audit()` писать того, кто действовал на самом деле: `actor_name = "<менеджер> → как <сотрудник>"`,
   `actor_id` — менеджер, а `employee_id` цели отдельным полем payload. В UI журнала показывать
   обоих.
2. При `impersonate` вызывать `can_manage_user(principal, target_user)`: supervisor не может
   войти как manager или admin. Комментарий `permissions.py:49-51` описывает именно это.
3. В режиме «как сотрудник» запретить действия от имени цели или требовать подтверждения:
   отметки, взятие кара, ответы обхода. Это вопрос владельцу (В-3). Нынешний режим удобен для
   «показа интерфейса», но позволяет ставить отметки за человека.
4. Ограничить срок токена имперсонации (например 1 ч вместо `session_ttl_hours`) и проверять
   `emp.active` в `current_principal` при `imp`.
