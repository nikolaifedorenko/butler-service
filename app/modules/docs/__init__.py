"""Модуль docs — заявления сотрудников: виды, значения плейсхолдеров, тексты по умолчанию.

Слои: application (doc_render — виды заявлений и значения для бланка; doc_templates —
тексты из key-value хранилища core), interface (docs_api), adapters (orm — StatementKind),
domain/ports — тривиальные. Файлы DOCX и PDF собирает модуль exchange.
"""
