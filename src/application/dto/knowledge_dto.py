from dataclasses import asdict, dataclass


@dataclass(slots=True)
class KnowledgeUploadResultDto:
    message: str
    chunks: int

    @classmethod
    def create(cls, *, message: str, chunks: int) -> "KnowledgeUploadResultDto":
        return cls(message=message, chunks=chunks)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
