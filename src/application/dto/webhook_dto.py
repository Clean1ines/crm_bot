from dataclasses import asdict, dataclass


@dataclass(slots=True)
class WebhookAckDto:
    ok: bool = True

    def to_dict(self) -> dict[str, bool]:
        return asdict(self)
