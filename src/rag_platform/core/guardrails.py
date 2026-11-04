"""Composable input and output guardrails built on Guardrails AI.

Add a rule by implementing a ``Validator`` subclass and registering it with
``GuardrailPipeline``. The module-level functions at the bottom retain the
small API used by the application while the implementation stays extensible.
"""

from __future__ import annotations

import json
import re
import threading
import unicodedata
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from guardrails import Guard, OnFailAction  # type: ignore[import-untyped]
from guardrails.validators import Validator, register_validator  # type: ignore[import-untyped]
from guardrails_ai.types import (  # type: ignore[import-untyped]
    FailResult,
    PassResult,
    ValidationResult,
)

from rag_platform.core.exceptions import GuardrailViolationError
from rag_platform.core.metrics import GUARDRAIL_REJECTIONS, USER_GUARDRAIL_REJECTIONS

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

MAX_QUERY_CHARS = 4_000
MAX_FILENAME_CHARS = 255


@dataclass(frozen=True, slots=True)
class PatternRule:
    """A named regular-expression rule used by a registered validator."""

    name: str
    pattern: re.Pattern[str]
    message: str


@register_validator(name="rag_platform/pattern_blocklist", data_type="string")
class PatternBlocklistValidator(Validator):  # type: ignore[misc]
    """Reject text matching one or more named patterns.

    These local checks do not use Guardrails Hub inference or its CLI config.
    The lightweight initializer sets only the fields consumed by Guard.
    """

    def __init__(self, rules: Iterable[PatternRule]) -> None:
        self.rules = tuple(rules)
        self.on_fail_descriptor = OnFailAction.NOOP
        self.on_fail_method = None
        self._kwargs: dict[str, Any] = {}

    def validate(self, value: str, metadata: dict[str, Any]) -> ValidationResult:
        del metadata
        for rule in self.rules:
            if rule.pattern.search(value):
                return FailResult(error_message=f"{rule.name}: {rule.message}")
        return PassResult()


@dataclass(slots=True)
class GuardrailCheck:
    """One validator, constructed on first use when configured lazily."""

    name: str
    validator: Validator | None = None
    validator_factory: Callable[[], Validator] | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def get_validator(self) -> Validator:
        """Return the cached validator, constructing it once if needed."""
        with self._lock:
            if self.validator is None:
                if self.validator_factory is None:
                    raise RuntimeError(f"No validator configured for guardrail '{self.name}'.")
                self.validator = self.validator_factory()
            return self.validator


class GuardrailPipeline:
    """Run a collection of registered Guardrails AI validators in order."""

    def __init__(self, checks: Iterable[GuardrailCheck]) -> None:
        self._checks = tuple(checks)

    def validate(self, text: str, *, path: str = "unknown", user_id: str = "anonymous") -> None:
        for check in self._checks:
            validator = check.get_validator()
            # Guardrails 0.11 configures failure behavior on the validator,
            # rather than accepting it as an argument to Guard.use().
            validator.on_fail_descriptor = OnFailAction.NOOP
            validator.on_fail_method = None
            # Guardrails has its own Hub telemetry exporter, independent of
            # this application's OpenTelemetry settings. Disable its metrics
            # for this local validation path so requests never depend on the
            # Guardrails cloud trace endpoint.
            guard = Guard()
            guard.configure(allow_metrics_collection=False)
            result = guard.use(validator).validate(text)
            if not result.validation_passed:
                GUARDRAIL_REJECTIONS.labels(rule=check.name, path=path).inc()
                USER_GUARDRAIL_REJECTIONS.labels(rule=check.name, user_id=user_id).inc()
                raise GuardrailViolationError(
                    f"Input rejected by guardrail '{check.name}'. "
                    "Prompt injection or policy-violating content detected."
                )


class TextSanitizer(ABC):
    """Base class for deterministic text normalization policies."""

    @abstractmethod
    def sanitize(self, text: str) -> str:
        """Return safe, normalized text for the relevant application boundary."""


class QuerySanitizer(TextSanitizer):
    """Normalize user queries and cap their length before downstream use."""

    def sanitize(self, text: str) -> str:
        normalized = unicodedata.normalize("NFC", text).strip()
        normalized = re.sub(r"\s+", " ", normalized)
        return normalized[:MAX_QUERY_CHARS]


class FilenameSanitizer(TextSanitizer):
    """Remove path components and control characters from uploaded names."""

    def sanitize(self, text: str) -> str:
        normalized = unicodedata.normalize("NFC", text)
        normalized = re.sub(r"[/\\]", "_", normalized)
        normalized = re.sub(r"[\x00-\x1f\x7f]", "", normalized)
        normalized = normalized.strip(". ")
        return normalized[:MAX_FILENAME_CHARS] or "upload"


class OutputSanitizer(TextSanitizer):
    """Remove executable markup and leaked instruction blocks from output."""

    def __init__(self, patterns: Iterable[re.Pattern[str]]) -> None:
        self._patterns = tuple(patterns)

    def sanitize(self, text: str) -> str:
        for pattern in self._patterns:
            text = pattern.sub("", text)
        return text.strip()


