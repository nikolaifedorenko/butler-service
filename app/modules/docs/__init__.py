"""Модуль docs — документы: заявления (.docx по шаблонам), сетка Графика в
Excel/PDF, шаблоны документов (фаза C4, EXECUTION-SPEC-v2 §7 + §11.2 G2).

Слои: application (doc_render — виды заявлений и рендер .docx; grid_docx —
сетка «ФИО × дни»; doc_templates — шаблоны из key-value хранилища core),
interface (docs_api), domain/ports/adapters — тривиальные (ORM-моделей у модуля
нет; StatementKind живёт в employees).

G2: чистый транспорт рендера (встроенный PDF на reportlab, бывший
app/pdf_render.py) — в **core/render.py**: его используют docs, night и
timesheet (экспорт Графика), не завися друг от друга (R3).
"""
