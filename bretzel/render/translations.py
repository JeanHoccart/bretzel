"""The words of an app in each language it declares — :func:`t`.

One table per language says every word on screen, whoever wrote it::

    app = Bretzel(lang="en", languages=("en", "fr"), translations={"fr": {
        "Create": "Créer",
        "Hello {name}": "Bonjour {name}",
        "{n} task": {"one": "{n} tâche", "other": "{n} tâches"},
        "sidebar.toggle": "Ouvrir le menu",
    }})

The app's own sentences are keyed by the sentence itself. A sentence
Bretzel wrote — "Clear filters", the sidebar's button — is keyed by its
name in :data:`bretzel.render.texts.DEFAULT_TEXTS` (lowercase words
joined by dots, :data:`FRAMEWORK_KEY`) and replaces the framework's own
words in that language. Rails and Django do the same: whoever wants to
change a word on screen does not have to know who wrote it.

    ui.button(t("Create"))                          # « Créer » for a French visitor
    ui.text(t("Hello {name}", name=user.name))
    ui.text(t("{n} task", n=count, plural="{n} tasks"))

**The sentence written in the code is the key** — gettext's choice
(Django's ``_()``), not i18next's ``t("button.create")``: the code reads
as the screen does, and a sentence nobody translated yet still shows,
in the language it was written in, rather than a key or an error. A
counted sentence takes the form the language says for ``n``
(:func:`bretzel.render.languages.plural_category`): « 0 tâche » in
French, "0 tasks" in English.

With every language written in every call, adding one would mean editing
every line, and no translator could work without the code. Django, Rails,
Laravel and Symfony ship this function; an integrated stack has no reason
not to.

``bretzel translations main:app`` lists, language by language, the
sentences ``t()`` is called with that a table lacks, and the entries no
call uses any more.

⚠️ :func:`t` reads the REQUEST's language: it is called while rendering
or handling, not in a module-level constant — evaluated once, at import,
for nobody. A column label is a function, not a tuple.
"""

from __future__ import annotations

import difflib
import re
from collections.abc import Iterable, Mapping
from string import Formatter
from typing import Any

__all__ = ["FRAMEWORK_KEY", "TranslationTables", "TranslationsError", "split_translations", "t"]

#: The shape of a sentence Bretzel wrote (``sidebar.toggle``,
#: ``datatable.results_few``): lowercase words joined by dots. An app's own
#: sentence is written as it reads, and does not take that shape.
FRAMEWORK_KEY = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")


class TranslationsError(ValueError):
    """Raised at startup when ``translations=`` cannot be read right."""


def _holes(template: str) -> set[str]:
    return {field for _, field, _, _ in Formatter().parse(template) if field}


def _primary(code: str) -> str:
    return code.lower().split("-", 1)[0]


