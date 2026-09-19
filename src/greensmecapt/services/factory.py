"""Build the production document-processing graph."""

import os
from collections.abc import Mapping
from pathlib import Path

from greensmecapt.document_intelligence.readers import (
    ProductionReaderConfiguration,
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
from greensmecapt.document_intelligence.structure.paddle import (
    PaddleParserConfiguration,
    PaddleResourceProfile,
)
from greensmecapt.document_intelligence.understanding import (
    HybridSemanticConfiguration,
    HybridSemanticExtractor,
)
from greensmecapt.document_intelligence.vision import (
    OpenAICompatibleVisualProvider,
    VisualUnderstandingService,
)
from greensmecapt.services.document_processing import (
    StoredDocumentProcessingService,
)
from greensmecapt.storage import DocumentStorage


class DocumentProcessingConfigurationError(
    ValueError
):
    """Raised when processing settings are incomplete."""


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
            (
                "config/"
                "metric_catalog.development.json"
            ),
        )
    )
    catalog = load_metric_catalog(
        catalog_path
    )
    intelligent_service = (
        _intelligent_service_from_environment(
            configured_environment
        )
    )
    reader_configuration = (
        production_reader_configuration_from_environment(
            configured_environment
        )
    )

    return StoredDocumentProcessingService(
        storage=storage,
        reader=build_production_document_reader(
            reader_configuration
        ),
        semantic_extractor=HybridSemanticExtractor(
            deterministic_extractor=(
                SemanticMetricExtractor(catalog)
            ),
            catalog=catalog,
            intelligent_service=(
                intelligent_service
            ),
            configuration=(
                HybridSemanticConfiguration(
                    require_intelligent_success=(
                        _environment_boolean(
                            configured_environment,
                            (
                                "GREENSMECAPT_"
                                "SEMANTIC_REQUIRED"
                            ),
                            default=False,
                        )
                    )
                )
            ),
        ),
        visual_service=VisualUnderstandingService(
            catalog=catalog,
            provider=_visual_provider_from_environment(
                configured_environment
            ),
        ),
    )


def production_reader_configuration_from_environment(
    environment: Mapping[str, str] | None = None,
) -> ProductionReaderConfiguration:
    """Build resource-aware OCR deployment settings."""

    configured = (
        environment
        if environment is not None
        else os.environ
    )
    raw_profile = configured.get(
        "GREENSMECAPT_PADDLE_PROFILE",
        PaddleResourceProfile.LOCAL_CPU.value,
    )

    try:
        profile = PaddleResourceProfile(
            raw_profile.strip().casefold()
        )
    except ValueError as error:
        allowed = ", ".join(
            item.value
            for item in PaddleResourceProfile
        )

        raise DocumentProcessingConfigurationError(
            "GREENSMECAPT_PADDLE_PROFILE must be "
            f"one of: {allowed}."
        ) from error

    cpu_threads = _environment_integer(
        configured,
        "GREENSMECAPT_PADDLE_CPU_THREADS",
        default=(
            2
            if (
                profile
                is PaddleResourceProfile.LOCAL_CPU
            )
            else 4
        ),
        minimum=1,
        maximum=64,
    )
    paddle = (
        PaddleParserConfiguration.for_profile(
            profile,
            device=configured.get(
                "GREENSMECAPT_PADDLE_DEVICE",
                "cpu",
            ),
            cpu_threads=cpu_threads,
        )
    )

    return ProductionReaderConfiguration(
        paddle=paddle,
        pdf_render_dpi=_environment_integer(
            configured,
            "GREENSMECAPT_PDF_RENDER_DPI",
            default=200,
            minimum=72,
            maximum=600,
        ),
        enable_tesseract_fallback=(
            _environment_boolean(
                configured,
                (
                    "GREENSMECAPT_"
                    "TESSERACT_FALLBACK"
                ),
                default=True,
            )
        ),
        tesseract_language=configured.get(
            "GREENSMECAPT_TESSERACT_LANGUAGE",
            "eng",
        ),
        tesseract_page_segmentation_mode=(
            _environment_integer(
                configured,
                "GREENSMECAPT_TESSERACT_PSM",
                default=6,
                minimum=0,
                maximum=None,
            )
        ),
        tesseract_timeout_seconds=(
            _environment_float(
                configured,
                (
                    "GREENSMECAPT_"
                    "TESSERACT_TIMEOUT_SECONDS"
                ),
                default=30.0,
                minimum_exclusive=0.0,
            )
        ),
    )


