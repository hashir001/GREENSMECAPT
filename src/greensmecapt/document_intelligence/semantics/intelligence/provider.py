"""Provider-neutral and OpenAI-compatible semantic extraction."""

import json
import os
from collections.abc import Mapping
from typing import Any, Literal, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from greensmecapt.document_intelligence.semantics.intelligence.models import (
    SemanticExtractionRequest,
    SemanticProviderOutput,
)


class SemanticProviderError(RuntimeError):
    """Raised when an intelligent provider cannot return valid output."""


class SemanticExtractionProvider(Protocol):
    """Extract structured claims from approved source segments."""

    @property
    def provider_name(self) -> str:
        """Return the provider implementation name."""
        ...

    @property
    def provider_version(self) -> str:
        """Return the provider implementation version."""
        ...

    @property
    def model_name(self) -> str:
        """Return the configured model name."""
        ...

    def extract(
        self,
        request: SemanticExtractionRequest,
    ) -> SemanticProviderOutput:
        """Return schema-constrained semantic claims."""
        ...


class JsonTransport(Protocol):
    """Send and receive JSON without coupling tests to HTTP."""

    def post_json(
        self,
        *,
        url: str,
        headers: Mapping[str, str],
        payload: Mapping[str, Any],
        timeout_seconds: float,
    ) -> Mapping[str, Any]:
        """POST JSON and return a decoded JSON object."""
        ...


class OpenAICompatibleProviderConfiguration(BaseModel):
    """Configure a local or explicitly approved hosted model."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        allow_inf_nan=False,
    )

    endpoint: str = Field(min_length=1)
    model: str = Field(min_length=1)
    api_key_environment_variable: str | None = Field(
        default=None,
        min_length=1,
    )

    allow_remote: bool = False
    timeout_seconds: float = Field(
        default=120.0,
        gt=0,
        le=600,
    )
    maximum_output_tokens: int = Field(
        default=4096,
        ge=256,
        le=32768,
    )
    token_parameter: Literal[
        "max_tokens",
        "max_completion_tokens",
    ] = "max_tokens"

    @model_validator(mode="after")
    def validate_endpoint(self):
        """Require explicit approval before sending data remotely."""

        parsed = urlsplit(self.endpoint)

        if parsed.scheme not in {"http", "https"}:
            raise ValueError(
                "Provider endpoint must use HTTP or HTTPS."
            )

        if not parsed.hostname:
            raise ValueError(
                "Provider endpoint must include a hostname."
            )

        local_hosts = {
            "localhost",
            "127.0.0.1",
            "::1",
        }

        if (
            not self.allow_remote
            and parsed.hostname not in local_hosts
        ):
            raise ValueError(
                "Remote semantic providers require "
                "allow_remote=True."
            )

        return self


class UrllibJsonTransport:
    """Perform JSON requests using the Python standard library."""

    def post_json(
        self,
        *,
        url: str,
        headers: Mapping[str, str],
        payload: Mapping[str, Any],
        timeout_seconds: float,
    ) -> Mapping[str, Any]:
        """POST JSON and validate the response container."""

        request = Request(
            url=url,
            data=json.dumps(payload).encode(),
            headers=dict(headers),
            method="POST",
        )

        try:
            with urlopen(
                request,
                timeout=timeout_seconds,
            ) as response:
                response_body = response.read().decode(
                    "utf-8"
                )
        except (HTTPError, URLError, TimeoutError) as error:
            raise SemanticProviderError(
                "The semantic provider request failed."
            ) from error

        try:
            decoded = json.loads(response_body)
        except json.JSONDecodeError as error:
            raise SemanticProviderError(
                "The semantic provider returned invalid JSON."
            ) from error

        if not isinstance(decoded, Mapping):
            raise SemanticProviderError(
                "The semantic provider response must be an object."
            )

        return decoded


class OpenAICompatibleSemanticProvider:
    """Use schema-constrained chat completion endpoints."""

    provider_name = "openai_compatible"
    provider_version = "1.1.0"

    def __init__(
        self,
        configuration: OpenAICompatibleProviderConfiguration,
        *,
        transport: JsonTransport | None = None,
    ) -> None:
        self._configuration = configuration
        self._transport = transport or UrllibJsonTransport()

    @property
    def model_name(self) -> str:
        """Return the configured provider model."""

        return self._configuration.model

    def extract(
        self,
        request: SemanticExtractionRequest,
    ) -> SemanticProviderOutput:
        """Request strictly structured, source-grounded claims."""

        headers = {
            "Content-Type": "application/json",
        }

        environment_variable = (
            self._configuration
            .api_key_environment_variable
        )

        if environment_variable is not None:
            api_key = os.environ.get(environment_variable)

            if not api_key:
                raise SemanticProviderError(
                    "The configured API-key environment "
                    f"variable {environment_variable!r} is missing."
                )

            headers["Authorization"] = f"Bearer {api_key}"

        output_schema = strict_provider_schema(
            SemanticProviderOutput.model_json_schema()
        )

        payload = {
            "model": self._configuration.model,
            "temperature": 0,
            self._configuration.token_parameter: (
                self._configuration.maximum_output_tokens
            ),
            "messages": [
                {
                    "role": "system",
                    "content": _SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": request.model_dump_json(
                        indent=2
                    ),
                },
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": (
                        "greensmecapt_semantic_claims"
                    ),
                    "strict": True,
                    "schema": output_schema,
                },
            },
        }

        response = self._transport.post_json(
            url=self._configuration.endpoint,
            headers=headers,
            payload=payload,
            timeout_seconds=(
                self._configuration.timeout_seconds
            ),
        )

        content = _completion_content(response)

        try:
            return SemanticProviderOutput.model_validate_json(
                content
            )
        except ValueError as error:
            raise SemanticProviderError(
                "The provider output did not satisfy the "
                "semantic extraction schema."
            ) from error


_SYSTEM_PROMPT = """
You extract environmental, financial, investment and governed context claims
from supplied document segments.

