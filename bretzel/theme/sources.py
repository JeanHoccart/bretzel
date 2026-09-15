"""Les racines que le compilateur de prod BALAIE — et qui les déclare.

Tailwind ne compile pas seulement le CSS d'entrée : il lit des fichiers
pour savoir quelles classes garder. Sans directive, il ne lit que le
``cwd``. Ce module répond donc à une seule question, et c'est toute sa
raison d'être : **quels dossiers, en plus du dossier courant.**

Trois réponses, et l'ordre dit leur nature :

1. **Le paquet du framework**, toujours, sans que personne ne le
   demande. Le bug fermé le 2026-08-29 était exactement son absence :
   installé par pip, ``bretzel`` n'est plus sous le ``cwd``, donc les
   classes de ses ``theme.py`` disparaissaient du ``style.css`` de prod
   — 609 Ko contre 684, sans une erreur, avec les bonnes couleurs et
   aucune mise en forme.
2. **Ce que les paquets installés déclarent**, via le point d'entrée
   ``bretzel.scan_roots`` (cf. :func:`discovered_source_roots`).
3. Rien d'autre. Il n'y a **pas** de troisième porte — ni kwarg de
   ``Theme``, ni option de config. Une seule manière de faire chaque
   chose (principe 4 de la charte), et c'est celle-ci parce qu'elle est
   la seule où ``pip install`` suffit : l'app n'a rien à écrire pour
   qu'un paquet tiers soit balayé.

Déclarer une racine
-------------------
Un paquet qui porte des classes Tailwind — une bibliothèque de
composants tierce, **ou l'app elle-même quand elle est livrée en
paquet** — le dit dans son ``pyproject.toml`` ::

    [project.entry-points."bretzel.scan_roots"]
    mes-composants = "mes_composants"

La clé est libre (elle ne sert qu'aux diagnostics) ; la valeur est le
**nom d'un module importable**, dont le dossier devient la racine.

⚠️ **Une racine déclarée est un dossier LU au démarrage**, pas du code
exécuté : la résolution passe par :func:`importlib.util.find_spec`, qui
ne charge pas le module.
"""

from __future__ import annotations

import sys
from collections.abc import Iterable
from functools import cache
from importlib import metadata, util
from pathlib import Path

#: Le paquet installé — la racine qui porte les thèmes de composant.
#:
#: ``parents[1]`` depuis ``bretzel/theme/sources.py`` donne ``bretzel/``,
#: **où que le paquet soit posé** : le dépôt en développement, ou le
#: ``site-packages`` de qui l'installe.
#:
#: Elle est calculée, PAS découverte, et c'est délibéré : passer par le
#: point d'entrée ferait dépendre le rendu du framework de la présence
#: de ses propres métadonnées, donc casserait un ``git clone`` non
#: installé. La seule racine dont on connaît le chemin sans rien lire
#: est aussi la seule qu'on ne peut pas se permettre de rater.
FRAMEWORK_SOURCE_ROOT: Path = Path(__file__).resolve().parents[1]

#: Le groupe de points d'entrée. C'est une **API publique** : un paquet
#: tiers l'écrit dans son ``pyproject.toml``, donc le renommer casse ses
#: métadonnées sans qu'aucun test de ce dépôt ne le voie.
ENTRY_POINT_GROUP = "bretzel.scan_roots"


@cache
def discovered_source_roots() -> tuple[Path, ...]:
    """Les racines que les paquets installés déclarent, triées.

    **Triées, et c'est structurel** : l'ordre des points d'entrée dépend
    de l'ordre du ``sys.path`` et du système de fichiers. Or ces racines
    entrent dans le CSS, dont l'empreinte NOMME le fichier compilé en
    cache (``build.get_or_build_css``). Un ordre instable produirait
    deux empreintes pour un même environnement, donc une recompilation
    de deux secondes à chaque démarrage — la maladie exacte réparée le
    2026-08-27, réintroduite par la porte d'à côté.

    Une entrée inutilisable ne fait pas tomber le démarrage — l'app
    n'est pas responsable des métadonnées d'un tiers — mais elle ne
    passe pas en silence : les classes de ce paquet manqueraient en
    prod, et rien d'autre ne le dirait. Même arbitrage que le repli du
    compilateur, qui s'annonce lui aussi.

    Mémoïsée : les métadonnées d'installation ne changent pas pendant la
    vie d'un process. ``discovered_source_roots.cache_clear()`` existe
    pour les tests, qui fabriquent des points d'entrée.
    """
    roots: set[Path] = set()
    for point in metadata.entry_points(group=ENTRY_POINT_GROUP):
        path = _root_of_module(point.module)
        if path is None:
            print(
                f"[bretzel] WARN : le point d'entrée {ENTRY_POINT_GROUP} "
                f"« {point.name} » nomme {point.module!r}, introuvable.\n"
                "[bretzel]        Ses classes Tailwind manqueront du "
                "style.css compilé."
            )
            continue
        roots.add(path)
    return tuple(sorted(roots))


