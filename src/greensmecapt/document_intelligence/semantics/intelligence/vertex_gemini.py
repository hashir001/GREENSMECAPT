"""Vertex Gemini-backed grounded semantic extraction."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from threading import Lock

from pydantic import BaseModel, ConfigDict, Field, model_validator

from greensmecapt.document_intelligence.semantics.intelligence.models import (
    SemanticExtractionRequest,
    SemanticProviderOutput,
)
from greensmecapt.document_intelligence.semantics.intelligence.provider import (
    _SYSTEM_PROMPT,
    SemanticProviderError,
)

_LOGGER = logging.getLogger("uvicorn.error")

# Vertex structured output accepts a narrower schema vocabulary than Pydantic's
# full JSON Schema. Keep the provider contract explicit, then validate the
# returned payload again with the authoritative Pydantic models.
_VERTEX_OUTPUT_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "claims": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "segment_id": {"type": "STRING"},
                    "indicator_id": {"type": "STRING"},
                    "raw_value": {"type": "STRING"},
                    "raw_number": {"type": "NUMBER"},
                    "raw_unit": {"type": "STRING"},
                    "source_quote": {"type": "STRING"},
                    "reporting_period": {
                        "type": "STRING",
                        "nullable": True,
                    },
                    "scope": {
                        "type": "STRING",
                        "nullable": True,
                    },
                    "claim_nature": {
                        "type": "STRING",
                        "enum": ["actual", "estimate", "target", "projected", "unspecified"],
                    },
                    "entity_name": {"type": "STRING", "nullable": True},
                    "facility_or_site": {"type": "STRING", "nullable": True},
                    "project_name": {"type": "STRING", "nullable": True},
                },
                "required": [
                    "segment_id",
                    "indicator_id",
                    "raw_value",
                    "raw_number",
                    "raw_unit",
                    "source_quote",
                    "reporting_period",
                    "scope",
                    "claim_nature",
                    "entity_name",
                    "facility_or_site",
                    "project_name",
                ],
            },
        },
        "qualitative_claims": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "segment_id": {"type": "STRING"},
                    "claim_id": {"type": "STRING"},
                    "source_quote": {"type": "STRING"},
                    "boolean_value": {
                        "type": "BOOLEAN",
                        "nullable": True,
                    },
                    "reporting_period": {
                        "type": "STRING",
                        "nullable": True,
                    },
                    "scope": {
                        "type": "STRING",
                        "nullable": True,
                    },
                    "claim_nature": {
                        "type": "STRING",
                        "enum": ["actual", "estimate", "target", "projected", "unspecified"],
                    },
                    "entity_name": {"type": "STRING", "nullable": True},
                    "facility_or_site": {"type": "STRING", "nullable": True},
                    "project_name": {"type": "STRING", "nullable": True},
                },
                "required": [
                    "segment_id",
                    "claim_id",
                    "source_quote",
                    "boolean_value",
                    "reporting_period",
                    "scope",
                    "claim_nature",
                    "entity_name",
                    "facility_or_site",
                    "project_name",
                ],
            },
        },
        "document_profile_claims": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "segment_id": {"type": "STRING"},
                    "document_type_id": {"type": "STRING"},
                    "source_quote": {"type": "STRING"},
                    "issuer_name": {"type": "STRING", "nullable": True},
                    "reporting_period": {
                        "type": "STRING",
                        "nullable": True,
                    },
                    "assurance_status": {
                        "type": "STRING",
                        "nullable": True,
                    },
                },
                "required": [
                    "segment_id",
                    "document_type_id",
                    "source_quote",
                    "issuer_name",
                    "reporting_period",
                    "assurance_status",
                ],
            },
        },
        "company_profile_claims": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "segment_id": {"type": "STRING"},
                    "field_id": {"type": "STRING"},
                    "raw_value": {"type": "STRING"},
                    "source_quote": {"type": "STRING"},
                },
                "required": [
                    "segment_id",
                    "field_id",
                    "raw_value",
                    "source_quote",
                ],
            },
        },
        "sector_activity_proposals": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "segment_id": {"type": "STRING"},
                    "sector_id": {"type": "STRING"},
                    "activity_fact_ids": {
                        "type": "ARRAY",
                        "items": {"type": "STRING"},
                    },
                    "source_quote": {"type": "STRING"},
                },
                "required": [
                    "segment_id",
                    "sector_id",
                    "activity_fact_ids",
                    "source_quote",
                ],
            },
        },
        "readiness_claims": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "segment_id": {"type": "STRING"},
                    "factor_id": {"type": "STRING"},
                    "state": {
                        "type": "STRING",
                        "enum": [
                            "enabling_evidence",
                            "constraining_evidence",
                            "mixed_evidence",
                        ],
                    },
                    "source_quote": {"type": "STRING"},
                    "model_rationale": {"type": "STRING"},
                },
                "required": [
                    "segment_id",
                    "factor_id",
                    "state",
                    "source_quote",
                    "model_rationale",
                ],
            },
        },
        "unmapped_material_claims": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "segment_id": {"type": "STRING"},
                    "category_id": {"type": "STRING"},
                    "suggested_label": {"type": "STRING"},
                    "source_quote": {"type": "STRING"},
                    "model_rationale": {"type": "STRING"},
                },
                "required": [
                    "segment_id",
                    "category_id",
                    "suggested_label",
                    "source_quote",
                    "model_rationale",
                ],
            },
        },
    },
    "required": [
        "claims",
        "qualitative_claims",
        "document_profile_claims",
        "company_profile_claims",
        "sector_activity_proposals",
        "readiness_claims",
        "unmapped_material_claims",
    ],
}


class VertexGeminiProviderConfiguration(BaseModel):
    """Configure Gemini on Vertex AI using Application Default Credentials."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        allow_inf_nan=False,
    )

    project_id: str = Field(min_length=1)
    location: str = Field(default="global", min_length=1)
    model: str = Field(default="gemini-2.5-flash", min_length=1)
    allow_remote: bool = False
    timeout_seconds: float = Field(default=120.0, gt=0, le=600)
    maximum_output_tokens: int = Field(default=8192, ge=256, le=32768)

    @model_validator(mode="after")
    def require_remote_approval(self):
        """Prevent accidental transmission of SME evidence to a cloud model."""

        if not self.allow_remote:
            raise ValueError(
                "Vertex Gemini semantic extraction requires allow_remote=True."
            )
        return self


