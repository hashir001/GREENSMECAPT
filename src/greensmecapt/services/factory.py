"""Build the production document-processing graph."""

import os
from collections.abc import Mapping
from pathlib import Path

from greensmecapt.document_intelligence.readers import (
    build_production_document_reader,
)
from greensmecapt.document_intelligence.semantics import (
    SemanticMetricExtractor,
    load_metric_catalog,
)
from greensmecapt.document_intelligence.semantics.intelligence import (
    IntelligentSemanticExtractionService,
    OpenAICompatibleProviderConfiguration,
    OpenAICompatibleSemanticProvider,
)
from greensmecapt.document_intelligence.understanding import (
    HybridSemanticConfiguration,
    HybridSemanticExtractor,
)
from greensmecapt.services.document_processing import (
    StoredDocumentProcessingService,
)
from greensmecapt.storage import DocumentStorage


class DocumentProcessingConfigurationError(ValueError):
    """Raised when processing environment settings are incomplete."""


def build_document_processing_service(
    storage: DocumentStorage,
    *,
    environment: Mapping[str, str] | None = None,
) -> StoredDocumentProcessingService:
    """Build OCR, deterministic NLP and optional LLM extraction."""

    configured_environment = (
        environment
        if environment is not None
        else os.environ
    )
    catalog_path = Path(
        configured_environment.get(
            "GREENSMECAPT_METRIC_CATALOG",
            "config/metric_catalog.development.json",
        )
    )
    catalog = load_metric_catalog(catalog_path)
    intelligent_service = _intelligent_service_from_environment(
        configured_environment
    )

    return StoredDocumentProcessingService(
        storage=storage,
        reader=build_production_document_reader(),
        semantic_extractor=HybridSemanticExtractor(
            deterministic_extractor=SemanticMetricExtractor(catalog),
            catalog=catalog,
            intelligent_service=intelligent_service,
            configuration=HybridSemanticConfiguration(
                require_intelligent_success=_environment_boolean(
                    configured_environment,
                    "GREENSMECAPT_SEMANTIC_REQUIRED",
                    default=False,
                )
            ),
        ),
    )


def _intelligent_service_from_environment(
    environment: Mapping[str, str],
) -> IntelligentSemanticExtractionService | None:
    endpoint = environment.get("GREENSMECAPT_SEMANTIC_ENDPOINT")
    model = environment.get("GREENSMECAPT_SEMANTIC_MODEL")

    if endpoint is None and model is None:
        return None

    if not endpoint or not model:
        raise DocumentProcessingConfigurationError(
            "Intelligent extraction requires both "
            "GREENSMECAPT_SEMANTIC_ENDPOINT and "
            "GREENSMECAPT_SEMANTIC_MODEL."
        )

    provider = OpenAICompatibleSemanticProvider(
        OpenAICompatibleProviderConfiguration(
            endpoint=endpoint,
            model=model,
            api_key_environment_variable=environment.get(
                "GREENSMECAPT_SEMANTIC_API_KEY_ENV"
            ),
            allow_remote=_environment_boolean(
                environment,
                "GREENSMECAPT_SEMANTIC_ALLOW_REMOTE",
                default=False,
            ),
        )
    )

    return IntelligentSemanticExtractionService(provider)


def _environment_boolean(
    environment: Mapping[str, str],
    name: str,
    *,
    default: bool,
) -> bool:
    raw_value = environment.get(name)

    if raw_value is None:
        return default

    normalized = raw_value.strip().casefold()

    if normalized in {"1", "true", "yes", "on"}:
        return True

    if normalized in {"0", "false", "no", "off"}:
        return False

    raise DocumentProcessingConfigurationError(
        f"Environment variable {name} must be a boolean value."
    )
