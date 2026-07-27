"""Tests for the top-level GREENSMECAPT package."""

import greensmecapt


def test_package_version() -> None:
    """The package should expose its current version."""
    assert greensmecapt.__version__ == "0.1.0"