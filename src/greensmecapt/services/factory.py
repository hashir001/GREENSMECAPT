"""Build the production document-processing graph."""

import os
from collections.abc import Mapping
from pathlib import Path

from greensmecapt.assessment.profiles import AssessmentPolicy, load_policy
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
    QualitativeInstruction,
    QualitativeValueType,
    VertexGeminiProviderConfiguration,
    VertexGeminiSemanticProvider,
)
from greensmecapt.document_intelligence.structure import (
    GoogleDocumentAIConfiguration,
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


class DocumentProcessingConfigurationError(ValueError):
    """Raised when processing settings are incomplete."""


def build_document_processing_service(
    storage: DocumentStorage,
    *,
    environment: Mapping[str, str] | None = None,
) -> StoredDocumentProcessingService:
    """Build OCR, deterministic NLP and optional LLM extraction."""

    configured_environment = environment if environment is not None else os.environ
    catalog_path = Path(
        configured_environment.get(
            "GREENSMECAPT_METRIC_CATALOG",
            ("config/metric_catalog.development.json"),
        )
    )
    catalog = load_metric_catalog(catalog_path)
    intelligent_service = _intelligent_service_from_environment(
        configured_environment,
        policy=load_policy(
            Path(
                configured_environment.get(
                    "GREENSMECAPT_ASSESSMENT_POLICY",
                    "config/assessment_profiles.development.json",
                )
            )
        ),
    )
    reader_configuration = production_reader_configuration_from_environment(configured_environment)

    return StoredDocumentProcessingService(
        storage=storage,
        reader=build_production_document_reader(reader_configuration),
        semantic_extractor=HybridSemanticExtractor(
            deterministic_extractor=(SemanticMetricExtractor(catalog)),
            catalog=catalog,
            intelligent_service=(intelligent_service),
            configuration=(
                HybridSemanticConfiguration(
                    require_intelligent_success=(
                        _environment_boolean(
                            configured_environment,
                            ("GREENSMECAPT_SEMANTIC_REQUIRED"),
                            default=False,
                        )
                    )
                )
            ),
        ),
        visual_service=VisualUnderstandingService(
            catalog=catalog,
            provider=_visual_provider_from_environment(configured_environment),
        ),
    )


def production_reader_configuration_from_environment(
    environment: Mapping[str, str] | None = None,
) -> ProductionReaderConfiguration:
    """Build resource-aware OCR deployment settings."""

    configured = environment if environment is not None else os.environ
    raw_profile = configured.get(
        "GREENSMECAPT_PADDLE_PROFILE",
        PaddleResourceProfile.LOCAL_CPU.value,
    )

    try:
        profile = PaddleResourceProfile(raw_profile.strip().casefold())
    except ValueError as error:
        allowed = ", ".join(item.value for item in PaddleResourceProfile)

        raise DocumentProcessingConfigurationError(
            f"GREENSMECAPT_PADDLE_PROFILE must be one of: {allowed}."
        ) from error

    cpu_threads = _environment_integer(
        configured,
        "GREENSMECAPT_PADDLE_CPU_THREADS",
        default=(2 if (profile is PaddleResourceProfile.LOCAL_CPU) else 4),
        minimum=1,
        maximum=64,
    )
    paddle = PaddleParserConfiguration.for_profile(
        profile,
        device=configured.get(
            "GREENSMECAPT_PADDLE_DEVICE",
            "cpu",
        ),
        cpu_threads=cpu_threads,
    )

    document_ai, document_ai_form = _google_document_ai_configurations(configured)

    return ProductionReaderConfiguration(
        paddle=paddle,
        google_document_ai=document_ai,
        google_document_ai_form=document_ai_form,
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
                ("GREENSMECAPT_TESSERACT_FALLBACK"),
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
                ("GREENSMECAPT_TESSERACT_TIMEOUT_SECONDS"),
                default=30.0,
                minimum_exclusive=0.0,
            )
        ),
    )


