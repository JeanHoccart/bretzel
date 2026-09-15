"""Kwargs splitting + attribute-name normalisation.

Components accept a wild kwargs surface : reactive props, named slots,
event handlers, raw HTML attrs (including ``aria_*`` / ``data_*`` /
``role`` / …), raw pass-through attrs (**``hx-`` seul** — ``:`` / ``@`` /
``x-`` LÈVENT depuis le 2026-07-30, cf. ``reject_dead_alpine_attr``), and
a few reserved framework keywords (``classes``, ``slots``, ``key``…).

This module is the dispatcher : :func:`split_kwargs` carves a single
``**kwargs`` dict into five buckets that the :class:`Component`
constructor consumes one by one.

"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from bretzel.components.base.component import Component


# ``on_<event>`` matches any lowercase event with optional underscores.
EVENT_PATTERN: re.Pattern[str] = re.compile(r"^on_[a-z][a-z0-9_]*$")


# HTMX attrs qui passent verbatim. Un composant n'a en principe pas à en
# écrire (cf. CLAUDE.md principe 2 : la frontière transport est runtime-only),
# mais quelques-uns pilotent le swap engine directement — sidebar/navbar pour
# la nav partielle, notification pour les toasts OOB, form, radio, table.
_PASSTHROUGH_PREFIXES: tuple[str, ...] = ("hx-",)

# ── Les préfixes Alpine, morts depuis V3 ─────────────────────────────────
# Ce tuple valait ``(":", "@", "x-", "hx-")``. Le commit 10e34c2e (2026-07-03)
# a renommé ``_RAW_ALPINE_PREFIXES`` → ``_PASSTHROUGH_PREFIXES`` en annonçant
# « Pure behaviour-neutral rename […] no logic touched » : le NOM a été
# dé-Alpiné, la VALEUR non.
#
# Mesuré le 2026-07-29 : le moteur de directives ne scanne que ``bz-attr:``
# et ``bz-on:`` (``02_directives.js``, ``startsWith`` — zéro occurrence de
# ``x-`` / ``@`` / ``:`` comme préfixe d'attribut). Un ``ui.card(**{"@click":
# "alert(1)", "x-show": "open"})`` partait donc dans le DOM, valide, et
# PERSONNE ne le regardait jamais : zéro erreur, zéro warning, zéro effet.
#
# ⚠️ Retirer le préfixe de la liste ne suffit PAS à fermer le mode d'échec :
# ``normalize_attr_name`` rend tel quel tout nom contenant ``-``/``:``/``@``,
# donc le catch-all ``raw_html`` émettrait exactement le même attribut. C'est
# le REFUS BRUYANT ci-dessous qui est le fix ; le tuple n'est que du
# vocabulaire.
_DEAD_ALPINE_PREFIXES: tuple[str, ...] = (":", "@", "x-")

# ── L'échappatoire HTML brute, désormais DÉCLARÉE ────────────────────────
#
# Jusqu'au 2026-08-16, le seau 5 était un catch-all muet : **tout** kwarg
# inconnu partait dans le DOM en attribut inerte. C'était le seul des cinq
# seaux à ne rien refuser — un event inconnu lève, un slot inconnu lève,
# une directive Alpine lève. Le garde-fou existait, il n'avait juste
# jamais été posé ici.
#
# Ce que ça coûtait : 44 kwargs morts mesurés sur ``examples/`` le
# 2026-08-01, dont ``ui.input(label=…)`` sur 22 sites qui rendaient
# ``<input label="…">`` — aucun libellé affiché, aucune erreur, rien à
# voir dans le HTML.
#
# ⚠️ **Le refus n'est PAS « refuser l'inconnu ».** Mesuré au runtime sur
# les 14 685 tests (instrumentation du seau 5) : 17 kwargs distincts y
# passaient, et l'écrasante majorité était LÉGITIME —
#
#   34 ``aria_label``, 6 ``class_``, 6 directives ``bz-*``, 4 ``data_*``,
#   1 ``role``… et cinq vrais morts (``clearable``, ``options``, ``href``,
#   ``value``, ``foo``), tous dans ``tests/``.
#
# Refuser sec aurait cassé 51 usages justes pour attraper 5 fautes. Le
# fix est donc de rendre l'échappatoire **explicite** : ces familles-là
# passent, tout le reste lève. Un scan AST ne l'aurait pas vu — il ratait
# ``class_`` et les ``bz-*``, qui arrivent par des helpers.
_RAW_HTML_PREFIXES: tuple[str, ...] = (
    "aria_",
    "aria-",
    "data_",
    "data-",
    # Le vocabulaire du runtime : ``bz-on:click``, ``bz-attr:placeholder``,
    # ``bz-class``, ``bz-show``. C'est l'idiom du framework, pas une
    # échappatoire — mais il arrive bien par ici quand on l'écrit en kwarg.
    "bz-",
)

#: Les noms EXACTS admis sans préfixe. Deux, et chacun sa raison.
_RAW_HTML_NAMES: frozenset[str] = frozenset(
    {
        # L'échappe Python standard pour l'attribut ``class`` — le socle ne
        # le pope pas (ce n'est pas un kwarg réservé), il ressort en
        # ``class=`` et cohabite avec ``classes=``. Testé par
        # ``test_attr_precedence_is_one_contract``.
        "class_",
        # Attribut ARIA sans préfixe ``aria-``. Le refuser obligerait à
        # écrire ``attrs={"role": …}`` pour l'attribut d'accessibilité le
        # plus courant après ``aria-label``.
        "role",
        # ── La famille de l'ancre ────────────────────────────────────────
        # Débloquée par ``tag="a"``, le retag universel. Le cas réel est
        # l'export du datatable : un ``Button`` retagué en ancre, PARCE QUE
        # seule une ancre peut télécharger, et qui doit rester visuellement
        # un bouton (il vit dans une barre d'outils à côté de « Clear
        # filters »). Cf. ``datatable.py`` § Export CSV.
        #
        # ⚠️ C'est la limite honnête de ce refus : la validité d'un attribut
        # HTML dépend du TAG RENDU, que ``split_kwargs`` ne connaît pas —
        # ``tag=`` est retiré par le constructeur avant d'arriver ici. Donc
        # ``ui.button(href=…)`` SANS ``tag="a"`` passe encore et reste
        # inerte. Le fermer demanderait de valider attribut contre tag,
        # c'est-à-dire d'embarquer une table HTML : un autre chantier.
        # `bretzel check` le voit, lui, puisqu'il lit le call-site.
        "href",
        "target",
        "rel",
        "download",
    }
)


def is_declared_raw_attr(python_name: str) -> bool:
    """``True`` si le kwarg est une échappatoire HTML brute **déclarée**."""
    return python_name in _RAW_HTML_NAMES or python_name.startswith(_RAW_HTML_PREFIXES)


class ComponentDefinitionError(TypeError):
    """Raised at class creation time when a component is malformed
    (e.g. ``EVENTS`` lists an event with no matching ``on_<event>``
    parameter in ``__init__``)."""


class ComponentUsageError(TypeError):
    """Raised at instantiation time when the user mis-uses a component
    (unknown slot, event handler for an event that isn't supported)."""


# ───────────────────────────────────────────────────────────────────────────
# normalize_attr_name — Python kwargs → HTML attrs
# ───────────────────────────────────────────────────────────────────────────


def normalize_attr_name(python_name: str) -> str:
    """Convert a Python-friendly kwarg name to an HTML attribute name.

    Rules :

    - Names already containing ``-``, ``:``, ``@`` are returned as-is
      (raw pass-through / HTMX attrs that the developer typed deliberately).
    - Trailing underscores (``class_``, ``for_``) are stripped — these
      are the standard Python escapes for HTML keywords that clash
      with Python builtins.
    - Internal underscores convert to dashes (``aria_label`` →
      ``aria-label``, ``data_testid`` → ``data-testid``).
    """
    if not python_name:
        return python_name
    # Trois scans C plutôt qu'un générateur de 3 tours : 8 241 appels
    # par rendu de /tabs, soit 32 964 itérations Python économisées.
    if "-" in python_name or ":" in python_name or "@" in python_name:
        return python_name
    if python_name.endswith("_"):
        python_name = python_name.rstrip("_")
    # ``data_*`` and ``aria_*`` follow the dash convention.
    return python_name.replace("_", "-")


def is_passthrough_attr(python_name: str) -> bool:
    """``True`` when the kwarg is a raw HTMX attribute that should pass
    through to the rendered element verbatim."""
    # ``startswith`` accepte un tuple et boucle en C. Le générateur
    # équivalent coûtait 5 itérations Python par attribut : profilé sur
    # un rendu de /tabs, 9 951 appels y produisaient 49 755 itérations.
    return python_name.startswith(_PASSTHROUGH_PREFIXES)


def reject_dead_alpine_attr(owner: str, name: str) -> None:
    """Lève si ``name`` porte un préfixe de directive Alpine.

    Appelé sur les DEUX voies d'entrée d'un attribut brut — ``**kwargs``
    (via :func:`split_kwargs`) et ``attrs={...}`` — parce que l'attribut est
    aussi inerte dans un cas que dans l'autre. Laisser passer l'un des deux
    rendrait le refus incohérent, et c'est exactement le genre d'asymétrie
    qui fait qu'un mécanisme n'est pas adopté.

    Le message pointe vers l'équivalent ``bz-`` : c'est ce qui transforme le
    refus en aide plutôt qu'en mur.
    """
    if not name.startswith(_DEAD_ALPINE_PREFIXES):
        return
    if name.startswith("@"):
        suggestion = f"``bz-on:{name[1:]}``"
    elif name.startswith(":"):
        suggestion = f"``bz-attr:{name[1:]}``"
    else:  # ``x-``
        suggestion = f"``bz-{name[2:]}``"
    raise ComponentUsageError(
        f"{owner}({name}=…) : ``{name}`` est une directive Alpine, et Alpine "
        f"n'est plus dans Bretzel depuis V3. Le runtime ne scanne que "
        f"``bz-attr:`` et ``bz-on:`` — cet attribut partirait dans le DOM "
        f"sans que rien ne le lise jamais.\n"
        f"  Écris {suggestion} à la place. Pour brancher le SERVEUR, ne "
        f"passe pas d'attribut du tout : déclare un handler "
        f"``on_<event>=`` et le socle émet le POST signé."
    )


# ───────────────────────────────────────────────────────────────────────────
# split_kwargs — the bucket dispatcher
# ───────────────────────────────────────────────────────────────────────────


def split_kwargs(
    cls: type[Component],
    kwargs: dict[str, Any],
) -> tuple[
    dict[str, Any],  # reactive props
    dict[str, Any],  # named slots
    dict[str, Any],  # event handlers (keys keep ``on_`` prefix)
    dict[str, Any],  # raw pass-through / htmx attrs (keys kept verbatim)
    dict[str, Any],  # raw HTML attrs (keys normalised to dash form)
]:
    """Carve ``kwargs`` into the five buckets the :class:`Component`
    constructor consumes.

    Reserved keywords (``classes``, ``style``, ``slots``, ``key``,
    ``id``, ``tag``, ``attrs``, ``visible``, ``tooltip``, ``debounce``,
    ``throttle``) are NOT touched here — the constructor pops them out
    before calling :func:`split_kwargs`.

    Validation :

    - An ``on_<event>`` key whose ``<event>`` is not in ``cls.EVENTS``
      raises :class:`ComponentUsageError`.
    - A slot name not in ``cls.NAMED_SLOTS`` raises
      :class:`ComponentUsageError`.

    The function never mutates ``kwargs`` — callers can iterate over
    the input again if needed.
    """
    reactive_props = getattr(cls, "__reactive_props__", {}) or {}
    declared_events: tuple[str, ...] = getattr(cls, "EVENTS", ())
    named_slots: tuple[str, ...] = getattr(cls, "NAMED_SLOTS", ())

    reactive: dict[str, Any] = {}
    slots: dict[str, Any] = {}
    events: dict[str, Any] = {}
    passthrough: dict[str, Any] = {}
    raw_html: dict[str, Any] = {}

    for key, value in kwargs.items():
        # 0. Directive Alpine — morte depuis V3, refus bruyant.
        reject_dead_alpine_attr(cls.__name__, key)

        # 1. Raw HTMX — verbatim, no kwargs decoding.
        if is_passthrough_attr(key):
            passthrough[key] = value
            continue

        # 2. Reactive prop declared on the class.
        if key in reactive_props:
            reactive[key] = value
            continue

        # 3. Named slot declared by the component author.
        if key in named_slots:
            slots[key] = value
            continue

        # 4. Event handler — must match the declared event list.
        match = EVENT_PATTERN.match(key)
        if match:
            event = key[3:]  # drop ``on_``
            if event not in declared_events:
                raise ComponentUsageError(
                    f"{cls.__name__} does not declare an ``on_{event}`` event "
                    f"(EVENTS = {declared_events!r}). Either add it to the "
                    "class, ou passe par ``attrs={'bz-on:x': …}`` — un "
                    "kwarg ``@…`` LÈVE désormais."
                )
            events[key] = value
            continue

        # 5. Anything else — raw HTML attr. Normalise the name to the
        # dashed form HTML expects.
        #
        # Special guard : a :class:`Component` instance can never be a
        # raw HTML attribute value. If we land here with one, the user
        # almost certainly mistyped a named-slot kwarg (``trailing=icon``
        # vs the declared ``icon_right``). Raise loudly so the typo
        # doesn't silently drop into ``raw_html``.
        if _looks_like_component(value):
            raise ComponentUsageError(
                f"{cls.__name__}({key}=…) received a component instance "
                "but no such named slot is declared "
                f"(NAMED_SLOTS = {named_slots!r}). Either register the slot "
                "on the class or rename the kwarg."
            )
        if not is_declared_raw_attr(key):
            raise ComponentUsageError(
                f"{cls.__name__}({key}=…) : ce composant ne lit pas "
                f"``{key}``, et ce n'est pas une échappatoire HTML déclarée. "
                f"L'attribut serait parti dans le DOM sans que rien ne le "
                f"lise — aucune erreur, aucun effet, rien à voir dans le "
                f"HTML.\n"
                f"  ``bretzel describe {cls.__name__.lower()}`` liste ce "
                f"qu'il accepte.\n"
                f"  Si tu veux vraiment cet attribut HTML : "
                f"``attrs={{'{normalize_attr_name(key)}': …}}``. Les familles "
                f"admises directement en kwarg sont "
                f"{', '.join(_RAW_HTML_PREFIXES)}* "
                f"et {', '.join(sorted(_RAW_HTML_NAMES))}."
            )
        raw_html[normalize_attr_name(key)] = value

    return reactive, slots, events, passthrough, raw_html


def _looks_like_component(value: Any) -> bool:
    """``True`` if ``value`` quacks like a :class:`Component` instance.

    Avoiding a direct import of :class:`Component` keeps this module's
    dependency graph minimal — structural detection on a few telltale
    attributes is enough for the slot-misuse guard.
    """
    return all(hasattr(value, attr) for attr in ("render", "id", "_reactive_values"))