INJECTION_RULES = (
    PatternRule(
        "role_override",
        re.compile(r"\bignore\s+(all\s+)?(previous|prior|above)\s+instructions?\b", re.I),
        "instruction override detected",
    ),
    PatternRule(
        "system_override",
        re.compile(r"\bnew\s+(system\s+)?prompt\b", re.I),
        "system prompt override detected",
    ),
    PatternRule(
        "delimiter_injection",
        re.compile(r"<\s*/?\s*(system|user|assistant|instruction)\s*>", re.I),
        "instruction delimiter detected",
    ),
    PatternRule(
        "bracket_injection",
        re.compile(r"\[\s*(system|inst|instruction)\s*\]", re.I),
        "instruction delimiter detected",
    ),
    PatternRule(
        "prompt_leak",
        re.compile(
            r"\b(repeat|print|output|reveal|show|tell me)\s+"
            r"(your\s+)?(system\s+)?(prompt|instructions?|context)\b",
            re.I,
        ),
        "system prompt disclosure request detected",
    ),
    PatternRule(
        "credential_disclosure",
        re.compile(
            r"\b(show|reveal|print|list|give|tell me|output|dump)\s+"
            r"(?:me\s+)?(?:all\s+)?(?:of\s+)?(?:your\s+|the\s+)?"
            r"(?:passwords?|credentials?|secrets?|api\s+keys?|access\s+tokens?)\b",
            re.I,
        ),
        "credential or secret disclosure request detected",
    ),
    PatternRule(
        "system_hacking_request",
        re.compile(
            r"\b(?:hack|break\s+into|compromise|exploit)\b.{0,80}"
            r"\b(?:the\s+)?(?:system|server|network|account|database|computer|website)\b"
            r"|\b(?:the\s+)?(?:system|server|network|account|database|computer|website)"
            r"\b.{0,80}\b(?:hack|break\s+into|compromise|exploit)\b",
            re.I,
        ),
        "system hacking request detected",
    ),
    PatternRule(
        "token_smuggling",
        re.compile(r"\\u00[0-9a-f]{2}|\\x[0-9a-f]{2}", re.I),
        "encoded control sequence detected",
    ),
)


def _create_detect_jailbreak_validator() -> Validator:
    """Load the local DetectJailbreak model only when pattern checks pass."""
    from guardrails_ai.detect_jailbreak import DetectJailbreak  # type: ignore[import-untyped]

    from rag_platform.core.jailbreak_models import DETECT_JAILBREAK_MODEL_DIR

    if not (DETECT_JAILBREAK_MODEL_DIR / "config.json").is_file():
        raise RuntimeError(
            "DetectJailbreak models are missing. Run `make jailbreak-models` "
            "or build the updated Docker image."
        )

    # The downloaded classifier config is normalized for Transformers 5.
    config = json.loads((DETECT_JAILBREAK_MODEL_DIR / "config.json").read_text(encoding="utf-8"))
    id2label = config.get("id2label", {})
    DetectJailbreak.TEXT_CLASSIFIER_NAME = str(DETECT_JAILBREAK_MODEL_DIR)
    DetectJailbreak.TEXT_CLASSIFIER_PASS_LABEL = str(id2label.get("0", "0"))
    DetectJailbreak.TEXT_CLASSIFIER_FAIL_LABEL = str(id2label.get("1", "1"))
    return DetectJailbreak(threshold=0.81, device="cpu")


PROMPT_INJECTION_PIPELINE = GuardrailPipeline(
    (
        *(
            GuardrailCheck(rule.name, PatternBlocklistValidator((rule,)))
            for rule in INJECTION_RULES
        ),
        GuardrailCheck("jailbreak", validator_factory=_create_detect_jailbreak_validator),
    )
)

OUTPUT_STRIPPER = OutputSanitizer(
    (
        re.compile(r"<script[\s\S]*?</script>", re.I),
        re.compile(r"<iframe[\s\S]*?</iframe>", re.I),
        re.compile(r"```\s*(system|instruction)[\s\S]*?```", re.I),
    )
)

QUERY_SANITIZER = QuerySanitizer()
FILENAME_SANITIZER = FilenameSanitizer()


def sanitize_query(text: str) -> str:
    """Compatibility API for query normalization."""
    return QUERY_SANITIZER.sanitize(text)


def sanitize_filename(name: str) -> str:
    """Compatibility API for uploaded filename normalization."""
    return FILENAME_SANITIZER.sanitize(name)


def sanitize_output(text: str) -> str:
    """Compatibility API for output cleanup."""
    return OUTPUT_STRIPPER.sanitize(text)


def check_prompt_injection(text: str, *, path: str = "unknown", user_id: str = "anonymous") -> None:
    """Reject known prompt-injection patterns through Guardrails AI."""
    PROMPT_INJECTION_PIPELINE.validate(text, path=path, user_id=user_id)
