import io
import json
import re

from src.domain.project_plane.json_types import JsonObject
from src.infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


class ChunkerService:
    """
    Extractor-level chunker.

    It does not build business semantic metadata. Its job is only:
    - extract source text;
    - preserve structure when source has headings/lists;
    - split large text on natural boundaries without overlap fragments.
    """

    def __init__(self, chunk_size: int = 2400, overlap: int = 0):
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
            return self._clean_structured_text("\n\n".join(intent_sections))

        generic_text = "\n".join(self._flatten_json_text(payload))
        return self._clean_text(generic_text)

    def _clean_text(self, text: str) -> str:
        text = text.replace("\r", "\n")
        text = re.sub(r"(?<!\n)\n(?!\n)", " ", text)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _clean_structured_text(self, text: str) -> str:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        lines = [re.sub(r"[ \t]+", " ", line).rstrip() for line in text.split("\n")]
        text = "\n".join(lines)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def chunk_text(self, text: str) -> list[str]:
        clean_text = self._normalized_input(text)
        if not clean_text:
            return []

        if re.search(r"(?m)^#{1,6}\s+\S", clean_text):
            chunks = self._chunk_markdown_sections(clean_text)
            if chunks:
                return self._non_empty_chunks(chunks)

        return self._non_empty_chunks(
            self._split_text_by_budget(clean_text, budget=self.chunk_size)
        )

    def _normalized_input(self, text: str) -> str:
        if not text:
            return ""

        if re.search(r"(?m)^#{1,6}\s+\S", text):
            return self._clean_structured_text(text)

        return self._clean_text(text)

    def _chunk_markdown_sections(self, text: str) -> list[str]:
        sections = [
            section.strip()
            for section in re.split(r"(?m)(?=^#{1,6}\s+\S)", text)
            if section.strip()
        ]

        chunks: list[str] = []
        for section in sections:
            chunks.extend(self._split_markdown_section(section))
        return chunks

    def _split_markdown_section(self, section: str) -> list[str]:
        if len(section) <= self.chunk_size:
            return [section]

        lines = section.splitlines()
        if not lines or not _is_markdown_header(lines[0]):
            return self._split_text_by_budget(section, budget=self.chunk_size)

        header = lines[0].strip()
        body = "\n".join(lines[1:]).strip()
        if not body:
            return [header]

        prefix = f"{header}\n\n"
        budget = self.chunk_size - len(prefix)
        if budget < 400:
            return self._split_text_by_budget(section, budget=self.chunk_size)

        return [
            f"{prefix}{chunk}".strip()
            for chunk in self._split_text_by_budget(body, budget=budget)
            if chunk.strip()
        ]

    def _split_text_by_budget(self, text: str, *, budget: int) -> list[str]:
        if len(text) <= budget:
            return [text]

        paragraphs = [
            part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()
        ]
        if not paragraphs:
            return self._split_long_plain_text(text, budget=budget)

        chunks: list[str] = []
        current = ""

        for paragraph in paragraphs:
            candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
            if len(candidate) <= budget:
                current = candidate
                continue

            if current:
                chunks.append(current)
                current = ""

            if len(paragraph) <= budget:
                current = paragraph
                continue

            chunks.extend(self._split_long_plain_text(paragraph, budget=budget))

        if current:
            chunks.append(current)

        return chunks

    def _split_long_plain_text(self, text: str, *, budget: int) -> list[str]:
        chunks: list[str] = []
        start = 0

        while start < len(text):
            end = min(start + budget, len(text))
            if end >= len(text):
                chunk = text[start:].strip()
                if chunk:
                    chunks.append(chunk)
                break

            cut = self._best_boundary_cut(text, start=start, end=end)
            if cut <= start:
                cut = end

            chunk = text[start:cut].strip()
            if chunk:
                chunks.append(chunk)

            start = self._skip_separators(text, cut)

        return chunks

    def _best_boundary_cut(self, text: str, *, start: int, end: int) -> int:
        lower_bound = start + max(120, (end - start) // 2)
        candidates = (
            text.rfind("\n\n", lower_bound, end),
            text.rfind("\n- ", lower_bound, end),
            text.rfind("\n* ", lower_bound, end),
            text.rfind(". ", lower_bound, end),
            text.rfind("! ", lower_bound, end),
            text.rfind("? ", lower_bound, end),
            text.rfind("; ", lower_bound, end),
            text.rfind(", ", lower_bound, end),
            text.rfind(" ", lower_bound, end),
        )
        return max(candidates)

    def _skip_separators(self, text: str, index: int) -> int:
        while index < len(text) and text[index].isspace():
            index += 1
        return index

    def _non_empty_chunks(self, chunks: list[str]) -> list[str]:
        return [
            chunk.strip()
            for chunk in chunks
            if chunk.strip() and not re.fullmatch(r"[-*_—–]{3,}", chunk.strip())
        ]

    async def process_file(
        self, file_bytes: bytes | bytearray, filename: str
    ) -> list[str | JsonObject]:
        filename_lower = filename.lower()

        if filename_lower.endswith(".md"):
            text = file_bytes.decode("utf-8", errors="ignore")

        elif filename_lower.endswith(".txt"):
            text = file_bytes.decode("utf-8", errors="ignore")

        elif filename_lower.endswith(".json"):
            text = self.extract_text_from_json(file_bytes)

        elif filename_lower.endswith(".pdf"):
            text = self.extract_text_from_pdf(file_bytes)

        else:
            raise ValueError(f"Unsupported file type: {filename}")

        if not text.strip():
            logger.warning(f"Empty text extracted from {filename}")
            return []

        chunks: list[str | JsonObject] = []
        chunks.extend(self.chunk_text(text))
        return chunks

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


def _is_markdown_header(text: str) -> bool:
    return re.match(r"^#{1,6}\s+\S", text.strip()) is not None
