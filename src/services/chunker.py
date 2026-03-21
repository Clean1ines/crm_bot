import io
import re
from typing import List
import PyPDF2  # оставляем как у тебя
from src.core.logging import get_logger

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

    def chunk_text(self, text: str) -> List[str]:
        if not text:
            return []

        text = self._clean_text(text)

        # 1. режем по заголовкам Markdown
        sections = re.split(r'(\n#{1,3}\s[^\n]+)', text)

        chunks = []
        current_header = ""

        buffer = ""

        for part in sections:
            part = part.strip()
            if not part:
                continue

            # если это заголовок
            if re.match(r'^#{1,3}\s', part):
                current_header = part.replace("#", "").strip()
                continue

            # основной текст
            combined = f"{current_header}\n{part}".strip() if current_header else part

            # если маленький — копим
            if len(combined) < self.chunk_size:
                buffer += "\n" + combined
                continue

            # если есть накопленный буфер — флашим
            if buffer.strip():
                chunks.extend(self._split_buffer(buffer))
                buffer = ""

            chunks.extend(self._split_buffer(combined))

        if buffer.strip():
            chunks.extend(self._split_buffer(buffer))

        return [c.strip() for c in chunks if c.strip()]

    def _split_buffer(self, text: str) -> List[str]:
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

            start = max(end - self.overlap, 0)

            if start >= len(text):
                break

        return chunks

    async def process_file(self, file_bytes: bytes, filename: str) -> List[str]:
        filename_lower = filename.lower()

        if filename_lower.endswith('.txt'):
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