def split_translations(
    raw: Mapping[str, Any] | None,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """``translations=`` → the framework's sentences it replaces, and the
    app's own, each by language.

    Every language of ``raw`` keeps an entry on the app's side, empty if
    need be, so :class:`TranslationTables` checks every code it names. A
    key shaped like a framework key that names none RAISES: a typo there
    would otherwise read as an app sentence nobody calls, and the
    framework's word would stay on screen without a word.
    """
    from bretzel.render.texts import DEFAULT_TEXTS, _reference

    framework: dict[str, dict[str, Any]] = {}
    own: dict[str, dict[str, Any]] = {}
    for code, table in (raw or {}).items():
        own[code] = {}
        if not isinstance(table, Mapping):
            own[code] = table  # refused, with its reason, by TranslationTables
            continue
        for key, said in table.items():
            if not FRAMEWORK_KEY.match(key):
                own[code][key] = said
            elif _reference(key) is not None:
                framework.setdefault(code, {})[key] = said
            else:
                near = difflib.get_close_matches(key, DEFAULT_TEXTS, n=1)
                raise TranslationsError(
                    f"translations[{code!r}][{key!r}] is shaped like a sentence of Bretzel's, "
                    f"and none is named so"
                    + (f" — did you mean {near[0]!r}?" if near else ".")
                    + " The names are listed in bretzel.render.texts.DEFAULT_TEXTS.")
    return framework, own


class TranslationTables:
    """The app's tables, checked once at startup, queried per request."""

    __slots__ = ("_tables",)

    def __init__(self, raw: Mapping[str, Any] | None, *, languages: Iterable[str],
                 default: str) -> None:
        from bretzel.render.texts import PLURAL_FORMS

        declared = list(dict.fromkeys([default, *languages]))
        self._tables: dict[str, Mapping[str, Any]] = {}
        for code, table in (raw or {}).items():
            if code not in declared:
                raise TranslationsError(
                    f"translations= has a table for {code!r}, a language the app does not "
                    f"declare ({declared}). Add it to languages=, otherwise nobody will "
                    f"ever receive it.")
            if not isinstance(table, Mapping):
                raise TranslationsError(
                    f"translations[{code!r}] must be a dict: the sentence as written in the "
                    f"code → its translation.")
            for source, said in table.items():
                forms = said if isinstance(said, Mapping) else {"other": said}
                unknown = sorted(set(forms) - set(PLURAL_FORMS))
                if unknown or "other" not in forms:
                    raise TranslationsError(
                        f"translations[{code!r}][{source!r}]: a counted sentence gives its "
                        f"forms among {list(PLURAL_FORMS)}, ``other`` always — got "
                        f"{sorted(forms)}.")
                for form, template in forms.items():
                    if _holes(template) != _holes(source):
                        raise TranslationsError(
                            f"translations[{code!r}][{source!r}]"
                            f"{'' if not isinstance(said, Mapping) else f'[{form!r}]'} does "
                            f"not have the holes of its sentence: expected "
                            f"{sorted(_holes(source)) or 'none'}, got "
                            f"{sorted(_holes(template)) or 'none'}.")
            self._tables[code] = table

    def for_language(self, code: str) -> Mapping[str, Any]:
        """The table of ``code`` — ``fr-CA`` takes ``fr``'s —, or an empty one."""
        if code in self._tables:
            return self._tables[code]
        primary = _primary(code)
        return next((table for lang, table in self._tables.items()
                     if _primary(lang) == primary), {})

    def languages(self) -> tuple[str, ...]:
        """The languages that have a table."""
        return tuple(self._tables)

    def __repr__(self) -> str:
        return f"TranslationTables({', '.join(self._tables)})"


def _request_table() -> tuple[str, Mapping[str, Any]]:
    """The request's language and its table — none outside a full app: a
    unit test, a script, a render without an app."""
    from bretzel.render.context import maybe_current_context

    ctx = maybe_current_context()
    lang = getattr(ctx, "lang", None) or "en"
    config = getattr(getattr(ctx, "app", None), "config", None)
    tables = getattr(config, "translation_tables", None)
    return lang, (tables.for_language(lang) if tables is not None else {})


def t(source: str, /, *, plural: str | None = None, **holes: Any) -> str:
    """``source`` in the request's language, its holes filled.

    ``plural``: the sentence counts ``n`` (a hole it must be given) —
    ``source`` is its singular, ``plural`` the rest, in the language the
    code is written in; a translation gives the forms of its language. A
    sentence no table translates is shown as written.
    """
    from bretzel.render.languages import plural_category

    lang, table = _request_table()
    said = table.get(source)
    if plural is None:
        template = said if isinstance(said, str) else source
    else:
        if "n" not in holes:
            raise TypeError(f"t({source!r}, plural=…) counts n: pass n=.")
        form = plural_category(lang, int(holes["n"]))
        if isinstance(said, Mapping):
            template = said.get(form) or said["other"]
        elif isinstance(said, str):
            template = said
        else:
            template = source if form == "one" else plural
    try:
        return template.format(**holes)
    except (KeyError, IndexError) as exc:
        raise TypeError(
            f"t({source!r}) expects the hole {exc}, which the call did not give.") from None
