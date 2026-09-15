"""Les composants publiés par des paquets INSTALLÉS — et pourquoi ce n'est
pas le même point d'entrée que les racines à balayer.

La moitié qui manquait
----------------------
Depuis le 2026-08-29, une bibliothèque tierce voit ses classes Tailwind
compilées : elle déclare une racine dans ``bretzel.scan_roots`` et le
``style.css`` de prod les garde. Mais la porte du THÈME restait fermée ::

    Theme(components={"gauge": {...}})
    # ThemeError: aucun composant n'a cette clé de thème

``server/lifecycle._validate_theme`` juge contre
:func:`~bretzel.introspect.theme_vocabulary`, qui balaie la surface
``ui.*`` du **framework** uniquement. Un ``THEME_KEY`` livré par un paquet
n'y figurait pas, donc l'app qui l'installe ne pouvait pas le surcharger —
il lui restait ``classes=`` au point d'appel, répété partout, sans
cascade ni cohérence de thème sombre. C'est exactement la différence
entre « un composant thémé » et « du HTML copié ».

Pourquoi un point d'entrée DISTINCT
------------------------------------
``bretzel.scan_roots`` nomme déjà un module, et on aurait pu l'importer
pour y chercher les sous-classes de :class:`Component`. Ç'aurait été un
revirement, pas une extension : son contrat est écrit noir sur blanc —
« une racine déclarée est un dossier LU au démarrage, **pas du code
exécuté** », et la résolution passe par ``find_spec``, qui ne charge
rien. Le transformer en import silencieux changerait ce qu'un auteur a
accepté en écrivant la ligne.

D'où deux déclarations pour un paquet, mais deux contrats honnêtes :
« balaie mes fichiers » n'est pas « charge mon code » ::

    [project.entry-points."bretzel.scan_roots"]
    mes-composants = "mes_composants"

    [project.entry-points."bretzel.components"]
    mes-composants = "mes_composants"

La seconde ligne **importe** le module au démarrage, et c'est le prix à
payer : un ``THEME_KEY`` ne se lit pas sans charger la classe qui le
porte.

Les collisions de clé
---------------------
``"gauge"`` est libre, ``"card"`` ne l'est pas. Un paquet qui publierait
un composant sous une clé du framework rendrait ambigu tout
``Theme(components={"card": …})`` — l'app croirait styler l'un et
stylerait l'autre. La collision est donc REFUSÉE, et le message nomme
les deux côtés : c'est le seul moment où on sait encore de qui vient
quoi.
"""

from __future__ import annotations

import inspect
from functools import cache
from importlib import import_module, metadata
from typing import Any

#: Le groupe de points d'entrée. Distinct de ``bretzel.scan_roots`` —
#: cf. le docstring du module.
ENTRY_POINT_GROUP = "bretzel.components"


class ThemeKeyCollision(RuntimeError):
    """Un paquet publie un ``THEME_KEY`` que le framework porte déjà."""


@cache
def third_party_components() -> tuple[type, ...]:
    """Les classes ``Component`` publiées par les paquets installés.

    Une entrée inutilisable ne fait pas tomber le démarrage — l'app n'est
    pas responsable des métadonnées d'un tiers — mais elle ne passe pas
    en silence : les composants de ce paquet resteraient inthématisables
    et rien d'autre ne le dirait. Même arbitrage que
    ``discovered_source_roots``, dont c'est le jumeau.

    Mémoïsée : les métadonnées d'installation ne changent pas pendant la
    vie d'un process. ``third_party_components.cache_clear()`` existe pour
    les tests, qui fabriquent des points d'entrée.
    """
    from bretzel.components.base import Component

    trouves: list[type] = []
    for point in metadata.entry_points(group=ENTRY_POINT_GROUP):
        try:
            module = import_module(point.module)
        except Exception as exc:  # un tiers casse, pas nous
            print(
                f"[bretzel] WARN : le point d'entrée {ENTRY_POINT_GROUP} "
                f"« {point.name} » nomme {point.module!r}, qui ne s'importe "
                f"pas ({type(exc).__name__}).\n"
                "[bretzel]        Ses composants ne seront pas thématisables."
            )
            continue
        for _nom, objet in inspect.getmembers(module, inspect.isclass):
            if (
                issubclass(objet, Component)
                and objet is not Component
                and getattr(objet, "THEME_KEY", "")
                # Une classe RÉEXPORTÉE depuis bretzel n'est pas publiée par
                # le paquet : sans ce test, un simple ``from bretzel import
                # ui`` en tête de module ferait entrer tout le catalogue.
                and not objet.__module__.startswith("bretzel.")
            ):
                trouves.append(objet)
    # Dédoublonné par identité : un paquet qui expose la même classe depuis
    # deux modules la déclarerait deux fois.
    uniques = {id(c): c for c in trouves}
    return tuple(
        sorted(uniques.values(), key=lambda c: (c.THEME_KEY, c.__name__))
    )


def third_party_theme_vocabulary() -> dict[str, dict[str, frozenset[str]]]:
    """``THEME_KEY`` → groupe → clés, pour les composants tiers.

    Même forme que :func:`~bretzel.introspect.theme_vocabulary` pour que
    la fusion soit une simple mise à jour de dictionnaire.

    LÈVE sur une collision avec une clé du framework — cf. le docstring
    du module.
    """
    from bretzel.introspect.components import theme_vocabulary

    du_framework = theme_vocabulary()
    out: dict[str, dict[str, frozenset[str]]] = {}
    for cls in third_party_components():
        cle = cls.THEME_KEY
        if cle in du_framework:
            raise ThemeKeyCollision(
                f"{cls.__module__}.{cls.__qualname__} publie "
                f"``THEME_KEY = {cle!r}``, que le framework porte déjà.\n"
                f"  Un ``Theme(components={{{cle!r}: …}})`` deviendrait "
                f"ambigu : l'app croirait styler l'un et stylerait "
                f"l'autre.\n"
                f"  Préfixe la clé du paquet — ``{_suggestion(cls)}`` par "
                f"exemple."
            )
        out.setdefault(cle, {}).update(_groupes_de(cls))
    return out


def _suggestion(cls: type) -> str:
    """Une clé préfixée plausible, pour que le message soit actionnable."""
    paquet = cls.__module__.split(".")[0].replace("_", "-")
    return f"{paquet}-{cls.THEME_KEY}"


def _groupes_de(cls: type) -> dict[str, frozenset[str]]:
    """Les groupes surchargeables d'un ``THEME``, comme le fait le socle."""
    theme: dict[str, Any] = getattr(cls, "THEME", {}) or {}
    return {
        groupe: frozenset(valeur)
        for groupe, valeur in theme.items()
        if isinstance(valeur, dict)
    }


__all__ = [
    "ENTRY_POINT_GROUP",
    "ThemeKeyCollision",
    "third_party_components",
    "third_party_theme_vocabulary",
]
