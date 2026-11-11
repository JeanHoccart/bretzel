"""The framework's words in the languages it ships, and how each counts.

English is :data:`bretzel.render.texts.DEFAULT_TEXTS`; the others live
here, one module each, with the same keys and the same holes. A language
the framework does not ship is served in English — an app gives its
sentences through ``translations=``.

**Counting is part of the language.** French says the singular for 0
and 1, English for 1 alone — "0 results" — and Russian or Polish have a
third and a fourth form. The rules below are CLDR's for whole numbers —
the framework only ever counts things (results, files, points) — for the
languages a Bretzel app is likely to declare; any other counts as English
does, ``one`` for 1.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

from bretzel.render.languages import fr

__all__ = ["BUILT_IN", "built_in", "plural_category"]

#: Primary language subtag → the framework's words in it.
BUILT_IN: Mapping[str, Mapping[str, str]] = {"fr": fr.TEXTS}


def _primary(code: str) -> str:
    """``fr-CA`` → ``fr``."""
    return code.lower().split("-", 1)[0]


def built_in(code: str) -> Mapping[str, str] | None:
    """The table the framework ships for ``code`` (``fr-CA`` takes ``fr``'s), or none."""
    return BUILT_IN.get(_primary(code))


def _slavic(n: int) -> str:
    """Russian, Ukrainian: 1, 21, 31… / 2–4, 22–24… / the rest."""
    if n % 10 == 1 and n % 100 != 11:
        return "one"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return "few"
    return "many"


def _polish(n: int) -> str:
    """Polish: 1 alone / 2–4, 22–24… but not 12–14 / the rest."""
    if n == 1:
        return "one"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return "few"
    return "many"


def _czech(n: int) -> str:
    """Czech, Slovak: 1 / 2–4 / the rest."""
    return "one" if n == 1 else "few" if 2 <= n <= 4 else "other"


_RULES: Mapping[str, Callable[[int], str]] = {
    # French counts 0 with the singular — « 0 résultat » — as Portuguese.
    **dict.fromkeys(("fr", "pt"), lambda n: "one" if n in (0, 1) else "other"),
    **dict.fromkeys(("ru", "uk"), _slavic),
    "pl": _polish,
    **dict.fromkeys(("cs", "sk"), _czech),
    # One form for every number.
    **dict.fromkeys(("ja", "zh", "ko", "vi", "th", "id"), lambda n: "other"),
}


def plural_category(code: str, n: int) -> str:
    """The CLDR category of the whole number ``n`` in ``code``: ``one``,
    ``few``, ``many`` or ``other``."""
    rule = _RULES.get(_primary(code))
    if rule is None:
        return "one" if abs(n) == 1 else "other"
    return rule(abs(n))
