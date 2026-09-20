"""Original-document storage for GREENSMECAPT."""

from greensmecapt.storage.documents import (
    DocumentStorage,
    DocumentStorageError,
    LocalDocumentStorage,
)
from greensmecapt.storage.factory import storage_from_environment
from greensmecapt.storage.supabase import (
    StorageResponse,
    SupabaseDocumentStorage,
    SupabaseStorageConfiguration,
)

__all__ = [
    "DocumentStorage",
    "DocumentStorageError",
    "LocalDocumentStorage",
    "StorageResponse",
    "SupabaseDocumentStorage",
    "SupabaseStorageConfiguration",
    "storage_from_environment",
]
