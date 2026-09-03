# ADR-0010 — Document Processing and Chunking Strategy

**Date:** 2026-09-02  
**Status:** Accepted  
**Phase:** 7 — Document processing pipeline

## Decision

After upload, a Celery task reads the raw object from MinIO, extracts text,
and stores `Chunk` rows before marking the document `ready`. Documents move
through `pending`, `processing`, `ready`, and `failed`; failures retry three
times and become `failed` only after the retry budget is exhausted.

Extraction is selected by MIME type: PyMuPDF for PDFs, `python-docx` for
DOCX, UTF-8 decoding for text/Markdown, and Tesseract OCR for PNG/JPEG.

Chunking uses a sliding window over whitespace-delimited tokens. The window
size, overlap, and maximum chunks are configurable. Sliding overlap retains
context crossing a chunk boundary, reducing retrieval misses compared with
non-overlapping fixed partitions. The stored `token_count` is therefore a
deterministic approximation, not an embedding-model tokenizer count; Phase 8
may swap the tokenizer while preserving chunk records and configuration shape.

## Consequences

- Chunk replacement is delete-and-insert in one transaction, so task retries
  cannot duplicate searchable content.
- `chunks.document_id` cascades on document deletion.
- Tesseract is installed in the worker/API image; production deployments
  should include language packs required by their documents.
