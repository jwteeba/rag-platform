"""Input/output guardrails: sanitization and prompt-injection defense.

Pure functions — no framework imports, no I/O. Every layer that accepts
user-supplied text (retrieval, generation, document filenames) calls these
before passing content downstream.

Prompt-injection detection uses a deny-list of well-known attack patterns
(role-override, instruction-override, jailbreak prefixes). It is intentionally
conservative: false positives are surfaced as `GuardrailViolationError` so the
caller can decide whether to reject or log-and-continue. The list is not
exhaustive — it is a first-pass defense-in-depth layer, not a silver bullet.

Output sanitization strips model-generated content that could exfiltrate
system-prompt fragments or embed executable markup before it reaches the client.
"""

from __future__ import annotations

import re
import unicodedata

from rag_platform.core.exceptions import GuardrailViolationError
from rag_platform.core.metrics import GUARDRAIL_REJECTIONS, USER_GUARDRAIL_REJECTIONS

_MAX_QUERY_CHARS = 4_000  # hard ceiling before any LLM token budget applies
_MAX_FILENAME_CHARS = 255

# Patterns that strongly indicate a prompt-injection attempt.
# Each tuple is (human-readable label, compiled pattern).
_INJECTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # Role / persona override
    (
        "role_override",
        re.compile(r"\bignore\s+(all\s+)?(previous|prior|above)\s+instructions?\b", re.I),
    ),
    ("system_override", re.compile(r"\bnew\s+(system\s+)?prompt\b", re.I)),
    ("persona_jailbreak", re.compile(r"\bact\s+as\s+(if\s+you\s+(are|were)|a\b)", re.I)),
    ("dan_jailbreak", re.compile(r"\bdo\s+anything\s+now\b|\bDAN\b", re.I)),
    # Instruction injection via delimiter smuggling
    ("delimiter_injection", re.compile(r"<\s*/?\s*(system|user|assistant|instruction)\s*>", re.I)),
    ("bracket_injection", re.compile(r"\[\s*(system|inst|instruction)\s*\]", re.I)),
    # Exfiltration / leakage probes
    (
        "prompt_leak",
        re.compile(
            r"\b(repeat|print|output|reveal|show|tell me)\s+(your\s+)?(system\s+)?(prompt|instructions?|context)\b",  # noqa: E501
            re.I,
        ),
    ),
    ("token_smuggling", re.compile(r"\\u00[0-9a-f]{2}|\\x[0-9a-f]{2}", re.I)),
]

# Patterns stripped from LLM output before returning to the client.
_OUTPUT_STRIP_PATTERNS: list[re.Pattern[str]] = [
    # HTML/script tags that could be rendered in a downstream UI
    re.compile(r"<script[\s\S]*?</script>", re.I),
    re.compile(r"<iframe[\s\S]*?</iframe>", re.I),
    # Markdown-fenced system/instruction blocks sometimes hallucinated by models
    re.compile(r"```\s*(system|instruction)[\s\S]*?```", re.I),
]


def sanitize_query(text: str) -> str:
    """Normalize and length-cap a user query.

    - NFC-normalizes Unicode (prevents homoglyph attacks).
    - Strips leading/trailing whitespace.
    - Collapses internal runs of whitespace to a single space.
    - Truncates to `_MAX_QUERY_CHARS` (hard ceiling; callers should also
      enforce schema-level `max_length` for earlier rejection).

    Does *not* raise — sanitization is always safe to apply.
    """
    text = unicodedata.normalize("NFC", text)
    text = text.strip()
    text = re.sub(r"\s+", " ", text)
    return text[:_MAX_QUERY_CHARS]


def sanitize_filename(name: str) -> str:
    """Normalize a filename: strip path traversal components and control chars."""
    name = unicodedata.normalize("NFC", name)
    # Strip any directory component — only the basename is kept.
    name = re.sub(r"[/\\]", "_", name)
    # Remove null bytes and other ASCII control characters.
    name = re.sub(r"[\x00-\x1f\x7f]", "", name)
    name = name.strip(". ")
    return name[:_MAX_FILENAME_CHARS] or "upload"


def sanitize_output(text: str) -> str:
    """Strip potentially dangerous patterns from LLM-generated output."""
    for pattern in _OUTPUT_STRIP_PATTERNS:
        text = pattern.sub("", text)
    return text.strip()


def check_prompt_injection(text: str, *, path: str = "unknown", user_id: str = "anonymous") -> None:
    """Raise `GuardrailViolationError` if `text` matches a known injection pattern.

    Called on every user-supplied query before it is embedded or sent to the
    LLM. The check is applied *after* `sanitize_query` so normalization
    cannot be used to bypass pattern matching.
    """
    for label, pattern in _INJECTION_PATTERNS:
        if pattern.search(text):
            GUARDRAIL_REJECTIONS.labels(rule=label, path=path).inc()
            USER_GUARDRAIL_REJECTIONS.labels(rule=label, user_id=user_id).inc()
            raise GuardrailViolationError(
                f"Input rejected by guardrail '{label}'. "
                "Prompt injection or policy-violating content detected."
            )
