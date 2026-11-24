"""Статика перепроверяется при каждой загрузке: модули подключают друг друга без ?v=."""
from __future__ import annotations

import re


def test_static_scripts_and_styles_require_revalidation(client):
    for path in ("/static/js/core.js", "/static/js/app.js", "/static/js/modules/docs.js",
                 "/static/js/modules/employees.js", "/static/css/tokens.css", "/static/vendor/lit-html/lit-html.js"):
        r = client.get(path)
        assert r.status_code == 200, path
        assert r.headers["cache-control"] == "no-cache", path
        assert r.headers.get("etag"), path


def test_unmodified_static_is_answered_with_304(client):
    first = client.get("/static/js/core.js")
    again = client.get("/static/js/core.js", headers={"If-None-Match": first.headers["etag"]})
    assert again.status_code == 304


def test_service_worker_serves_only_the_versioned_print_child_key(client):
    worker = client.get("/sw.js")
    assert worker.status_code == 200
    stamp = re.search(r"const VERSION = 'tt-([\w.-]+)'", worker.text)[1]
    path = f"/static/js/print-page.js?v={stamp}"
    keys = re.findall(r"'(/static/js/print-page\.js(?:\?[^']*)?)'", worker.text)
    assert keys == [path]
    child = client.get(path)
    assert child.status_code == 200
    assert child.headers["cache-control"] == "no-cache"