def _google_document_ai_configurations(
    environment: Mapping[str, str],
) -> tuple[
    GoogleDocumentAIConfiguration | None,
    GoogleDocumentAIConfiguration | None,
]:
    provider = environment.get("GREENSMECAPT_STRUCTURED_OCR_PROVIDER", "paddle").strip().casefold()
    if provider == "paddle":
        return None, None
    if provider != "google_document_ai":
        raise DocumentProcessingConfigurationError(
            "GREENSMECAPT_STRUCTURED_OCR_PROVIDER must be either 'paddle' or 'google_document_ai'."
        )

    names = {
        "project_id": "GREENSMECAPT_GOOGLE_DOCUMENT_AI_PROJECT_ID",
        "location": "GREENSMECAPT_GOOGLE_DOCUMENT_AI_LOCATION",
    }
    values = {field: environment.get(name, "").strip() for field, name in names.items()}
    missing = [name for field, name in names.items() if not values[field]]
    if missing:
        raise DocumentProcessingConfigurationError(
            "Google Document AI configuration is missing: " + ", ".join(missing)
        )

    ocr_processor_id = environment.get(
        "GREENSMECAPT_GOOGLE_DOCUMENT_AI_OCR_PROCESSOR_ID", ""
    ).strip()
    if not ocr_processor_id:
        missing.append("GREENSMECAPT_GOOGLE_DOCUMENT_AI_OCR_PROCESSOR_ID")
    if missing:
        raise DocumentProcessingConfigurationError(
            "Google Document AI configuration is missing: " + ", ".join(missing)
        )

    common = dict(
        **values,
        processor_version=(
            environment.get("GREENSMECAPT_GOOGLE_DOCUMENT_AI_PROCESSOR_VERSION") or None
        ),
        timeout_seconds=_environment_float(
            environment,
            "GREENSMECAPT_GOOGLE_DOCUMENT_AI_TIMEOUT_SECONDS",
            default=120.0,
            minimum_exclusive=0.0,
        ),
    )
    ocr = GoogleDocumentAIConfiguration(
        **common,
        processor_id=ocr_processor_id,
    )
    form_processor_id = environment.get(
        "GREENSMECAPT_GOOGLE_DOCUMENT_AI_FORM_PROCESSOR_ID", ""
    ).strip()
    form = (
        GoogleDocumentAIConfiguration(
            **common,
            processor_id=form_processor_id,
        )
        if form_processor_id
        else None
    )
    return ocr, form


