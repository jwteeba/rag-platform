from __future__ import annotations

import io

import fitz
from docx import Document

from rag_platform.document_management.application.services.text_extraction import extract_text


def test_extracts_plain_text_and_markdown() -> None:
    assert (
        extract_text(data=b"# heading\nhello", content_type="text/markdown") == "# heading\nhello"
    )


def test_extracts_pdf_text() -> None:
    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_text((72, 72), "PDF content")
    data = pdf.tobytes()
    pdf.close()

    assert "PDF content" in extract_text(data=data, content_type="application/pdf")


def test_extracts_docx_text() -> None:
    document = Document()
    document.add_paragraph("DOCX content")
    output = io.BytesIO()
    document.save(output)

    assert "DOCX content" in extract_text(
        data=output.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


def test_extracts_image_using_ocr(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from PIL import Image

    image = Image.new("RGB", (1, 1), "white")
    output = io.BytesIO()
    image.save(output, format="PNG")
    monkeypatch.setattr("pytesseract.image_to_string", lambda _: "OCR content")

    assert extract_text(data=output.getvalue(), content_type="image/png") == "OCR content"
