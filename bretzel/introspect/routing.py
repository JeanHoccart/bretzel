"""Le routage des kwargs — dérivé du socle, jamais recopié.

**Pourquoi cette section existe, et pourquoi elle est générée.**
``kwarg-routing.md`` portait une table écrite à la main décrivant les cinq
seaux de ``split_kwargs``. Le 2026-08-16, elle contenait **trois
affirmations fausses** : les préfixes Alpine annoncés « passthrough »
(faux depuis le 2026-07-30, soit deux semaines et demie), le seau 6
nommé « catch-all » (fermé le jour même), et un avertissement affirmant
que ``bz-*`` n'y passe pas (mesuré : six le font).

Trois gates de doc existaient déjà et aucune ne pouvait les voir : elles
vérifient des chemins, des symboles, des inventaires — des choses
**décidables**. « Ce paragraphe décrit-il encore le comportement ? » ne
l'est pas.

Trois candidats de gate ont été mesurés puis **écartés** :

- une gate sur les constantes citées avec leur valeur → population de 3,
  et trois faux positifs sur trois (guillemets, placeholders) ;
- étendre la gate de vocabulaire Alpine au funnel → ~60 exceptions à
  écrire, presque toutes du récit légitime (``traps.md`` RACONTE) ;
- une gate de fraîcheur par co-changement git → 9 docs sur 11 « en
  retard » en permanence. Un signal toujours allumé n'est pas un signal.

Ce qui reste, et qui marche : **ne pas écrire la partie décidable**. Une
table qui énumère des constantes n'a pas à être recopiée — elle se lit.
La prose garde ce qui ne dérive pas : le *pourquoi*.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Bucket:
    """Un seau de ``split_kwargs``, avec ce qui y tombe."""

    rank: int
    name: str
    accepts: tuple[str, ...]
    outcome: str


def describe_kwarg_routing() -> tuple[Bucket, ...]:
    """Les seaux, lus sur les constantes du socle."""
    from bretzel.components.base.attrs import (
        _DEAD_ALPINE_PREFIXES,
        _PASSTHROUGH_PREFIXES,
        _RAW_HTML_NAMES,
        _RAW_HTML_PREFIXES,
    )
    from bretzel.components.base.component import RESERVED_KWARGS

    star = tuple(f"{p}*" for p in _PASSTHROUGH_PREFIXES)
    dead = tuple(f"{p}*" for p in _DEAD_ALPINE_PREFIXES)
    declared = tuple(f"{p}*" for p in _RAW_HTML_PREFIXES) + tuple(sorted(_RAW_HTML_NAMES))

    return (
        Bucket(0, "réservés (popés avant split_kwargs)", RESERVED_KWARGS, "cas par cas"),
        Bucket(1, "directive Alpine — morte depuis V3", dead, "ComponentUsageError"),
        Bucket(2, "passthrough verbatim", star, "passthrough"),
        Bucket(
            3,
            "prop réactive déclarée sur la classe",
            ("<__reactive_props__>",),
            "_reactive_values",
        ),
        Bucket(4, "slot nommé", ("<NAMED_SLOTS>",), "_slot_components"),
        Bucket(5, "handler d'event", ("on_<EVENTS>",), "_event_attrs"),
        Bucket(6, "échappatoire HTML DÉCLARÉE", declared, "_raw_attrs (nom normalisé)"),
        Bucket(7, "tout le reste", ("*",), "ComponentUsageError"),
    )
