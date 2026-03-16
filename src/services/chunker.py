"""
Text chunking service for splitting documents into manageable pieces.
Supports plain text and PDF files.
"""

import io
from typing import List
import PyPDF2  # type: ignore
from src.core.logging import get_logger

logger = get_logger(__name__)

class ChunkerService:
    """
    Service for chunking text documents.
    Splits text into overlapping chunks of a specified size.
    """

    def __init__(self, chunk_size: int = 500, overlap: int = 50):
        """
        Args:
            chunk_size: number of characters per chunk.
            overlap: number of characters to overlap between consecutive chunks.
        """
        self.chunk_size = chunk_size
        self.overlap = overlap

    def extract_text_from_pdf(self, file_bytes: bytes) -> str:
        """
        Extract text from a PDF file using PyPDF2.
        """
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
        return text

    def chunk_text(self, text: str) -> List[str]:
        """
        Split text into overlapping chunks.
        """
        if not text:
            return []
        chunks = []
        start = 0
        text_len = len(text)
        while start < text_len:
            end = min(start + self.chunk_size, text_len)
            # try to cut at a word boundary (last space within chunk)
            if end < text_len and text[end] not in (' ', '\n', '\t'):
                # find last space before end
                last_space = text.rfind(' ', start, end)
                if last_space > start:
                    end = last_space
            chunks.append(text[start:end].strip())
            start = end - self.overlap
            if start < 0:
                start = 0
            if start >= text_len:
                break
        return chunks

    async def process_file(self, file_bytes: bytes, filename: str) -> List[str]:
        """
        Process an uploaded file: extract text and split into chunks.
        Supported extensions: .txt, .pdf
        """
        filename_lower = filename.lower()
        if filename_lower.endswith('.txt'):
            # assume plain text
            text = file_bytes.decode('utf-8', errors='ignore')
        elif filename_lower.endswith('.pdf'):
            text = self.extract_text_from_pdf(file_bytes)
        else:
            raise ValueError(f"Unsupported file type: {filename}. Only .txt and .pdf are allowed.")

        if not text.strip():
            logger.warning(f"Empty text extracted from {filename}")
            return []
        return self.chunk_text(text)
