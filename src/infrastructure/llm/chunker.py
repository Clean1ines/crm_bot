import io
import re

import PyPDF2  # оставляем как у тебя

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

    def extract_text_from_pdf(self, file_bytes: bytes) -> str:
        text = ""
        try:
            pdf_reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
            for page in pdf_reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        except Exception as e:
            logger.error(f"PDF extraction failed: {e}")
            raise ValueError(f"Failed to extract text from PDF: {e}")

        return self._clean_text(text)

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
        sections = re.split(r'(?:^|\n)(#{1,3}\s[^\n]+)', text)

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

    async def process_file(self, file_bytes: bytes, filename: str) -> list[str]:
        filename_lower = filename.lower()

        if filename_lower.endswith(('.txt', '.md')):
            text = file_bytes.decode('utf-8', errors='ignore')
            text = self._clean_text(text)

        elif filename_lower.endswith('.pdf'):
            text = self.extract_text_from_pdf(file_bytes)

        else:
            raise ValueError(f"Unsupported file type: {filename}")

        if not text.strip():
            logger.warning(f"Empty text extracted from {filename}")
            return []

        return self.chunk_text(text)


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
        next_buffer = f"{self._buffer}\n\n{combined}".strip() if self._buffer else combined

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
    return re.match(r'^#{1,3}\s', text) is not None


def _header_text(text: str) -> str:
    return text.replace("#", "").strip()
