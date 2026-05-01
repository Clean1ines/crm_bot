import io
import json
import re

from src.infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


class ChunkerService:
    """
    FIXED version:
    - structure-aware chunking (headers first)
    - sentence-safe splitting
    - preserves meaning blocks
    """

    def __init__(self, chunk_size: int = 800, overlap: int = 100):
        self.chunk_size = chunk_size
        self.overlap = overlap

    def extract_text_from_pdf(self, file_bytes: bytes | bytearray) -> str:
        text = ""
        try:
            from PyPDF2 import PdfReader

            pdf_reader = PdfReader(io.BytesIO(file_bytes))
            for page in pdf_reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        except Exception as e:
            logger.error(f"PDF extraction failed: {e}")
            raise ValueError(f"Failed to extract text from PDF: {e}")

        return self._clean_text(text)

    def extract_text_from_json(self, file_bytes: bytes | bytearray) -> str:
        try:
            payload = json.loads(file_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            logger.error("JSON extraction failed", extra={"error": str(exc)})
            raise ValueError("Invalid JSON structure") from exc

        intent_sections = self._intent_sections_from_json(payload)
        if intent_sections:
            return self._clean_text("\n\n".join(intent_sections))

        generic_text = "\n".join(self._flatten_json_text(payload))
        return self._clean_text(generic_text)

    def _clean_text(self, text: str) -> str:
        """
        FIX: убираем мусорные переносы и склейки PDF
        """
        text = text.replace("\r", "\n")

        # склеиваем сломанные переносы строк
        text = re.sub(r"(?<!\n)\n(?!\n)", " ", text)

        # нормализуем пробелы
        text = re.sub(r"[ \t]+", " ", text)

        # восстанавливаем абзацы
        text = re.sub(r"\n{3,}", "\n\n", text)

        return text.strip()

    def chunk_text(self, text: str) -> list[str]:
        """
        Split extracted text into stable RAG chunks.

        Runtime guarantee:
        - large text must never collapse into one giant chunk;
        - Markdown headers are preserved as useful context when possible;
        - if structure detection fails, fallback still splits by size.
        """
        clean_text = self._normalized_input(text)
        if not clean_text:
            return []

        if self._should_split_directly(clean_text):
            return self._non_empty_chunks(self._split_buffer(clean_text))

        chunks = self._chunk_markdown_sections(clean_text)
        if chunks:
            return self._non_empty_chunks(chunks)

        return self._non_empty_chunks(self._split_buffer(clean_text))

    def _normalized_input(self, text: str) -> str:
        if not text:
            return ""

        return self._clean_text(text)

    def _should_split_directly(self, text: str) -> bool:
        # Fast and safe path: if text is already one big cleaned block,
        # split it directly. This protects runtime uploads from becoming
        # a single huge knowledge chunk.
        return len(text) >= self.chunk_size and "\n#" not in text

    def _chunk_markdown_sections(self, text: str) -> list[str]:
        sections = re.split(r"(?:^|\n)(#{1,3}\s[^\n]+)", text)

        builder = _SectionChunkBuilder(chunker=self)
        for part in sections:
            builder.add(part)

        return builder.finish()

    def _split_buffer(self, text: str) -> list[str]:
        """
        sentence-aware splitting
        """
        if len(text) <= self.chunk_size:
            return [text]

        chunks = []
        start = 0

        while start < len(text):
            end = min(start + self.chunk_size, len(text))

            # режем по предложениям
            cut = max(
                text.rfind(". ", start, end),
                text.rfind("! ", start, end),
                text.rfind("? ", start, end),
                text.rfind("\n", start, end),
            )

            if cut > start:
                end = cut + 1

            chunk = text[start:end].strip()

            if chunk:
                chunks.append(chunk)

            # Если дошли до конца текста — завершаем цикл.
            # Иначе overlap вернёт start назад и можно бесконечно
            # повторять последний хвост документа.
            if end >= len(text):
                break

            next_start = max(end - self.overlap, 0)

            # Защита от не-прогресса: при странных cut/overlap
            # следующий start обязан двигаться вправо.
            if next_start <= start:
                next_start = end

            start = next_start

        return chunks

    def _non_empty_chunks(self, chunks: list[str]) -> list[str]:
        return [chunk.strip() for chunk in chunks if chunk.strip()]

    async def process_file(
        self, file_bytes: bytes | bytearray, filename: str
    ) -> list[str]:
        filename_lower = filename.lower()

        if filename_lower.endswith((".txt", ".md")):
            text = file_bytes.decode("utf-8", errors="ignore")
            text = self._clean_text(text)

        elif filename_lower.endswith(".json"):
            text = self.extract_text_from_json(file_bytes)

        elif filename_lower.endswith(".pdf"):
            text = self.extract_text_from_pdf(file_bytes)

        else:
            raise ValueError(f"Unsupported file type: {filename}")

        if not text.strip():
            logger.warning(f"Empty text extracted from {filename}")
            return []

        return self.chunk_text(text)

    def _intent_sections_from_json(self, payload: object) -> list[str]:
        if not isinstance(payload, dict):
            return []

        raw_intents = payload.get("intents")
        if not isinstance(raw_intents, dict):
            return []

        sections: list[str] = []
        for intent_name, intent_payload in raw_intents.items():
            if not isinstance(intent_payload, dict):
                continue

            lines = [f"## {str(intent_name).strip()}"]
            answer = self._json_text_value(intent_payload.get("answer"))
            if answer:
                lines.append(f"answer: {answer}")

            for field_name in ("synonyms", "keywords", "patterns"):
                field_values = self._string_list_from_json(
                    intent_payload.get(field_name)
                )
                if field_values:
                    lines.append(f"{field_name}: {', '.join(field_values)}")

            if len(lines) > 1:
                sections.append("\n".join(lines))

        return sections

    def _flatten_json_text(self, payload: object, *, path: str = "") -> list[str]:
        if isinstance(payload, dict):
            dict_lines: list[str] = []
            for key, value in payload.items():
                key_path = f"{path}.{key}" if path else str(key)
                dict_lines.extend(self._flatten_json_text(value, path=key_path))
            return dict_lines

        if isinstance(payload, list):
            list_lines: list[str] = []
            for index, value in enumerate(payload):
                index_path = f"{path}[{index}]" if path else f"[{index}]"
                list_lines.extend(self._flatten_json_text(value, path=index_path))
            return list_lines

        text_value = self._json_text_value(payload)
        if not text_value:
            return []

        return [f"{path}: {text_value}" if path else text_value]

    def _json_text_value(self, value: object) -> str:
        if isinstance(value, bool) or value is None:
            return ""
        if isinstance(value, (int, float, str)):
            return str(value).strip()
        return ""

    def _string_list_from_json(self, value: object) -> list[str]:
        if not isinstance(value, list):
            return []

        result: list[str] = []
        for item in value:
            text_value = self._json_text_value(item)
            if text_value:
                result.append(text_value)
        return result


class _SectionChunkBuilder:
    def __init__(self, *, chunker: ChunkerService) -> None:
        self._chunker = chunker
        self._chunks: list[str] = []
        self._current_header = ""
        self._buffer = ""

    def add(self, raw_part: str) -> None:
        part = raw_part.strip()
        if not part:
            return

        if _is_markdown_header(part):
            self._flush_buffer()
            self._current_header = _header_text(part)
            return

        self._add_body_part(part)

    def finish(self) -> list[str]:
        self._flush_buffer()
        return self._chunks

    def _add_body_part(self, part: str) -> None:
        combined = self._with_current_header(part)

        if len(combined) >= self._chunker.chunk_size:
            self._flush_buffer()
            self._chunks.extend(self._chunker._split_buffer(combined))
            return

        self._append_to_buffer(combined)

    def _with_current_header(self, part: str) -> str:
        if not self._current_header:
            return part

        return f"{self._current_header}\n{part}".strip()

    def _append_to_buffer(self, combined: str) -> None:
        next_buffer = (
            f"{self._buffer}\n\n{combined}".strip() if self._buffer else combined
        )

        if len(next_buffer) >= self._chunker.chunk_size:
            self._flush_buffer()
            self._buffer = combined
            return

        self._buffer = next_buffer

    def _flush_buffer(self) -> None:
        if not self._buffer.strip():
            return

        self._chunks.extend(self._chunker._split_buffer(self._buffer.strip()))
        self._buffer = ""


def _is_markdown_header(text: str) -> bool:
    return re.match(r"^#{1,3}\s", text) is not None


def _header_text(text: str) -> str:
    return text.replace("#", "").strip()
