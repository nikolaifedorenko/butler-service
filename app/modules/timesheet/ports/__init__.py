"""Порты (2.6, 8.3): только Protocol + доменные типы. Контрактные dataclass'ы
(PeriodState, ClosingInputs, Employment) физически живут в domain/types/entities.py
(v7.1/F-06). ClockPort не вводится: now снимается в composition root и передаётся
параметром (7.1, v7.1/F-15)."""
