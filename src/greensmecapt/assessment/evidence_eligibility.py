"""Shared rules for deciding whether reviewed evidence may enter assessment."""

from greensmecapt.domain import (
    EvidenceClaimNature,
    EvidenceItem,
    EvidenceValidationStatus,
    SMEVerificationStatus,
)


def is_reviewed_evidence(item: EvidenceItem) -> bool:
    """Return true only for accepted evidence not disputed by its SME owner."""

    return (
        item.validation_status is EvidenceValidationStatus.ACCEPTED
        and item.sme_verification.status
        not in {
            SMEVerificationStatus.CORRECTION_PROPOSED,
            SMEVerificationStatus.NOT_APPLICABLE,
        }
    )


def describes_current_state(item: EvidenceItem) -> bool:
    """Keep targets and projections out of achieved/current performance."""

    return item.claim_nature not in {
        EvidenceClaimNature.TARGET,
        EvidenceClaimNature.PROJECTED,
    }


def is_current_reviewed_evidence(item: EvidenceItem) -> bool:
    """Return true for usable evidence describing actual/current conditions."""

    return is_reviewed_evidence(item) and describes_current_state(item)