def _intelligent_service_from_environment(
    environment: Mapping[str, str],
) -> IntelligentSemanticExtractionService | None:
    endpoint = environment.get(
        "GREENSMECAPT_SEMANTIC_ENDPOINT"
    )
    model = environment.get(
        "GREENSMECAPT_SEMANTIC_MODEL"
    )

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
            api_key_environment_variable=(
                environment.get(
                    
                        "GREENSMECAPT_"
                        "SEMANTIC_API_KEY_ENV"
                    
                )
            ),
            allow_remote=_environment_boolean(
                environment,
                (
                    "GREENSMECAPT_"
                    "SEMANTIC_ALLOW_REMOTE"
                ),
                default=False,
            ),
        )
    )

    return IntelligentSemanticExtractionService(
        provider
    )


def _visual_provider_from_environment(
    environment: Mapping[str, str],
) -> OpenAICompatibleVisualProvider | None:
    endpoint = environment.get(
        "GREENSMECAPT_VISUAL_ENDPOINT"
    )
    model = environment.get(
        "GREENSMECAPT_VISUAL_MODEL"
    )

    if endpoint is None and model is None:
        return None

    if not endpoint or not model:
        raise DocumentProcessingConfigurationError(
            "Visual interpretation requires both "
            "GREENSMECAPT_VISUAL_ENDPOINT and "
            "GREENSMECAPT_VISUAL_MODEL."
        )

    return OpenAICompatibleVisualProvider(
        OpenAICompatibleProviderConfiguration(
            endpoint=endpoint,
            model=model,
            api_key_environment_variable=(
                environment.get(
                    "GREENSMECAPT_VISUAL_API_KEY_ENV"
                )
            ),
            allow_remote=_environment_boolean(
                environment,
                "GREENSMECAPT_VISUAL_ALLOW_REMOTE",
                default=False,
            ),
        )
    )


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

    if normalized in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return True

    if normalized in {
        "0",
        "false",
        "no",
        "off",
    }:
        return False

    raise DocumentProcessingConfigurationError(
        f"Environment variable {name} must be "
        "a boolean value."
    )


def _environment_integer(
    environment: Mapping[str, str],
    name: str,
    *,
    default: int,
    minimum: int,
    maximum: int | None,
) -> int:
    raw_value = environment.get(name)

    if raw_value is None:
        return default

    try:
        value = int(raw_value)
    except ValueError as error:
        raise DocumentProcessingConfigurationError(
            f"Environment variable {name} must "
            "be an integer."
        ) from error

    if value < minimum or (
        maximum is not None
        and value > maximum
    ):
        upper = (
            f" and at most {maximum}"
            if maximum is not None
            else ""
        )

        raise DocumentProcessingConfigurationError(
            f"Environment variable {name} must be "
            f"at least {minimum}{upper}."
        )

    return value


def _environment_float(
    environment: Mapping[str, str],
    name: str,
    *,
    default: float,
    minimum_exclusive: float,
) -> float:
    raw_value = environment.get(name)

    if raw_value is None:
        return default

    try:
        value = float(raw_value)
    except ValueError as error:
        raise DocumentProcessingConfigurationError(
            f"Environment variable {name} must "
            "be numeric."
        ) from error

    if value <= minimum_exclusive:
        raise DocumentProcessingConfigurationError(
            f"Environment variable {name} must be "
            f"greater than {minimum_exclusive}."
        )

    return value
