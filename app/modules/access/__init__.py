"""Модуль access — вход/выход, сессии, impersonation и управление правами.

Модели (User, AccessGroup/Member, AccessGrant) живут в core/identity — это
фундамент аутентификации всего приложения (решение фазы C1); модуль access —
их ИНТЕРФЕЙС: login/logout/impersonation (auth_routes) и экран «Права доступа»
(access_api). can_manage_user — ролевой страж анти-эскалации в core/auth_guards
(задокументированное исключение ADR-0006/§0 п.8) — остаётся в core.
Слои domain/application/ports/adapters — тривиальные (код перенесён «как есть»).
"""
