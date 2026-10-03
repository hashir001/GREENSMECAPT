"""Select document storage from deployment configuration."""

import os

from greensmecapt.paths import PROJECT_ROOT
from greensmecapt.storage.documents import (
    DocumentStorage,
    DocumentStorageError,
    LocalDocumentStorage,
)
from greensmecapt.storage.supabase import (
    SupabaseDocumentStorage,
    SupabaseStorageConfiguration,
)


def storage_from_environment() -> DocumentStorage:
    """Build the explicitly selected document-storage backend."""

    backend = os.environ.get(
        "GREENSMECAPT_STORAGE_BACKEND",
        "local",
    ).strip().casefold()

    if backend == "local":
        return LocalDocumentStorage(
            os.environ.get(
                "GREENSMECAPT_STORAGE_ROOT",
                str(PROJECT_ROOT / "data" / "documents"),
            )
        )

    if backend != "supabase":
        raise DocumentStorageError(
            f"Unknown document storage backend: {backend!r}."
        )

    project_url = os.environ.get(
        "GREENSMECAPT_SUPABASE_URL",
    )
    service_role_key = os.environ.get(
        "GREENSMECAPT_SUPABASE_SERVICE_ROLE_KEY",
    )
    missing = tuple(
        name
        for name, value in (
            ("GREENSMECAPT_SUPABASE_URL", project_url),
            (
                "GREENSMECAPT_SUPABASE_SERVICE_ROLE_KEY",
                service_role_key,
            ),
        )
        if not value
    )

    if missing:
        raise DocumentStorageError(
            "Supabase document storage is missing: "
            + ", ".join(missing)
            + "."
        )

    return SupabaseDocumentStorage(
        SupabaseStorageConfiguration(
            project_url=project_url,
            service_role_key=service_role_key,
            bucket=os.environ.get(
                "GREENSMECAPT_SUPABASE_STORAGE_BUCKET",
                "source-documents",
            ),
        )
    )
