"""Лимит одновременных конвертаций LibreOffice (аудит, шаг 6.6, PERF-04).

Вместо настоящего soffice — скрипт, который «конвертирует» полсекунды и кладёт PDF в
--outdir. Проверяется: второй запрос не ждёт до 180 с и не запускает ещё один процесс, а
получает None (вызывающий соберёт PDF встроенным рендером); у каждого запуска свой профиль.
"""
from __future__ import annotations

import sys
import threading
import time

FAKE_SOFFICE = """import pathlib, sys, time
args = sys.argv[1:]
log = pathlib.Path({log!r})
log.open("a").write(" ".join(args) + "\\n")
time.sleep(0.5)
out = pathlib.Path(args[args.index("--outdir") + 1]) / "doc.pdf"
out.write_bytes(b"%PDF-fake")
"""


def test_second_conversion_does_not_wait_for_busy_libreoffice(tmp_path, monkeypatch):
    from app.core import render

    log = tmp_path / "calls.log"
    script = tmp_path / "fake_soffice.py"
    script.write_text(FAKE_SOFFICE.format(log=str(log)))
    exe = tmp_path / "soffice"               # обёртка на sh: путь к python может быть с пробелами
    exe.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n')
    exe.chmod(0o755)
    monkeypatch.setattr(render.shutil, "which", lambda name: str(exe) if name == "soffice" else None)
    monkeypatch.setattr(render, "LO_SLOTS", threading.BoundedSemaphore(1))
    monkeypatch.setattr(render, "LO_WAIT_S", 0.1)

    results = {}
    first = threading.Thread(target=lambda: results.setdefault("first", render.docx_to_pdf_libreoffice(b"x")))
    first.start()
    deadline = time.monotonic() + 10
    while not log.exists() and time.monotonic() < deadline:   # первый процесс запущен, держит слот
        time.sleep(0.02)
    results["second"] = render.docx_to_pdf_libreoffice(b"x")
    first.join(10)

    assert results == {"first": b"%PDF-fake", "second": None}
    calls = log.read_text().splitlines()
    assert len(calls) == 1, "при занятом слоте запустился второй LibreOffice"
    assert "-env:UserInstallation=file://" in calls[0]
    assert render.docx_to_pdf_libreoffice(b"x") == b"%PDF-fake"   # слот освободился
