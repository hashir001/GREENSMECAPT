"""Vertex Gemini-backed grounded semantic extraction."""

from __future__ import annotations

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
    provider_version = "1.0.0"

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
                    "response_mime_type": "application/json",
                    "response_schema": SemanticProviderOutput,
                },
            )
        except SemanticProviderError:
            raise
        except Exception as error:
            raise SemanticProviderError(
                "Vertex Gemini semantic extraction failed."
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
                raise SemanticProviderError(
                    "Vertex Gemini credentials or client setup failed."
                ) from error

        return self._client
