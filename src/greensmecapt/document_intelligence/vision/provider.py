"""OpenAI-compatible local or hosted multimodal provider."""

import base64
import json
import os
from collections.abc import Mapping
from typing import Any

from greensmecapt.document_intelligence.semantics.intelligence.provider import (
    JsonTransport,
    OpenAICompatibleProviderConfiguration,
    SemanticProviderError,
    UrllibJsonTransport,
    strict_provider_schema,
)
from greensmecapt.document_intelligence.vision.models import (
    VisualInterpretationRequest,
    VisualProviderOutput,
)
from greensmecapt.document_intelligence.vision.ports import (
    VisualProviderError,
)


class OpenAICompatibleVisualProvider:
    """Interpret one exact visual crop through a multimodal endpoint."""

    provider_name = "openai_compatible_visual"
    provider_version = "1.0.0"

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
        return self._configuration.model

    def interpret(
        self,
        request: VisualInterpretationRequest,
    ) -> VisualProviderOutput:
        """Request schema-constrained claims from a page-region crop."""

        headers = {"Content-Type": "application/json"}
        key_name = self._configuration.api_key_environment_variable

        if key_name is not None:
            api_key = os.environ.get(key_name)

            if not api_key:
                raise VisualProviderError(
                    f"Configured API-key variable {key_name!r} is missing."
                )

            headers["Authorization"] = f"Bearer {api_key}"

        image_url = (
            "data:image/png;base64,"
            + base64.b64encode(request.image_png).decode("ascii")
        )
        payload = {
            "model": self._configuration.model,
            "temperature": 0,
            self._configuration.token_parameter: (
                self._configuration.maximum_output_tokens
            ),
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": _request_text(request),
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": image_url},
                        },
                    ],
                },
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "greensmecapt_visual_claims",
                    "strict": True,
                    "schema": strict_provider_schema(
                        VisualProviderOutput.model_json_schema()
                    ),
                },
            },
        }

        try:
            response = self._transport.post_json(
                url=self._configuration.endpoint,
                headers=headers,
                payload=payload,
                timeout_seconds=self._configuration.timeout_seconds,
            )
            content = _completion_content(response)
            return VisualProviderOutput.model_validate_json(content)
        except (SemanticProviderError, ValueError) as error:
            raise VisualProviderError(
                "The visual provider returned invalid structured output."
            ) from error


_SYSTEM_PROMPT = """
You inspect one cropped chart, diagram, or assessment-relevant image.

Rules:
1. Use only values visibly present in the supplied crop.
2. Use only the allowed indicator IDs and units.
3. Never estimate values from bar height, area, color, or visual impression.
4. Copy raw_value exactly as it appears in the image.
5. raw_number must be the number explicitly written in raw_value.
6. Explain where the value appears in source_description.
7. Return no claim when the number, label, or unit is uncertain.
8. Do not convert units; the application validates and converts them.
9. A photograph without an explicit metric normally produces no claim.
10. Return only the required JSON structure.
""".strip()


def _request_text(request: VisualInterpretationRequest) -> str:
    metrics = [
        {
            "indicator_id": metric.indicator_id,
            "name": metric.name,
            "aliases": metric.aliases,
            "canonical_unit": metric.canonical_unit,
            "accepted_units": tuple(
                alias
                for unit in metric.units
                for alias in unit.aliases
            ),
            "minimum": metric.minimum,
            "maximum": metric.maximum,
        }
        for metric in request.catalog.metrics
    ]
    return json.dumps(
        {
            "document_id": request.document_id,
            "page_number": request.page_number,
            "region_id": request.region.region_id,
            "region_kind": request.region.kind.value,
            "caption": request.region.caption,
            "page_context": request.page_context,
            "allowed_metrics": metrics,
        },
        indent=2,
    )


def _completion_content(response: Mapping[str, Any]) -> str:
    choices = response.get("choices")

    if (
        not isinstance(choices, list)
        or not choices
        or not isinstance(choices[0], Mapping)
    ):
        raise VisualProviderError(
            "The visual provider response contains no completion."
        )

    message = choices[0].get("message")
    content = (
        message.get("content")
        if isinstance(message, Mapping)
        else None
    )

    if not isinstance(content, str) or not content.strip():
        raise VisualProviderError(
            "The visual provider completion contains no JSON text."
        )

    return content