def _root_of_module(name: str) -> Path | None:
    """Le dossier d'un module importable, **sans l'importer**.

    Un paquet (``mes_composants``) rend son dossier ; un module simple
    (``mes_composants.theme``) rend le dossier qui le contient — les
    deux formes marchent, parce qu'un auteur écrira l'une ou l'autre
    sans penser à la différence.

    Retourne ``None`` quand le nom ne résout pas : paquet désinstallé,
    métadonnées orphelines, faute de frappe.
    """
    already_loaded = sys.modules.get(name)
    if already_loaded is not None:
        spec = getattr(already_loaded, "__spec__", None)
    else:
        try:
            spec = util.find_spec(name)
        except (ImportError, AttributeError, ValueError):
            return None
    if spec is None:
        return None
    if spec.submodule_search_locations:
        return Path(next(iter(spec.submodule_search_locations))).resolve()
    if spec.origin and spec.origin != "built-in":
        return Path(spec.origin).resolve().parent
    return None


def all_source_roots() -> tuple[Path, ...]:
    """Le paquet du framework, puis ce que les autres déclarent.

    Le framework en tête parce qu'il est le seul certain ; le reste
    trié par :func:`discovered_source_roots`. Une racine déclarée deux
    fois n'apparaît qu'une.
    """
    roots: list[Path] = [FRAMEWORK_SOURCE_ROOT]
    roots.extend(
        r for r in discovered_source_roots() if r != FRAMEWORK_SOURCE_ROOT
    )
    return tuple(roots)


def generate_source_directives(roots: Iterable[Path | str]) -> str:
    """Return the Tailwind v4 ``@source "<dir>";`` block for ``roots``.

    Mesure du 2026-08-29, ``cwd`` = un dossier d'app quelconque, chemin
    de prod réel (``get_or_build_css``) ::

        sans directive   609 Ko   tabular-nums ABSENT · 16rem ABSENT
        avec             684 Ko   les deux PRESENT

    La safelist ``@source inline(...)`` ne pouvait pas rattraper le
    coup, et c'est ce qui rend les deux mécanismes complémentaires
    plutôt que redondants : la safelist ne clôt que ce que le scanner ne
    PEUT pas voir (un ``{bg_color}`` non résolu au render). Une classe
    statique comme ``rounded-md`` est parfaitement visible — à condition
    qu'on regarde le bon dossier.

    Un chemin est écrit tel quel dans du CSS : un guillemet dedans
    couperait la directive au milieu, donc il lève plutôt que de
    produire une feuille cassée.

    ⚠️ **Pour le compilateur de prod uniquement.** Le compilateur
    navigateur du mode dev lit le DOM vivant, pas le disque ; ces
    directives sont retirées du CSS inliné par
    :func:`bretzel.theme.css.strip_scan_roots`.
    """
    lines: list[str] = []
    for root in roots:
        path = Path(root).resolve().as_posix()
        if '"' in path:
            raise ValueError(
                f"Racine de balayage inutilisable : {path!r} contient un "
                'guillemet, qui terminerait la directive @source "…" au '
                "milieu du chemin."
            )
        lines.append(f'@source "{path}";')
    return "\n".join(lines)


__all__ = [
    "ENTRY_POINT_GROUP",
    "FRAMEWORK_SOURCE_ROOT",
    "all_source_roots",
    "discovered_source_roots",
    "generate_source_directives",
]
