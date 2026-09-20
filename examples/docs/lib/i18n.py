"""Explicit bilingual copy for the public Bretzel documentation."""

from bretzel import Language


def tr(en: str, fr: str) -> str:
    """Return the copy for the language resolved for this request."""
    return fr if Language().code.startswith("fr") else en
