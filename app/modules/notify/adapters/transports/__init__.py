"""Транспорты доставки — единственные места, где приложение выходит в сеть.

Telegram Bot API (httpx) и SMTP/MS Exchange (smtplib). Контракт сбоя —
ports/transports.TransportError; в тестах leaf-функции (http_sender, smtp_mailer)
подменяются заглушками (monkeypatch), прогон в интернет не выходит.
"""
