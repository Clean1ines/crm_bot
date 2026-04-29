from typing import Protocol


class LoggerPort(Protocol):
    def debug(
        self,
        message: str | None = None,
        *args: object,
        **kwargs: object,
    ) -> object: ...
    def info(
        self,
        message: str | None = None,
        *args: object,
        **kwargs: object,
    ) -> object: ...
    def warning(
        self,
        message: str | None = None,
        *args: object,
        **kwargs: object,
    ) -> object: ...
    def error(
        self,
        message: str | None = None,
        *args: object,
        **kwargs: object,
    ) -> object: ...
    def exception(
        self,
        message: str | None = None,
        *args: object,
        **kwargs: object,
    ) -> object: ...


class NullLogger:
    def debug(
        self,
        message: str | None = None,
        *args: object,
        **kwargs: object,
    ) -> None:
        pass

    def info(
        self,
        message: str | None = None,
        *args: object,
        **kwargs: object,
    ) -> None:
        pass

    def warning(
        self,
        message: str | None = None,
        *args: object,
        **kwargs: object,
    ) -> None:
        pass

    def error(
        self,
        message: str | None = None,
        *args: object,
        **kwargs: object,
    ) -> None:
        pass

    def exception(
        self,
        message: str | None = None,
        *args: object,
        **kwargs: object,
    ) -> None:
        pass
