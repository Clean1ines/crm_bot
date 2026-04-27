from typing import Protocol


class LoggerPort(Protocol):
    def debug(self, message: str, *args: object, **kwargs: object) -> None: ...
    def info(self, message: str, *args: object, **kwargs: object) -> None: ...
    def warning(self, message: str, *args: object, **kwargs: object) -> None: ...
    def error(self, message: str, *args: object, **kwargs: object) -> None: ...
    def exception(self, message: str, *args: object, **kwargs: object) -> None: ...


class NullLogger:
    def debug(self, message: str, *args: object, **kwargs: object) -> None: pass
    def info(self, message: str, *args: object, **kwargs: object) -> None: pass
    def warning(self, message: str, *args: object, **kwargs: object) -> None: pass
    def error(self, message: str, *args: object, **kwargs: object) -> None: pass
    def exception(self, message: str, *args: object, **kwargs: object) -> None: pass
