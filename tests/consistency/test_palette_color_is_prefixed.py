"""Gate G2 — une couleur de **palette** passe par le thème, jamais par un
``f"text-{color}"`` en Python.

Deux familles de couleurs, deux formes de classe (``theme/palette.py``
``bg_class``) :

- **sémantique** (``primary``, ``muted``, ``success``…) → sans préfixe :
  ``text-primary`` ;
- **palette** (``tomato``, ``sky``… de ``DEFAULT_PALETTE``) → préfixée :
  ``text-ui-tomato``.

D'où le piège : un composant qui bâtit sa classe à la main avec
``f"text-{color}"`` **marche pour les sémantiques** — le cas testé
partout — et émet ``text-tomato``, une classe que Tailwind ne génère
jamais, dès qu'on lui passe une couleur de palette. La couleur est
silencieusement ignorée. Seul le passage par le placeholder
``{bg_color}`` (résolu par ``_resolve_template`` / ``compose_class``)
connaît le préfixe.

Cette gate teste le **symptôme**, pas la forme du code : on rend chaque
composant qui accepte ``color=`` avec une couleur de palette, et on exige
que TOUS les tokens qui la mentionnent soient préfixés. Un futur
composant qui réinvente l'interpolation à la main tombe dedans, quelle
que soit la syntaxe qu'il emploie.

⚠️ Le rig a besoin d'un vrai ``Theme`` : sans contexte d'app,
``_resolve_template`` retombe sur une substitution bête qui produit
``text-tomato`` même pour un slot correct — la gate ne discriminerait
plus rien. (C'est aussi pourquoi ``test_color_wiring`` ne voyait pas ces
dérives : il n'exerce que ``success``, une sémantique.)

Trouvé par l'audit 2026-07-18 (F28 Link / F29 Divider / F30 Heading) ;
la gate a ajouté Table, que l'audit avait manqué.
"""

from __future__ import annotations

import re

import pytest

from bretzel.components.base.testing import render_isolated
from bretzel.core.serialize import serialize
from bretzel.theme import Theme
from tests.consistency._discovery import public_component_classes

# Une couleur de DEFAULT_PALETTE (non sémantique) : sa classe DOIT porter
# le préfixe de palette.
_COLOR = "tomato"
# ``tomato`` non précédé du préfixe ``ui-``. On borne à gauche sur le tiret
# de l'utilitaire Tailwind (``text-``, ``bg-``, ``ring-``, ``border-``…)
# pour ne pas matcher ``ui-tomato`` ni un ``tomato`` en texte libre.
#: Une couleur de palette écrite SANS le préfixe ``ui-``.
#:
#: ``bz-c-tomato`` est exclu : ce n'est pas un utilitaire Tailwind mais
#: la classe-PONT que le socle tamponne sur toute racine colorée (cf.
#: :mod:`bretzel.theme.bridges`). Elle porte le nom nu à dessein — c'est
#: notre espace de noms, pas celui des couleurs de Tailwind — et sa
#: présence est vérifiée par ``test_a_color_bridge_derives_everything``.
#: Sans cette exclusion la gate rougissait sur 21 composants qui n'ont
#: rien fait de mal (mesuré le 2026-08-30, en migrant le Badge).
_UNPREFIXED = re.compile(r"(?<!ui)(?<!bz-c)-tomato\b")


def _colour_aware(cls: type) -> bool:
    # ``__reactive_props__``, avec les dunder : le nom de l'attribut posé par
    # la métaclasse. Écrit ``_reactive_props`` jusqu'au 2026-07-29, la clause
    # rendait donc ``{}`` sur les 76 composants et ne sélectionnait RIEN —
    # mesuré : 0 contre 46. La gate ne tenait que par son fallback
    # ``hasattr``, qui donne le même ensemble aujourd'hui mais raterait un
    # composant portant une prop reactive ``color`` sans attribut de classe.
    return "color" in getattr(cls, "__reactive_props__", {}) or hasattr(cls, "color")


_CANDIDATES = [c for c in public_component_classes() if _colour_aware(c)]


def test_the_gate_has_a_population() -> None:
    """Plancher de non-vacuité — et il aurait attrapé le bug ci-dessus.

    ``_colour_aware`` lisait ``_reactive_props`` (sans dunder), donc sa
    première clause rendait ``{}`` sur les 76 composants. Un plancher aurait
    fait tomber la population à 0 le jour de la faute au lieu de laisser le
    fallback ``hasattr`` masquer la panne pendant des mois."""
    assert len(_CANDIDATES) >= 40, (
        f"seulement {len(_CANDIDATES)} composants sont détectés comme "
        f"colour-aware (46 mesurés le 2026-07-29) — la détection a régressé, "
        f"la gate ne vérifie plus grand-chose."
    )


@pytest.mark.parametrize("cls", _CANDIDATES, ids=lambda c: c.__name__)
def test_palette_color_reaches_the_dom_prefixed(cls: type) -> None:
    try:
        with render_isolated(theme=Theme()):
            out = serialize(cls(color=_COLOR).render())
    except Exception as exc:
        pytest.skip(f"{cls.__name__} non constructible nu : "
                    f"{type(exc).__name__}: {exc}")

    if _COLOR not in out:
        pytest.skip(f"{cls.__name__} n'émet aucun token de couleur "
                    f"(color= design-time non utilisé dans son thème)")

    stray = _UNPREFIXED.search(out)
    assert stray is None, (
        f"{cls.__name__} : color={_COLOR!r} produit "
        f"…{out[max(0, stray.start() - 24):stray.end() + 8]}… — une classe "
        f"non préfixée que Tailwind ne génère pas pour une couleur de "
        f"palette. La couleur est silencieusement perdue (les sémantiques "
        f"comme 'primary' masquent le bug : elles sont sans préfixe).\n"
        f"Fix : passer par le thème — `{{bg_color}}` dans le slot, résolu "
        f"par `compose_class` / `self._resolve_template('text-{{bg_color}}', "
        f"color)` — jamais `f\"text-{{color}}\"`."
    )


def test_the_detector_still_bites() -> None:
    """Mutation : une couleur de palette NON préfixée est reconnue.

    Le préfixe ``ui-`` est ce qui distingue une couleur de la palette
    Bretzel d'une couleur Tailwind du même nom. Sans lui, la classe
    émise ne résout aucune variable de thème — et c'est invisible en
    dev, où le compilateur navigateur scanne le DOM déjà résolu.
    """
    for offending in ("bg-tomato", "text-tomato/40", "ring-tomato"):
        assert _UNPREFIXED.search(offending), f"{offending!r} devrait mordre"
    for licit in ("bg-ui-tomato", "text-ui-tomato/40"):
        assert not _UNPREFIXED.search(licit), f"{licit!r} : faux positif"
