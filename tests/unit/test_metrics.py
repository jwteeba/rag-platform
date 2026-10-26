"""Registration and increment behavior for application Prometheus metrics."""

from __future__ import annotations

from rag_platform.core.metrics import CACHE_HITS, DOCUMENTS_UPLOADED, RETRIEVAL_LATENCY


def _value(metric: object, sample_suffix: str, labels: dict[str, str]) -> float:
    for family in metric.collect():  # type: ignore[union-attr]
        for sample in family.samples:
            if sample.name.endswith(sample_suffix) and sample.labels == labels:
                return float(sample.value)
    return 0.0


def test_counters_register_labels_and_increment() -> None:
    document_labels = {"content_type": "text/plain"}
    cache_labels = {"cache_layer": "retrieval"}
    documents_before = _value(DOCUMENTS_UPLOADED, "_total", document_labels)
    cache_before = _value(CACHE_HITS, "_total", cache_labels)

    DOCUMENTS_UPLOADED.labels(**document_labels).inc()
    CACHE_HITS.labels(**cache_labels).inc()

    assert _value(DOCUMENTS_UPLOADED, "_total", document_labels) == documents_before + 1
    assert _value(CACHE_HITS, "_total", cache_labels) == cache_before + 1


def test_histogram_registers_observation() -> None:
    before = _value(RETRIEVAL_LATENCY, "_count", {})
    RETRIEVAL_LATENCY.observe(0.025)
    assert _value(RETRIEVAL_LATENCY, "_count", {}) == before + 1
