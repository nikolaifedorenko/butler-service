"""Транспорт Telegram Bot API.

Методы, которые нужны приложению:
  * ``getMe``      — проверка токена («Проверить бота» в настройках);
  * ``getUpdates`` — общий каталог чатов: бота добавляют в группы служб, и чаты
                     появляются здесь (закрепление за службой — в её карточке);
  * ``sendMessage``/``sendPhoto``/``sendVideo``/``sendDocument`` — доставка.

Адрес Bot API настраивается (``notify_telegram_api``) — в домене MS Exchange выход
в интернет обычно идёт через корпоративный прокси. Токен в сообщениях об ошибках
и в журнале не печатается: TransportError несёт только причину.

``getUpdates`` намеренно вызывается БЕЗ offset: приложение не обрабатывает команды
бота, а каталог чатов собирается из последних обновлений (Telegram хранит их сутки).
Подтверждение offset'ом «съело» бы обновления, которые могут понадобиться позже.
"""
from __future__ import annotations

from typing import Callable, Optional

from . import TransportError

# (url, payload, files, timeout) → ответ Bot API как dict
Sender = Callable[[str, Optional[dict], Optional[dict], float], dict]


def http_sender(url: str, payload: Optional[dict], files: Optional[dict], timeout: float) -> dict:
    """Отправитель по умолчанию: httpx (зависимость проекта, ничего нового не ставим).

    Отправитель отвечает ТОЛЬКО за доставку запроса и разбор JSON: проверку
    ``ok``/``error_code`` делает TelegramBot.call(), иначе подмена отправителя
    в тестах обходила бы обработку ошибок Bot API.
    """
    import httpx

    try:
        if files:
            r = httpx.post(url, data=payload or {}, files=files, timeout=timeout)
        else:
            r = httpx.post(url, json=payload or {}, timeout=timeout)
    except httpx.HTTPError as e:
        raise TransportError(f"Telegram недоступен: {type(e).__name__}") from e
    try:
        return r.json()
    except ValueError as e:
        raise TransportError(f"Telegram ответил не-JSON (HTTP {r.status_code})") from e


def _friendly(description: str, code) -> str:
    """Текст ошибки для пользователя: токен не показываем, причину объясняем."""
    d = (description or "").lower()
    if "unauthorized" in d or code == 401:
        return "Telegram отклонил токен бота (401 Unauthorized)"
    if "chat not found" in d or code == 400 and "chat" in d:
        return "Чат не найден: бот не добавлен в группу или не получил в ней ни одного сообщения"
    if "bot was blocked" in d or "user is deactivated" in d:
        return "Получатель заблокировал бота"
    if "too large" in d or "file is too big" in d:
        return "Файл больше лимита Telegram (50 МБ)"
    if description:
        return f"Telegram: {description[:200]}"
    return f"Telegram вернул ошибку (код {code})"


class TelegramBot:
    """Клиент Bot API: токен + необязательный свой отправитель (для тестов)."""

    def __init__(self, token: str, api_base: str = "https://api.telegram.org",
                 timeout: float = 20.0, sender: Optional[Sender] = None):
        if not (token or "").strip():
            raise TransportError("Токен бота Telegram не задан (Настройки → Чаты и Почта)")
        self.token = token.strip()
        self.api_base = (api_base or "https://api.telegram.org").rstrip("/")
        self.timeout = float(timeout or 20)
        self._sender = sender or http_sender

    def call(self, method: str, payload: Optional[dict] = None,
             files: Optional[dict] = None) -> dict:
        """Вызвать метод Bot API и проверить ответ. Токен в ошибку не попадает."""
        url = f"{self.api_base}/bot{self.token}/{method}"
        data = self._sender(url, payload, files, self.timeout)
        if not isinstance(data, dict) or not data.get("ok"):
            desc = data.get("description") if isinstance(data, dict) else ""
            code = data.get("error_code") if isinstance(data, dict) else "—"
            raise TransportError(_friendly(desc or "", code))
        return data

    # ── проверка и каталог ──
    def get_me(self) -> dict:
        """Кто такой бот: username нужен, чтобы понять «тот ли бот добавлен в группы»."""
        return self.call("getMe").get("result") or {}

    def get_updates(self, limit: int = 100) -> list[dict]:
        return self.call("getUpdates", {"limit": limit, "allowed_updates": []}).get("result") or []

    # ── доставка ──
    def send_message(self, chat_id: int, text: str) -> int:
        res = self.call("sendMessage", {"chat_id": chat_id, "text": text[:4096],
                                        "disable_web_page_preview": True}).get("result") or {}
        return int(res.get("message_id") or 0)

    def send_media(self, chat_id: int, files: list[tuple[str, bytes, str]],
                   caption: str = "") -> list[int]:
        """Отправить вложения: каждое своим сообщением (подпись — у первого).

        sendMediaGroup требует multipart со вложенным JSON и ограничен 10 файлами;
        поштучная отправка проще, надёжнее и работает с любым числом файлов
        (Telegram сам сложит соседние фото/видео в альбом).
        """
        ids: list[int] = []
        for i, (name, blob, mime) in enumerate(files):
            method, field = _media_method(mime)
            payload = {"chat_id": chat_id, "caption": caption[:1024]} if i == 0 and caption \
                else {"chat_id": chat_id}
            res = self.call(method, payload, files={field: (name, blob, mime)}).get("result") or {}
            ids.append(int(res.get("message_id") or 0))
        return ids


def _media_method(mime: str) -> tuple[str, str]:
    mime = (mime or "").lower()
    if mime.startswith("video/"):
        return "sendVideo", "video"
    if mime.startswith("image/"):
        return "sendPhoto", "photo"
    return "sendDocument", "document"
