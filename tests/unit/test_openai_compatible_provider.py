"""Tests for OpenAI-compatible semantic providers."""

import json

import pytest
from pydantic import ValidationError

from greensmecapt.document_intelligence.semantics.intelligence import (
    MetricInstruction,
    OpenAICompatibleProviderConfiguration,
    OpenAICompatibleSemanticProvider,
    SemanticExtractionRequest,
)


class FakeTransport:
    """Return a controlled chat-completion response."""

    def __init__(self) -> None:
        self.payload = None
        self.headers = None

    def post_json(
        self,
        *,
        url,
        headers,
        payload,
        timeout_seconds,
    ):
        self.payload = payload
        self.headers = headers

        output = {
            "claims": [
                {
                    "segment_id": "page_1_text",
                    "indicator_id": (
                        "renewable_energy_percentage"
                    ),
                    "raw_value": "72 percent",
                    "raw_number": 72.0,
                    "raw_unit": "percent",
                    "source_quote": (
                        "Renewable energy share was "
                        "72 percent."
                    ),
                }
            ]
        }

        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(output)
                    }
                }
            ]
        }


def _request() -> SemanticExtractionRequest:
    return SemanticExtractionRequest(
        document_id="doc_001",
        catalog_id="catalog_001",
        catalog_version="1.0",
        metrics=(
            MetricInstruction(
                indicator_id=(
                    "renewable_energy_percentage"
                ),
                name="Renewable energy share",
                aliases=("renewable energy share",),
                canonical_unit="percent",
                accepted_unit_aliases=(
                    "%",
                    "percent",
                ),
                minimum=0,
                maximum=100,
            ),
        ),
        segments=(
            {
                "segment_id": "page_1_text",
                "page_number": 1,
                "locator": "page 1",
                "text": (
                    "Renewable energy share was "
                    "72 percent."
                ),
            },
        ),
    )


def test_allow_local_provider_without_remote_approval() -> None:
    """A local model endpoint should be safe by default."""

    configuration = (
        OpenAICompatibleProviderConfiguration(
            endpoint=(
                "http://localhost:11434/"
                "v1/chat/completions"
            ),
            model="local-model",
        )
    )

    assert configuration.allow_remote is False


def test_reject_remote_provider_without_approval() -> None:
    """Remote document transmission must be explicit."""

    with pytest.raises(ValidationError):
        OpenAICompatibleProviderConfiguration(
            endpoint=(
                "https://provider.example/"
                "v1/chat/completions"
            ),
            model="remote-model",
        )


def test_allow_explicitly_approved_remote_provider() -> None:
    """Remote providers may be configured deliberately."""

    configuration = (
        OpenAICompatibleProviderConfiguration(
            endpoint=(
                "https://provider.example/"
                "v1/chat/completions"
            ),
            model="remote-model",
            allow_remote=True,
        )
    )

    assert configuration.allow_remote is True


def test_request_schema_constrained_output() -> None:
    """Provider requests should carry the output schema."""

    transport = FakeTransport()
    provider = OpenAICompatibleSemanticProvider(
        OpenAICompatibleProviderConfiguration(
            endpoint=(
                "http://localhost:11434/"
                "v1/chat/completions"
            ),
            model="local-model",
        ),
        transport=transport,
    )

    output = provider.extract(_request())

    assert len(output.claims) == 1
    assert output.claims[0].raw_number == 72.0

    assert (
        transport.payload["response_format"]["type"]
        == "json_schema"
    )
    assert (
        transport.payload["temperature"]
        == 0
    )
    assert "Authorization" not in transport.headers