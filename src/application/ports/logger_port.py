from typing import Protocol, Any


class LoggerPort(Protocol):
    def debug(self, message: str, *args: Any, **kwargs: Any) -> None: ...
    def info(self, message: str, *args: Any, **kwargs: Any) -> None: ...
    def warning(self, message: str, *args: Any, **kwargs: Any) -> None: ...
    def error(self, message: str, *args: Any, **kwargs: Any) -> None: ...
    def exception(self, message: str, *args: Any, **kwargs: Any) -> None: ...


class NullLogger:
    def debug(self, message: str, *args: Any, **kwargs: Any) -> None: pass
    def info(self, message: str, *args: Any, **kwargs: Any) -> None: pass
    def warning(self, message: str, *args: Any, **kwargs: Any) -> None: pass
    def error(self, message: str, *args: Any, **kwargs: Any) -> None: pass
    def exception(self, message: str, *args: Any, **kwargs: Any) -> None: pass
