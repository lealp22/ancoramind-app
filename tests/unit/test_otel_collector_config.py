"""Regression tests for the private, content-redacting T10 Collector config."""

from __future__ import annotations

from pathlib import Path


def test_collector_config_has_private_otlp_receiver_and_redaction_pipeline() -> None:
    config_path = Path("observability/otel-collector.yaml")
    content = config_path.read_text(encoding="utf-8")

    assert "endpoint: 0.0.0.0:4317" in content
    for key in (
        "gen_ai.prompt",
        "gen_ai.completion",
        "message.content",
        "ancora.tool.arguments",
        "ancora.tool.result",
        "document.content",
    ):
        assert f"key: {key}" in content
    assert "limit_mib: 256" in content
    assert "queue_size: 1000" in content
