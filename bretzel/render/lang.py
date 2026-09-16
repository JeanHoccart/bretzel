"""Quelle langue servir à CETTE requête — et la table de mots qui va avec.

Pair de :mod:`bretzel.render.screen`, et pour la même raison : le
navigateur sait quelque chose que le serveur doit rendre. Là-bas c'est la
forme de l'écran, ici la langue ; dans les deux cas un cookie porte le
choix, et le serveur rend depuis une vraie valeur plutôt que de deviner.

Le partage avec :mod:`bretzel.render.texts` est net : **ce module choisit
la langue, l'autre possède les mots.**

La chaîne, et pourquoi son ordre est le sujet
----------------------------------------------
1. le cookie ``bz_lang``, s'il nomme une langue déclarée ;
2. ``Accept-Language``, négocié contre les langues de l'app ;
3. la langue par défaut (``Bretzel(lang=…)``).

C'est l'ordre de Django (``LocaleMiddleware``), de Rails et de
next-intl, et ce n'est pas un goût. ``Accept-Language`` décrit la
configuration du système d'exploitation, **pas un choix de lecture** :
quelqu'un dont le système est anglais mais qui lit en français doit
pouvoir le dire, et sans un cookie au-dessus de l'en-tête un sélecteur
de langue serait inécrivable. Une page qui dépend du seul en-tête cesse
aussi d'être adressable — deux personnes ouvrant la même URL voient deux
pages, ce qui casse les favoris, le référencement, et oblige le cache à
``Vary``.

Inverser cet ordre ne casse **rien de visible** : la négociation
continue de marcher, les pages continuent de rendre, et seul le
sélecteur cesse d'avoir un effet, pour les gens dont le système n'est
pas dans la langue qu'ils ont choisie. D'où deux mesures plutôt qu'une
relecture : ``tests/integration/test_the_language_is_resolved_per_request.py``
et ``tests/probes/probe_lang.py``, qui l'éprouve au navigateur.

Ce que ce module ne fait pas
-----------------------------
Traduire les chaînes de l'app. :attr:`Language.code` rend la langue
résolue, et un
dict par langue dans l'app fait le reste en six lignes ; les catalogues,
l'extraction et les règles de pluriel par langue sont un chantier à part
(v2.1). Ce qui manquait vraiment, c'était de savoir QUELLE langue servir.
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


#: ``fr``, ``fr-CA``, ``*`` — plus un ``;q=0,8`` toléré (des proxys en
#: produisent). Tout le reste est ignoré silencieusement : un en-tête mal
#: formé est du bruit venu du réseau, pas une erreur de l'app.
_ACCEPT_ITEM = re.compile(
    r"^\s*(?P<tag>[A-Za-z]{1,8}(?:-[A-Za-z0-9]{1,8})*|\*)"
    r"\s*(?:;\s*q\s*=\s*(?P<q>[0-9]+(?:[.,][0-9]+)?))?\s*$"
)


def _primary(tag: str) -> str:
    """``fr-CA`` → ``fr``. La comparaison se fait toujours en minuscules."""
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
    # ``sort`` est STABLE, y compris avec ``reverse`` : l'ordre d'ajout
    # (celui de l'en-tête) départage donc les qualités égales, sans avoir
    # à porter un index dans le tuple.
    ranked.sort(key=lambda row: row[0], reverse=True)

    #: dernier gagnant — deux entrées de même étiquette sont une faute de
    #: l'app, pas une ambiguïté à arbitrer.
    exact = {code.lower(): code for code in available}
    #: premier gagnant : ``["fr-CA", "fr"]`` doit servir ``fr-BE`` par
    #: ``fr-CA``, la première déclarée, pas par la dernière.
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
        # Toute langue déclarée mais non surchargée retombe sur l'anglais.
        # Pas d'erreur : une app qui ajoute ``"de"`` avant d'avoir traduit
        # doit pouvoir la servir, en anglais, plutôt que refuser de démarrer.
        self._tables: dict[str, Mapping[str, str]] = dict.fromkeys(
            codes, DEFAULT_TEXTS
        )
        if not overrides:
            return

        nested = {k for k, v in overrides.items() if isinstance(v, Mapping)}
        # ``flat`` = tout le reste, pas « les chaînes » : une valeur d'un
        # troisième type se glisserait entre deux listes et échapperait au
        # garde ci-dessous.
        flat = set(overrides) - nested
        if nested and flat:
            raise TextsError(
                f"texts= mélange les deux formes : {sorted(flat)[:3]} sont des "
                f"phrases (forme plate) et {sorted(nested)[:3]} des tables "
                f"(forme par langue). Choisis-en une — un dict qui contient "
                f"les deux n'a pas de lecture juste."
            )
        if not nested:
            self._tables[default] = resolve_texts(overrides)  # type: ignore[arg-type]
            return

        unknown = sorted(nested - set(codes))
        if unknown:
            raise TextsError(
                f"texts= surcharge des langues non déclarées : "
                f"{', '.join(repr(c) for c in unknown)}. Ajoute-les à "
                f"``languages=``, sinon personne ne les recevra jamais — une "
                f"table que rien ne peut sélectionner est du travail perdu en "
                f"silence."
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

    #: La langue résolue de cette requête, en BCP-47 — ``"en"``,
    #: ``"fr-CA"``.
    #:
    #: Annotée ICI et pas seulement assignée dans ``__init__`` : le
    #: descripteur que ``__slots__`` pose suffirait à l'exécution, mais
    #: ``test_cited_symbols_resolve`` lit les classes à l'AST, où un
    #: slot n'est qu'une chaîne dans un tuple. Sans cette ligne, toute
    #: prose qui écrit ``:attr:`Language.code``` rougit. (``Screen`` s'en
    #: passe parce qu'aucune prose ne cite ses champs par un rôle.)
    code: str

    #: Un an. Une préférence de langue n'a pas de raison d'expirer avec la
    #: session : quelqu'un qui a choisi le français le veut encore au retour.
    _COOKIE_MAX_AGE = 365 * 24 * 3600

    def __init__(self) -> None:
        from bretzel.render.context import maybe_current_context

        ctx = maybe_current_context()
        self.code = getattr(ctx, "lang", None) or "en"

    @classmethod
    def set(cls, code: str) -> None:
        """Select the language and reload the page in that language."""
        # ``navigation`` est AU-DESSUS de ``render`` dans le DAG, d'où
        # l'import différé — même forme que ``render/context.py``, qui
        # remonte vers ``server.handlers`` pour signer une action.
        # ``current_context`` est de la même couche, différé par la même
        # convention que ``render/screen.py``.
        #
        # Cette remontée est l'asymétrie du sujet, et elle est vraie :
        # ``Language`` est la seule des quatre lectures d'ambiance dont
        # l'ÉCRITURE est un aller-retour serveur (cookie + rechargement).
        # Son versant lecture reste où on le lit ; son versant écriture
        # remonte. (Le concept, lui, s'étale déjà sur trois couches — le
        # nom du cookie est dans ``runtime/protocol.py``, la déclaration
        # ``languages`` dans ``server/config.py``.)
        from bretzel.render.context import current_context
        from bretzel.server.navigation import reload as _reload

        ctx = current_context()
        languages = ctx.app.config.languages
        if code not in languages:
            hint = (
                " L'app n'en déclare qu'une : ajoute Bretzel(languages=['en', 'fr'])."
                if len(languages) <= 1
                else ""
            )
            raise BretzelError(
                f"Language.set({code!r}) : langue non déclarée. languages="
                f"{list(languages)}.{hint}"
            )
        ctx.set_cookie(
            LANG_COOKIE,
            code,
            max_age=cls._COOKIE_MAX_AGE,
            samesite="lax",
            # Lisible en JS À DESSEIN, contrairement au cookie de session :
            # ce n'est pas un secret, et une app qui veut proposer sa langue
            # côté client doit pouvoir la lire.
            httponly=False,
            path="/",
        )
        _reload()
