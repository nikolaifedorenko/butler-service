"""Application-слой notify (публичная граница модуля, R3/R4).

Раздел-потребитель (ночной отчёт, электрокары, …) передаёт сюда готовый текст,
получателей и вложения; модуль не знает про ночной отчёт. Всё, что нужно другим
модулям и legacy-коду, импортируется отсюда или из подмодулей application.*.
"""
from ..domain.templates import items_block  # noqa: F401
from .catalog import (  # noqa: F401
    NotifyChat,
    NotifyDispatch,
    NotifyTemplate,
    ResponsibilityService,
)
from .chats import chats_from_updates, list_chats, refresh_chats  # noqa: F401
from .config import (  # noqa: F401
    NOTIFY_KEYS,
    NotifyConfig,
    load_config,
    mask_secret,
    public_config,
    save_config,
)
from .dispatch import (  # noqa: F401
    Attachment,
    attachments_of,
    deliver,
    dispatch_dict,
    journal_of,
    resend,
    send_group,
)
from .recipients import group_by_service, message_context, service_chat_ids  # noqa: F401
from .templates import (  # noqa: F401
    DEFAULT_TEMPLATES,
    DOMAIN_TITLES,
    PLACEHOLDERS,
    render_template,
    save_template,
    template_of,
    templates_payload,
)
