"""Статика перепроверяется при каждой загрузке: модули подключают друг друга без ?v=."""
from __future__ import annotations


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