Rules:
1. Use only the supplied segments, allowed metrics and qualitative_claims.
2. Never infer or estimate a value.
3. Copy source_quote exactly from one segment.
4. Copy raw_value exactly as written.
5. raw_number is the number explicitly represented by raw_value.
6. raw_unit is the unit explicitly written in the same source quote,
   including a nearby table header or scale label that clearly governs
   the number.
7. Use the exact segment_id and indicator_id supplied.
8. Return no claim when the metric, value, or unit is uncertain.
9. Do not convert units. The application performs conversion.
10. Copy reporting_period only when the quote explicitly states it.
11. Copy scope only when the quote explicitly states it, such as Scope 1.
12. Use null for reporting_period or scope when it is not explicit.
13. For a qualitative claim, copy source_quote exactly from one segment and
use only a supplied claim_id.
14. Set boolean_value only for a qualitative instruction whose value_type is
boolean. Use true or false only when the quote states the fact clearly.
15. For source_text qualitative claims, boolean_value must be null. Do not
summarize or rewrite the source; the application preserves the exact quote.
16. A plan, target or intention is not an achieved result. A missing statement
is not false. Return no claim when wording is ambiguous.
17. In table segments, header rows and the data row are separated by ||.
When columns represent different periods, return a separate claim for each
period/value and copy enough of the exact segment into source_quote to preserve
the governing period and unit.
18. Never classify a forecast, reduction, saving, avoided amount, target or
proposed operating effect as an actual consumption or emissions total. Use a
separate allowed forecast or savings indicator when one is supplied.
19. Currency scale words such as thousand or million belong to raw_unit and
raw_value; never silently multiply raw_number.
20. Never turn a qualitative statement into a numeric metric or score.
21. document_profile_claims, company_profile_claims and
sector_activity_proposals are proposals, not final company master data. Use
only supplied controlled IDs and an exact supporting quote.
22. A company-profile raw_value must occur exactly within source_quote. Do not
infer employee counts, dates, locations, licences, products or company names.
23. Sector and activity proposals may interpret an exact quote, but must use
only supplied sector and activity IDs. Return no proposal when the evidence is
too general to support it.
24. unmapped_material_claims are a review-only safety net. Use them only for
material information that fits no allowed metric or governed qualitative
claim. Never restate an already captured claim, and never exceed
maximum_unmapped_claims.
25. model_rationale may explain why an unmapped quote may matter, but must not
present the information as verified, scoreable or approved.
26. Return only the required JSON structure.
""".strip()


def strict_provider_schema(schema: Mapping[str, Any]) -> dict[str, Any]:
    """Adapt a Pydantic schema to strict structured-output requirements."""

    result = json.loads(json.dumps(schema))

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            value.pop("default", None)
            properties = value.get("properties")

            if value.get("type") == "object" and isinstance(properties, dict):
                value["required"] = list(properties)
                value["additionalProperties"] = False

            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(result)
    return result


def _completion_content(
    response: Mapping[str, Any],
) -> str:
    """Recover text content from a chat-completion response."""

    choices = response.get("choices")

    if (
        not isinstance(choices, list)
        or not choices
        or not isinstance(choices[0], Mapping)
    ):
        raise SemanticProviderError(
            "The provider response contains no completion."
        )

    message = choices[0].get("message")

    if not isinstance(message, Mapping):
        raise SemanticProviderError(
            "The provider completion contains no message."
        )

    content = message.get("content")

    if isinstance(content, str) and content.strip():
        return content

    raise SemanticProviderError(
        "The provider completion contains no text content."
    )
