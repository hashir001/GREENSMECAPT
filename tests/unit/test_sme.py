"""Tests for the SME domain model."""

import pytest
from pydantic import ValidationError

from greensmecapt.domain import SME


def test_create_sme() -> None:
    """A valid SME should be created."""

    sme = SME(
        sme_id="sme_001",
        legal_name="EcoPack Manufacturing LLC",
        sector="Sustainable Packaging",
        jurisdiction="United Arab Emirates",
    )

    assert sme.sme_id == "sme_001"
    assert sme.legal_name == "EcoPack Manufacturing LLC"
    assert sme.sector == "Sustainable Packaging"
    assert sme.jurisdiction == "United Arab Emirates"


def test_reject_blank_legal_name() -> None:
    """An SME with a blank legal name should be rejected."""

    with pytest.raises(ValidationError):
        SME(
            sme_id="sme_001",
            legal_name="   ",
            sector="Sustainable Packaging",
            jurisdiction="United Arab Emirates",
        )


def test_reject_unexpected_sme_field() -> None:
    """Unknown fields should not silently enter the SME model."""

    with pytest.raises(ValidationError):
        SME(
            sme_id="sme_001",
            legal_name="EcoPack Manufacturing LLC",
            sector="Sustainable Packaging",
            jurisdiction="United Arab Emirates",
            invented_score=99,
        )