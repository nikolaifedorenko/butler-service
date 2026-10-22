"""core — инфраструктурное ядро приложения (EXECUTION-SPEC-v2, фаза C1).

Конфигурация, БД-сессия, время, ошибки, безопасность, права, аудит, медиа,
идентичность (User/гранты), рендер-транспорт (render — встроенный PDF на reportlab,
бывший app/pdf_render, фаза C4/G2). Правило R5: core НЕ импортирует модули приложения
(app.api, app.services, app.models, app.modules.*) — только stdlib,
сторонние библиотеки и сам core. Composition root (main.py, bootstrap/) —
единственное место, которое знает все слои.
"""
