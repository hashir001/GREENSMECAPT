"""Tests for Vertex Gemini semantic extraction."""

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from greensmecapt.document_intelligence.semantics.intelligence import (
    MetricInstruction,
    SemanticExtractionRequest,
    SemanticProviderError,
    SemanticSourceSegment,
    VertexGeminiProviderConfiguration,
    VertexGeminiSemanticProvider,
)


class _ProviderStatusError(Exception):
    def __init__(self, code: int) -> None:
        super().__init__(f"provider status {code}")
        self.code = code


class _Models:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.calls: list[dict[str, object]] = []
        self.error = error

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return SimpleNamespace(
            parsed={
                "claims": [
                    {
                        "segment_id": "segment-1",
                        "indicator_id": "electricity_consumption_kwh",
                        "raw_value": "1,250 kWh",
                        "raw_number": 1250,
                        "raw_unit": "kWh",
                        "source_quote": "Purchased electricity was 1,250 kWh in 2025.",
                        "reporting_period": "2025",
                        "scope": None,
                    }
                ],
                "qualitative_claims": [],
            }
        )


def _request() -> SemanticExtractionRequest:
    return SemanticExtractionRequest(
        document_id="document-1",
        catalog_id="catalog",
        catalog_version="1",
        metrics=(
            MetricInstruction(
                indicator_id="electricity_consumption_kwh",
                name="Electricity consumption",
                aliases=("purchased electricity",),
                canonical_unit="kwh",
                accepted_unit_aliases=("kwh",),
            ),
        ),
        segments=(
            SemanticSourceSegment(
                segment_id="segment-1",
                page_number=1,
                locator="page 1",
                text="Purchased electricity was 1,250 kWh in 2025.",
            ),
        ),
    )


def test_vertex_provider_returns_validated_structured_output() -> None:
    models = _Models()
    provider = VertexGeminiSemanticProvider(
        VertexGeminiProviderConfiguration(
            project_id="project",
            model="gemini-2.5-flash",
            allow_remote=True,
        ),
        client=SimpleNamespace(models=models),
    )

    output = provider.extract(_request())

    assert output.claims[0].raw_number == 1250
    assert models.calls[0]["model"] == "gemini-2.5-flash"
    config = models.calls[0]["config"]
    assert config["thinking_config"] == {"thinking_budget": 0}
    assert config["response_mime_type"] == "application/json"
    assert isinstance(config["response_schema"], dict)
    assert "additionalProperties" not in str(config["response_schema"])


def test_vertex_provider_translates_access_denial() -> None:
    models = _Models(error=_ProviderStatusError(403))
    provider = VertexGeminiSemanticProvider(
        VertexGeminiProviderConfiguration(
            project_id="project",
            allow_remote=True,
        ),
        client=SimpleNamespace(models=models),
    )

    with pytest.raises(SemanticProviderError, match=r"roles/aiplatform\.user"):
        provider.extract(_request())


def test_vertex_configuration_requires_remote_approval() -> None:
    with pytest.raises(ValidationError, match="allow_remote=True"):
        VertexGeminiProviderConfiguration(
            project_id="project",
            model="gemini-2.5-flash",
        )