def _intelligent_service_from_environment(
    environment: Mapping[str, str],
    *,
    policy: AssessmentPolicy | None = None,
) -> IntelligentSemanticExtractionService | None:
    provider_name = environment.get(
        "GREENSMECAPT_SEMANTIC_PROVIDER",
        "",
    ).strip().casefold()
    endpoint = environment.get("GREENSMECAPT_SEMANTIC_ENDPOINT")
    model = environment.get("GREENSMECAPT_SEMANTIC_MODEL")

    if not provider_name and endpoint is None and model is None:
        return None

    if not provider_name:
        provider_name = "openai_compatible"

    allow_remote = _environment_boolean(
        environment,
        "GREENSMECAPT_SEMANTIC_ALLOW_REMOTE",
        default=False,
    )
    timeout_seconds = _environment_float(
        environment,
        "GREENSMECAPT_SEMANTIC_TIMEOUT_SECONDS",
        default=120.0,
        minimum_exclusive=0.0,
    )
    maximum_output_tokens = _environment_integer(
        environment,
        "GREENSMECAPT_SEMANTIC_MAX_OUTPUT_TOKENS",
        default=8192,
        minimum=256,
        maximum=32768,
    )

    if provider_name == "vertex_gemini":
        if not model:
            raise DocumentProcessingConfigurationError(
                "Vertex Gemini extraction requires "
                "GREENSMECAPT_SEMANTIC_MODEL."
            )
        project_id = (
            environment.get("GREENSMECAPT_VERTEX_PROJECT_ID", "").strip()
            or environment.get(
                "GREENSMECAPT_GOOGLE_DOCUMENT_AI_PROJECT_ID",
                "",
            ).strip()
        )
        if not project_id:
            raise DocumentProcessingConfigurationError(
                "Vertex Gemini extraction requires "
                "GREENSMECAPT_VERTEX_PROJECT_ID or "
                "GREENSMECAPT_GOOGLE_DOCUMENT_AI_PROJECT_ID."
            )
        provider = VertexGeminiSemanticProvider(
            VertexGeminiProviderConfiguration(
                project_id=project_id,
                location=environment.get(
                    "GREENSMECAPT_VERTEX_LOCATION",
                    "global",
                ),
                model=model,
                allow_remote=allow_remote,
                timeout_seconds=timeout_seconds,
                maximum_output_tokens=maximum_output_tokens,
            )
        )
    elif provider_name == "openai_compatible":
        if not endpoint or not model:
            raise DocumentProcessingConfigurationError(
                "OpenAI-compatible extraction requires both "
                "GREENSMECAPT_SEMANTIC_ENDPOINT and "
                "GREENSMECAPT_SEMANTIC_MODEL."
            )
        provider = OpenAICompatibleSemanticProvider(
            OpenAICompatibleProviderConfiguration(
                endpoint=endpoint,
                model=model,
                api_key_environment_variable=(
                    environment.get("GREENSMECAPT_SEMANTIC_API_KEY_ENV")
                ),
                allow_remote=allow_remote,
                timeout_seconds=timeout_seconds,
                maximum_output_tokens=maximum_output_tokens,
                token_parameter=environment.get(
                    "GREENSMECAPT_SEMANTIC_TOKEN_PARAMETER",
                    "max_tokens",
                ),
            )
        )
    else:
        raise DocumentProcessingConfigurationError(
            "GREENSMECAPT_SEMANTIC_PROVIDER must be either "
            "'openai_compatible' or 'vertex_gemini'."
        )

    return IntelligentSemanticExtractionService(
        provider,
        qualitative_instructions=(_qualitative_instructions(policy) if policy is not None else ()),
        maximum_segments_per_request=_environment_integer(
            environment,
            "GREENSMECAPT_SEMANTIC_MAX_SEGMENTS",
            default=60,
            minimum=1,
            maximum=500,
        ),
        maximum_characters_per_request=_environment_integer(
            environment,
            "GREENSMECAPT_SEMANTIC_MAX_CHARACTERS",
            default=40_000,
            minimum=1_000,
            maximum=500_000,
        ),
    )

def _qualitative_instructions(
    policy: AssessmentPolicy,
) -> tuple[QualitativeInstruction, ...]:
    """Expose only policy-governed facts and assessment context to the LLM."""

    activity_facts = tuple(
        QualitativeInstruction(
            claim_id=f"activity_fact:{fact_id}",
            name=fact_id.replace("_", " "),
            question=question,
            value_type=QualitativeValueType.BOOLEAN,
        )
        for fact_id, question in policy.fact_questions.items()
    )
    criterion_context = tuple(
        QualitativeInstruction(
            claim_id=f"criterion_context:{criterion.criterion_id}",
            name=criterion.title,
            question=criterion.question,
            value_type=QualitativeValueType.SOURCE_TEXT,
            criterion_id=criterion.criterion_id,
        )
        for criterion in policy.criteria
    )
    return (*activity_facts, *criterion_context)


def _visual_provider_from_environment(
    environment: Mapping[str, str],
) -> OpenAICompatibleVisualProvider | None:
    endpoint = environment.get("GREENSMECAPT_VISUAL_ENDPOINT")
    model = environment.get("GREENSMECAPT_VISUAL_MODEL")

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
            api_key_environment_variable=(environment.get("GREENSMECAPT_VISUAL_API_KEY_ENV")),
            allow_remote=_environment_boolean(
                environment,
                "GREENSMECAPT_VISUAL_ALLOW_REMOTE",
                default=False,
            ),
            token_parameter=environment.get(
                "GREENSMECAPT_VISUAL_TOKEN_PARAMETER",
                "max_tokens",
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
        f"Environment variable {name} must be a boolean value."
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
            f"Environment variable {name} must be an integer."
        ) from error

    if value < minimum or (maximum is not None and value > maximum):
        upper = f" and at most {maximum}" if maximum is not None else ""

        raise DocumentProcessingConfigurationError(
            f"Environment variable {name} must be at least {minimum}{upper}."
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
            f"Environment variable {name} must be numeric."
        ) from error

    if value <= minimum_exclusive:
        raise DocumentProcessingConfigurationError(
            f"Environment variable {name} must be greater than {minimum_exclusive}."
        )

    return value
