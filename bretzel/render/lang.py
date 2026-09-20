"""Which language to serve THIS request — and the word table that goes with it.

The pair of :mod:`bretzel.render.screen`, and for the same reason: the
browser knows something the server has to render. There it is the shape of
the screen, here the language; in both cases a cookie carries the choice,
and the server renders from a real value rather than guessing.

The split with :mod:`bretzel.render.texts` is clean: **this module picks
the language, the other owns the words.**

The chain, and why its order is the subject
-------------------------------------------
1. the ``bz_lang`` cookie, if it names a declared language;
2. ``Accept-Language``, negotiated against the app's languages;
3. the default language (``Bretzel(lang=…)``).

That is Django's order (``LocaleMiddleware``), Rails's and next-intl's,
and it is not a matter of taste. ``Accept-Language`` describes the
operating system's configuration, **not a reading choice**: someone whose
system is in English but who reads in French must be able to say so, and
without a cookie above the header a language selector would be
unwritable. A page depending on the header alone also stops being
addressable — two people opening the same URL see two pages, which breaks
bookmarks, search indexing, and forces the cache to ``Vary``.

Reversing that order breaks **nothing visible**: negotiation keeps
working, pages keep rendering, and only the selector stops having an
effect, for the people whose system is not in the language they chose.
Hence two measurements rather than a re-read:
``tests/integration/test_the_language_is_resolved_per_request.py`` and
``tests/probes/probe_lang.py``, which exercises it in the browser.

What this module does not do
----------------------------
Translate the app's strings. :attr:`Language.code` returns the resolved
language, and a dict per language in the app does the rest in six lines;
catalogues, extraction and per-language plural rules are a separate
project (v2.1). What was really missing was knowing WHICH language to
serve.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from bretzel.core.errors import BretzelError
from bretzel.render.texts import DEFAULT_TEXTS, TextsError, resolve_texts
from bretzel.runtime.protocol import LANG_COOKIE

__all__ = [
    "Language",
    "LanguageTables",
    "negotiate_language",
    "resolve_language",
]


#: ``fr``, ``fr-CA``, ``*`` — plus a tolerated ``;q=0,8`` (some proxies
#: produce it). Everything else is silently ignored: a malformed header
#: is noise from the network, not an app error.
_ACCEPT_ITEM = re.compile(
    r"^\s*(?P<tag>[A-Za-z]{1,8}(?:-[A-Za-z0-9]{1,8})*|\*)"
    r"\s*(?:;\s*q\s*=\s*(?P<q>[0-9]+(?:[.,][0-9]+)?))?\s*$"
)


def _primary(tag: str) -> str:
    """``fr-CA`` → ``fr``. Comparison is always done in lower case."""
    return tag.lower().split("-", 1)[0]


def negotiate_language(
    header: str | None,
    available: Sequence[str],
    *,
    default: str,
) -> str:
    """Choose a language from ``Accept-Language`` or use ``default``."""
    if len(available) <= 1 or not header:
        return default

    ranked: list[tuple[float, str]] = []
    for chunk in header.split(","):
        match = _ACCEPT_ITEM.match(chunk)
        if match is None:
            continue
        raw_q = match.group("q")
        quality = float(raw_q.replace(",", ".")) if raw_q else 1.0
        if quality > 0:
            ranked.append((quality, match.group("tag")))
    # ``sort`` is STABLE, including with ``reverse``: insertion order
    # (the header's) therefore breaks ties between equal qualities,
    # without having to carry an index in the tuple.
    ranked.sort(key=lambda row: row[0], reverse=True)

    #: last one wins — two entries with the same tag are an app fault,
    #: not an ambiguity to arbitrate.
    exact = {code.lower(): code for code in available}
    #: first one wins: ``["fr-CA", "fr"]`` must serve ``fr-BE`` through
    #: ``fr-CA``, the first declared, not through the last.
    primaries: dict[str, str] = {}
    for code in available:
        primaries.setdefault(_primary(code), code)

    for _, tag in ranked:
        if tag == "*":
            return default
        hit = exact.get(tag.lower()) or primaries.get(_primary(tag))
        if hit is not None:
            return hit
    return default


class LanguageTables:
    """Store the framework text table for each declared language."""

    __slots__ = ("_default", "_tables")

    def __init__(
        self,
        overrides: Mapping[str, Any] | None,
        *,
        languages: Iterable[str],
        default: str,
    ) -> None:
        codes = list(dict.fromkeys([default, *languages]))
        self._default = default
        # Any declared but unoverridden language falls back to English.
        # No error: an app adding ``"de"`` before having translated it
        # must be able to serve it, in English, rather than refuse to
        # start.
        self._tables: dict[str, Mapping[str, str]] = dict.fromkeys(
            codes, DEFAULT_TEXTS
        )
        if not overrides:
            return

        nested = {k for k, v in overrides.items() if isinstance(v, Mapping)}
        # ``flat`` = everything else, not "the strings": a value of a
        # third type would slip between two lists and escape the guard
        # below.
        flat = set(overrides) - nested
        if nested and flat:
            raise TextsError(
                f"texts= mixes the two forms: {sorted(flat)[:3]} are "
                f"sentences (flat form) and {sorted(nested)[:3]} are tables "
                f"(per-language form). Pick one — a dict containing both "
                f"has no correct reading."
            )
        if not nested:
            self._tables[default] = resolve_texts(overrides)  # type: ignore[arg-type]
            return

        unknown = sorted(nested - set(codes))
        if unknown:
            raise TextsError(
                f"texts= overrides undeclared languages: "
                f"{', '.join(repr(c) for c in unknown)}. Add them to "
                f"``languages=``, otherwise nobody will ever receive them — "
                f"a table nothing can select is work lost in silence."
            )
        for code in nested:
            self._tables[code] = resolve_texts(overrides[code])

    def for_language(self, code: str) -> Mapping[str, str]:
        """Return the table for ``code`` or for the default language."""
        return self._tables.get(code) or self._tables[self._default]

    def languages(self) -> tuple[str, ...]:
        """Return supported language codes with the default first."""
        return tuple(self._tables)

    def __repr__(self) -> str:
        return f"LanguageTables({', '.join(self.languages())})"


def resolve_language(
    *,
    cookie: str | None,
    header: str | None,
    available: Sequence[str],
    default: str,
) -> str:
    """Resolve the language for the current request."""
    if cookie and cookie in available:
        return cookie
    return negotiate_language(header, available, default=default)


class Language:
    """Read or select the language for the current request."""

    __slots__ = ("code",)

    #: This request's resolved language, in BCP-47 — ``"en"``,
    #: ``"fr-CA"``.
    #:
    #: Annotated HERE and not merely assigned in ``__init__``: the
    #: descriptor ``__slots__`` sets would be enough at runtime, but
    #: ``test_cited_symbols_resolve`` reads classes at the AST level,
    #: where a slot is only a string in a tuple. Without this line, any
    #: prose writing ``:attr:`Language.code``` turns red. (``Screen``
    #: does without it because no prose cites its fields by a role.)
    code: str

    #: One year. A language preference has no reason to expire with the
    #: session: someone who chose French still wants it on their return.
    _COOKIE_MAX_AGE = 365 * 24 * 3600

    def __init__(self) -> None:
        from bretzel.render.context import maybe_current_context

        ctx = maybe_current_context()
        self.code = getattr(ctx, "lang", None) or "en"

    @classmethod
    def set(cls, code: str) -> None:
        """Select the language and reload the page in that language."""
        # ``navigation`` is ABOVE ``render`` in the DAG, hence the
        # deferred import — same shape as ``render/context.py``, which
        # reaches up to ``server.handlers`` to sign an action.
        # ``current_context`` is from the same layer, deferred by the
        # same convention as ``render/screen.py``.
        #
        # That upward reach is the subject's asymmetry, and it is real:
        # ``Language`` is the only one of the four ambient reads whose
        # WRITE is a server round trip (cookie + reload). Its read side
        # stays where it is read; its write side reaches up. (The concept
        # itself already spreads over three layers — the cookie name is
        # in ``runtime/protocol.py``, the ``languages`` declaration in
        # ``server/config.py``.)
        from bretzel.render.context import current_context
        from bretzel.server.navigation import reload as _reload

        ctx = current_context()
        languages = ctx.app.config.languages
        if code not in languages:
            hint = (
                " The app declares only one: add Bretzel(languages=['en', 'fr'])."
                if len(languages) <= 1
                else ""
            )
            raise BretzelError(
                f"Language.set({code!r}): undeclared language. languages="
                f"{list(languages)}.{hint}"
            )
        ctx.set_cookie(
            LANG_COOKIE,
            code,
            max_age=cls._COOKIE_MAX_AGE,
            samesite="lax",
            # Readable in JS ON PURPOSE, unlike the session cookie:
            # this is not a secret, and an app wanting to offer its
            # language client-side must be able to read it.
            httponly=False,
            path="/",
        )
        _reload()
