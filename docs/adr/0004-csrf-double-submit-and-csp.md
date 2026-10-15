# ADR-0004. CSRF: double-submit cookie; CSP: script-src 'self', style-src с 'unsafe-inline'

**Статус:** принят 15.10.2026

## Контекст
Сессия — httponly-cookie; интерфейс — SPA без сборки (inline-атрибутов
`style="…"` 300+, inline-скриптов и onclick-обработчиков нет — проверено grep'ом).

## Решение
1. CSRF — double-submit: токен в JS-читаемой cookie (`SameSite=Lax`) + заголовок
   `X-CSRF-Token`, сравнение `secrets.compare_digest` побайтово, проверка строго
   ДО вызова обработчика (отклонённый запрос не имеет побочных эффектов).
   `POST /api/auth/login` исключён (login-CSRF — отдельная поверхность низкой
   критичности). Ротация токена при логине не делается — для double-submit
   достаточна нечитаемость cookie с чужого origin.
2. CSP: `script-src 'self'` (строго), `style-src 'self' 'unsafe-inline'` —
   осознанный компромисс: вычищать 300+ inline-style в шаблонах без сборки
   несоразмерно дорого; основной вектор (инъекция скрипта) закрыт.
   `object-src/base-uri/form-action` закрыты, `frame-ancestors 'none'`,
   `img-src 'self' data: blob:` (SVG-фавикон, скачивание PDF через
   createObjectURL). Флаг `CSP_REPORT_ONLY=1` для осторожной раскатки.
3. HSTS — только когда запрос фактически по TLS (`X-Forwarded-Proto` при
   `TRUST_PROXY_HEADERS=1`, иначе схема запроса).

## Последствия
Любые новые inline-скрипты в шаблонах сломаются в браузере — это намеренный
барьер; стили — через CSS-классы где возможно. Внешние ресурсы (CDN-шрифты и
т.п.) запрещены — только self-hosted.
