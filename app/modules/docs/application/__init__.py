"""Application-слой docs — публичная граница модуля (R3/R4).

Потребители: timesheet (hours_text, grid_docx — экспорт Графика), settings
(doc_templates), night (docx→pdf через core.render), bootstrap (DOC_TYPES).
Импорт — подмодулями: from app.modules.docs.application.doc_render import …
"""
