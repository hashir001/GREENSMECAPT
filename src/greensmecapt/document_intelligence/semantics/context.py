"""Normalize explicit reporting context without inferring it."""

import re

_FISCAL_PERIOD = re.compile(
    r"\b(?:FY|fiscal\s+year|financial\s+year)\s*"
    r"(?P<period>20\d{2}(?:\s*[/\-]\s*\d{2,4})?)\b",
    flags=re.IGNORECASE,
)
_QUALIFIED_YEAR = re.compile(
    r"\b(?:reporting\s+(?:period|year)|calendar\s+year|year\s+ended)\s+"
    r"(?P<period>20\d{2}(?:\s*[/\-]\s*20?\d{2})?)\b",
    flags=re.IGNORECASE,
)
_BARE_YEAR = re.compile(
    r"(?<!\d)(?P<period>20\d{2})(?!\d)"
)
_SCOPE = re.compile(
    r"\bscope\s*[-:]?\s*(?P<number>[123])\b",
    flags=re.IGNORECASE,
)


def extract_reporting_period(
    text: str,
    *,
    allow_bare_year: bool = False,
) -> str | None:
    """Return one explicit reporting period, or no period."""

    matches = [
        f"FY{match.group('period')}"
        for match in _FISCAL_PERIOD.finditer(text)
    ]
    matches.extend(
        match.group("period")
        for match in _QUALIFIED_YEAR.finditer(text)
    )

    if allow_bare_year:
        matches.extend(
            match.group("period")
            for match in _BARE_YEAR.finditer(text)
        )

    normalized = tuple(
        dict.fromkeys(
            normalize_reporting_period(value)
            for value in matches
        )
    )

    if len(normalized) != 1:
        return None

    return normalized[0]


def normalize_reporting_period(value: str) -> str:
    """Canonicalize an explicitly reported year or fiscal period."""

    compact = " ".join(value.strip().split())
    fiscal_match = _FISCAL_PERIOD.fullmatch(compact)

    if fiscal_match is not None:
        period = re.sub(
            r"\s*([/\-])\s*",
            r"\1",
            fiscal_match.group("period"),
        )
        return f"FY{period}"

    return re.sub(r"\s*([/\-])\s*", r"\1", compact)


def extract_scope(text: str) -> str | None:
    """Return one explicit emissions scope, or no scope."""

    scopes = tuple(
        dict.fromkeys(
            f"scope {match.group('number')}"
            for match in _SCOPE.finditer(text)
        )
    )

    if len(scopes) != 1:
        return None

    return scopes[0]


def normalize_scope(value: str) -> str:
    """Canonicalize an explicit scope label."""

    match = _SCOPE.fullmatch(value.strip())

    if match is not None:
        return f"scope {match.group('number')}"

    return " ".join(value.casefold().split())