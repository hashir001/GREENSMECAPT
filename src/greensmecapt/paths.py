"""Stable project-relative paths for local development defaults."""

from collections.abc import Mapping
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def configured_path(
    environment: Mapping[str, str],
    variable: str,
    default_relative_path: str,
) -> Path:
    """Keep explicit paths untouched and anchor only built-in defaults."""

    configured = environment.get(variable)
    if configured:
        return Path(configured).expanduser()
    return PROJECT_ROOT / default_relative_path
