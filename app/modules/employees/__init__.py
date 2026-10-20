"""Модуль employees — каталог персонала и жизненный цикл сотрудника (фаза C4).

Слои: domain (группы графика, склонение имён — чистые), application (каталог
моделей для других модулей, трудоустройство, жизненный цикл), ports (тривиальный
— контрактов пока нет), adapters (orm — Employee/Department/Subdivision/
StatementKind/EmergencyContact/PositionHistory/EmploymentPeriod), interface
(роутер «Сотрудники»).

Публичная поверхность (R3/R4): другие модули импортируют только
``employees.application`` (модели — через ``application.catalog``). Корневой
``__init__`` намеренно НЕ ре-экспортирует application: ``lifecycle`` импортирует
границу timesheet (base_schedule/catalog), а timesheet — границу employees;
ранний ре-экспорт создал бы цикл инициализации пакетов.
"""
