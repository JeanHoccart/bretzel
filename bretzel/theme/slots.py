"""Pure helpers for component-theme slot resolution and override merging.

Component themes are plain dicts of the shape ::

    {
        "slots":    {"root": "...", "icon": "..."},
        "variants": {"solid": "...", "outline": "..."},
        "sizes":    {"sm": "...", "md": "..."},
    }

Les valeurs sont des chaînes de classes Tailwind **complètes**. Elles
l'ont été à partir du 2026-08-30 : jusque-là elles portaient des trous
``{bg_color}`` / ``{fg_color}``, comblés au rendu contre le ``color=``
du composant. Ce mécanisme a été déposé avec la phase 5 du chantier des
jetons de couleur — les thèmes lisent maintenant des PALIERS
(``bg-(--bz-bg)``), et c'est la classe-pont posée sur la racine qui dit
de quelle couleur il s'agit (cf. :mod:`bretzel.theme.bridges`).

Ce que la dépose a supprimé, et pourquoi c'était le bon moment :
``resolve_slot``, ``resolve_slot_or_keyword``, ``PLACEHOLDER_NAMES`` et
``SHAPE_TOKEN_RE``. Un trou n'est **pas une classe** : le compilateur ne
peut pas le voir, donc il fallait en calculer la CLÔTURE — chaque forme
× chaque couleur, 3 791 classes, 80 % du ``style.css``. Un palier est une
classe complète.

Ce module expose désormais :

- :func:`merge_component_themes` : fusion profonde non mutante des
  surcharges de l'utilisateur sur un thème de base.
- :func:`validate_component_overrides` : le refus d'une clé inconnue.

Les deux sont pures (pas d'E/S, pas de contextvars), donc mesurables et
raisonnables en isolation.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from bretzel.theme.palette import Palette, ThemeError

#: Les noms de couleur qui ne sont NI un slot sémantique NI une entrée de
#: palette, et qu'on accepte quand même parce qu'ils désignent une vraie
#: couleur CSS. Aujourd'hui un seul : ``current`` → ``currentColor``.
#:
#: Cet ensemble est lu à DEUX endroits qui doivent s'accorder — le
#: générateur de PONTS (``theme/bridges.py``, qui décide quelles
#: classes-ponts existent dans le CSS) et le refus du socle
#: (``components/base/_wiring._refuse_unknown_color``, qui décide quels
#: noms le rendu a le droit d'émettre). Les faire lire la MÊME constante
#: est ce qui interdit à une couleur d'être émise sans pont : ce qui n'a
#: pas de règle ici est refusé là.
#:
#: ⚠️ N'ajoute un nom ici que s'il désigne une couleur CSS valide, sur
#: laquelle les douze formules de palier peuvent partir. Une couleur de
#: MARQUE va dans la palette (``Theme(palette={...})``), pas ici — elle y
#: reçoit son pont toute seule.
COLOR_KEYWORDS: frozenset[str] = frozenset({"current"})


def merge_component_themes(
    base: dict[str, Any],
    override: dict[str, Any],
) -> dict[str, Any]:
    """Deep-merge ``override`` on top of ``base`` — non-mutating.

    Recursion rule : at every depth, dicts are merged key-by-key ;
    anything else (string / list / int / None) is replaced wholesale
    by the override value.

    Inputs are never mutated — both ``base`` and ``override`` come
    out unchanged. The returned tree is a fresh structure so callers
    can mutate it freely.

    Example ::

        base = {
            "slots":    {"root": "...", "icon": "..."},
            "variants": {"solid": "...", "outline": "..."},
            "sizes":    {"sm": "...", "md": "..."},
        }
        override = {"slots": {"root": "rounded-full ..."}}

        merge_component_themes(base, override) == {
            "slots":    {"root": "rounded-full ...", "icon": "..."},
            "variants": {"solid": "...", "outline": "..."},
            "sizes":    {"sm": "...", "md": "..."},
        }
    """
    if not isinstance(base, dict) or not isinstance(override, dict):
        # Caller passed something weird — treat override as the winner.
        return _deep_copy(override) if override is not None else _deep_copy(base)

    out: dict[str, Any] = {}
    keys = list(base.keys())
    for k in override:
        if k not in keys:
            keys.append(k)

    for key in keys:
        if key in base and key in override:
            base_v = base[key]
            over_v = override[key]
            if isinstance(base_v, dict) and isinstance(over_v, dict):
                out[key] = merge_component_themes(base_v, over_v)
            else:
                out[key] = _deep_copy(over_v)
        elif key in override:
            out[key] = _deep_copy(override[key])
        else:
            out[key] = _deep_copy(base[key])
    return out


def _deep_copy(value: Any) -> Any:
    """Tiny recursive copy.

    We avoid :func:`copy.deepcopy` because the only mutable structures
    we expect (dict / list) are simple, and bringing in ``copy``
    adds an import for no value.
    """
    if isinstance(value, dict):
        return {k: _deep_copy(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_deep_copy(v) for v in value]
    # Primitives + tuples + frozensets are already immutable.
    return value


# ───────────────────────────────────────────────────────────────────────────
# Validation des surcharges de composant
# ───────────────────────────────────────────────────────────────────────────


#: Le seul groupe dont on ferme les CLÉS. Ailleurs — ``variants``,
#: ``sizes``, ``paddings``… — une clé neuve ÉTEND le thème, et c'est le
#: chemin recommandé pour dévier du thème livré : la fermer condamnerait
#: la seule sortie propre. Un slot, lui, est composé par le code du
#: composant (``compose_class("root")``) : un nom qu'il ignore est mort par
#: construction, rien ne peut le réveiller depuis l'app.
CLOSED_GROUP: str = "slots"


def validate_component_overrides(
    components: Mapping[str, Any],
    vocabulary: Mapping[str, Mapping[str, frozenset[str]]],
) -> None:
    """Lève si une surcharge nomme quelque chose que rien ne lira.

    ``vocabulary`` est **injecté** : la couche ``theme`` n'a pas le droit
    d'importer ``components`` (contrat ``base-independent-of-app`` de
    ``.importlinter``), donc elle ne peut pas se le procurer elle-même.
    Même dispositif que ``color_shapes`` dans ``generate_theme_css_full``,
    et même raison.

    Conséquence assumée, à connaître : ``Theme(components={"crad": …})``
    ne lève **pas** à la construction — un ``Theme`` reste constructible
    sans la couche composants, ce qui est ce qui le rend testable seul. La
    levée arrive au **démarrage de l'app**, appelée depuis
    ``server.lifecycle``, avant que quoi que ce soit d'autre ne soit
    monté. ``Theme(semantic=…)`` lève, lui, immédiatement : ses 11 slots
    vivent dans la même couche.

    Ce qu'on refuse, dans l'ordre où on le rencontre :

    1. une **clé de composant** qu'aucun ``THEME_KEY`` ne porte ;
    2. un **groupe** que ce composant n'a pas ;
    3. une clé de ``slots`` que ce composant ne compose jamais.
    """
    for name, override in components.items():
        groups = vocabulary.get(name)
        if groups is None:
            raise ThemeError(
                f"Theme(components={{{name!r}: …}}) : aucun composant n'a "
                f"cette clé de thème. La clé est `THEME_KEY`, pas toujours "
                f"le nom `ui.*` — `sidebar_section` s'écrit sous "
                f"`'sidebar'`. `bretzel describe <nom>` la donne."
            )
        if not isinstance(override, Mapping):
            continue
        for group, entries in override.items():
            if group not in groups:
                raise ThemeError(
                    f"Theme(components={{{name!r}: {{{group!r}: …}}}}) : "
                    f"`{name}` n'a pas de groupe `{group}`. Ses groupes : "
                    f"{', '.join(sorted(groups)) or '(aucun)'}."
                )
            if group != CLOSED_GROUP or not isinstance(entries, Mapping):
                continue
            unknown = sorted(set(entries) - set(groups[group]))
            if unknown:
                raise ThemeError(
                    f"Theme(components={{{name!r}: {{'slots': …}}}}) : "
                    f"`{name}` ne compose aucun slot {unknown}. Ses slots : "
                    f"{', '.join(sorted(groups[group])) or '(aucun)'}. Un "
                    f"slot est composé par le code du composant, donc un "
                    f"nom qu'il ignore est mort : rien ne peut le réveiller "
                    f"depuis l'app."
                )
