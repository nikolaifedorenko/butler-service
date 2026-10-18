"""Form-login с редиректом (16.10.2026): классическая связка «submit → 303» для
браузерных менеджеров паролей — плашка «Сохранить пароль?» появляется сразу после
входа, а не отложенно (SPA-вход через preventDefault+fetch менеджеры откладывают)."""
from __future__ import annotations

import unittest

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app, init_db  # noqa: E402

init_db()
client = TestClient(app)


class TestLoginForm(unittest.TestCase):
    def _post(self, username: str, password: str):
        return client.post("/api/auth/login-form",
                           data={"username": username, "password": password},
                           follow_redirects=False)

    def test_00_get_redirects_home(self):
        """GET на адрес действия формы (восстановленная вкладка) — 303 домой, не JSON 404."""
        r = client.get("/api/auth/login-form", follow_redirects=False)
        self.assertEqual(r.status_code, 303)
        self.assertEqual(r.headers["location"], "/")

    def test_01_success_redirects_home_with_session(self):
        r = self._post("admin", "demo1234")
        self.assertEqual(r.status_code, 303, r.text)
        self.assertEqual(r.headers["location"], "/")
        self.assertTrue(r.headers.get("set-cookie"), "сессия выставлена редиректом")

    def test_02_wrong_password_redirects_with_code(self):
        r = self._post("admin", "wrong-password")
        self.assertEqual(r.status_code, 303)
        self.assertEqual(r.headers["location"], "/?login_error=auth")
        self.assertIsNone(r.headers.get("set-cookie"), "сессия при ошибке не выдаётся")

    def test_03_session_from_form_login_works(self):
        c = TestClient(app)
        r = c.post("/api/auth/login-form", data={"username": "admin", "password": "demo1234"},
                   follow_redirects=False)
        self.assertEqual(r.status_code, 303)
        me = c.get("/api/auth/me")
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["user"]["username"], "admin")

    def test_04_json_login_still_works(self):
        c = TestClient(app)
        r = c.post("/api/auth/login", json={"username": "admin", "password": "demo1234"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["user"]["username"], "admin")


if __name__ == "__main__":
    unittest.main()
