"""Validate API deployment configuration."""

import os
from urllib.parse import urlsplit


def cors_origins_from_environment() -> tuple[str, ...]:
    """Return unique, explicit browser origins for CORS."""

    raw_origins = os.environ.get(
        "GREENSMECAPT_CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    )
    origins = tuple(
        dict.fromkeys(
            origin.strip().rstrip("/")
            for origin in raw_origins.split(",")
            if origin.strip()
        )
    )

    for origin in origins:
        parsed = urlsplit(origin)

        if (
            origin == "*"
            or parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                f"Invalid GREENSMECAPT CORS origin: {origin!r}."
            )

    return origins