class VertexGeminiSemanticProvider:
    """Use Vertex Gemini structured output with the existing grounded contract."""

    provider_name = "vertex_gemini"
    provider_version = "1.3.0"

    def __init__(
        self,
        configuration: VertexGeminiProviderConfiguration,
        *,
        client: object | None = None,
    ) -> None:
        self._configuration = configuration
        self._client = client
        self._lock = Lock()

    @property
    def model_name(self) -> str:
        return self._configuration.model

    def extract(
        self,
        request: SemanticExtractionRequest,
    ) -> SemanticProviderOutput:
        """Return only claims satisfying the strict semantic output schema."""

        try:
            response = self._resolved_client().models.generate_content(
                model=self._configuration.model,
                contents=request.model_dump_json(indent=2),
                config={
                    "system_instruction": _SYSTEM_PROMPT,
                    "temperature": 0,
                    "max_output_tokens": (
                        self._configuration.maximum_output_tokens
                    ),
                    "thinking_config": {"thinking_budget": 0},
                    "response_mime_type": "application/json",
                    "response_schema": _VERTEX_OUTPUT_SCHEMA,
                },
            )
        except SemanticProviderError:
            raise
        except Exception as error:
            _LOGGER.exception(
                "Vertex Gemini request failed for project %s, location %s, model %s.",
                self._configuration.project_id,
                self._configuration.location,
                self._configuration.model,
            )
            raise SemanticProviderError(
                _provider_failure_message(error)
            ) from error

        parsed = getattr(response, "parsed", None)
        if isinstance(parsed, SemanticProviderOutput):
            return parsed
        if isinstance(parsed, Mapping):
            try:
                return SemanticProviderOutput.model_validate(parsed)
            except ValueError as error:
                raise SemanticProviderError(
                    "Vertex Gemini returned invalid structured output."
                ) from error

        response_text = getattr(response, "text", None)
        if not isinstance(response_text, str) or not response_text.strip():
            raise SemanticProviderError(
                "Vertex Gemini returned no semantic extraction output."
            )

        try:
            return SemanticProviderOutput.model_validate_json(response_text)
        except ValueError as error:
            raise SemanticProviderError(
                "Vertex Gemini output did not satisfy the semantic schema."
            ) from error

    def _resolved_client(self) -> object:
        client = self._client
        if client is not None:
            return client

        with self._lock:
            if self._client is not None:
                return self._client

            try:
                from google import genai
                from google.genai import types
            except ImportError as error:
                raise SemanticProviderError(
                    "Vertex Gemini support is not installed. Install the "
                    "'vertex-semantic' project extra."
                ) from error

            try:
                self._client = genai.Client(
                    vertexai=True,
                    project=self._configuration.project_id,
                    location=self._configuration.location,
                    http_options=types.HttpOptions(
                        api_version="v1",
                        timeout=int(
                            self._configuration.timeout_seconds * 1000
                        ),
                    ),
                )
            except Exception as error:
                _LOGGER.exception(
                    "Vertex Gemini client setup failed for project %s.",
                    self._configuration.project_id,
                )
                raise SemanticProviderError(
                    "Vertex Gemini credentials or client setup failed. "
                    "Verify GOOGLE_APPLICATION_CREDENTIALS."
                ) from error

        return self._client


def _provider_failure_message(error: Exception) -> str:
    """Translate provider status codes into safe, actionable diagnostics."""

    raw_code = getattr(error, "code", None)
    try:
        code = int(raw_code)
    except (TypeError, ValueError):
        code = None

    if code == 400:
        return (
            "Vertex Gemini rejected the extraction request (400). "
            "The backend log contains the rejected field."
        )
    if code == 401:
        return (
            "Vertex Gemini authentication failed (401). Verify "
            "GOOGLE_APPLICATION_CREDENTIALS."
        )
    if code == 403:
        return (
            "Vertex Gemini access was denied (403). Enable the Vertex AI API "
            "and grant Agent Platform User (roles/aiplatform.user) to the "
            "backend service account."
        )
    if code == 404:
        return (
            "Vertex Gemini model access failed (404). Verify the configured "
            "project, location and model."
        )
    if code == 429:
        return (
            "Vertex Gemini quota or rate limit was exceeded (429)."
        )
    if code in {500, 502, 503, 504}:
        return (
            f"Vertex Gemini was temporarily unavailable ({code})."
        )

    return (
        "Vertex Gemini semantic extraction failed "
        f"({type(error).__name__}). See the backend log."
    )
