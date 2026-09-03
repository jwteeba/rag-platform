"""Content-type-aware extraction of UTF-8 text from uploaded bytes."""

from __future__ import annotations

import io


def extract_text(*, data: bytes, content_type: str) -> str:
    if content_type in {"text/plain", "text/markdown"}:
        return data.decode("utf-8")
    if content_type == "application/pdf":
        import fitz

        with fitz.open(stream=data, filetype="pdf") as document:
            return "\n".join(page.get_text() for page in document)
    if content_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        from docx import Document as DocxDocument

        return "\n".join(paragraph.text for paragraph in DocxDocument(io.BytesIO(data)).paragraphs)
    if content_type in {"image/png", "image/jpeg"}:
        import pytesseract
        from PIL import Image

        return str(pytesseract.image_to_string(Image.open(io.BytesIO(data))))
    raise ValueError(f"unsupported processing content type: {content_type}")
