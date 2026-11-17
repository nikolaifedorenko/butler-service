"""Публичные чистые правила шахматки для тех, кто читает её данные (представления): сетка половинок
суток, естественный порядок объектов, счёт пожеланий и типы дня. Сама предметная область (``domain``)
приватна: другие модули берут нужное отсюда (граница R3)."""
from ..domain.allocate import natural_key  # noqa: F401
from ..domain.halfday import AM, PIECE_BASE, PM, Piece, ooo_span, overlaps, pieces, pos, segments  # noqa: F401
from ..domain.prefs import scorer  # noqa: F401
from ..domain.types import OFF, StayDay  # noqa: F401
