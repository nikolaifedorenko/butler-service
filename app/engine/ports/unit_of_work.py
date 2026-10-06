from typing import Protocol


class UnitOfWork(Protocol):         # атомарность
    def __enter__(self) -> "UnitOfWork": ...
    def __exit__(self, *exc) -> None: ...   # commit при успехе, rollback при исключении
