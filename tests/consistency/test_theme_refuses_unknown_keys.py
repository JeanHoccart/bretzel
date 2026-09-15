"""Gate : une clé de thème que rien ne lit LÈVE, et au bon moment.

Le silence que ça ferme
-----------------------

Mesuré le 2026-08-16, avant ce dispositif ::

    Theme(semantic={"primry": "#f00"})            -> ACCEPTÉ
    Theme(semantic_dark={"primry": …})            -> ACCEPTÉ
    Theme(components={"crad": …})                 -> ACCEPTÉ
    Theme(components={"card": {"slots": {"rooot"}}}) -> ACCEPTÉ
    la clé fautive atteint-elle le CSS ?          -> non

Quatre façons d'écrire un thème qui ne fait rien, sans un mot. Le symptôme
— « ma couleur ne s'applique pas » — envoie chercher du côté du cache
navigateur pendant que la faute est une lettre.

Les deux moments, et pourquoi ils diffèrent
--------------------------------------------

C'est le point non-évident du dispositif, et la raison d'être de cette
gate :

- ``semantic`` / ``semantic_dark`` lèvent **à la construction**. Leurs 11
  slots vivent dans ``theme/tokens.py``, même couche : rien à aller
  chercher.
- ``components`` lève **au démarrage de l'app**. Le vocabulaire est dérivé
  des classes de composants, et le contrat ``base-independent-of-app`` de
  ``.importlinter`` interdit à ``bretzel.theme`` de les importer. Le
  démarrage est le premier endroit où les deux moitiés coexistent.

L'asymétrie est donc **imposée par l'architecture**, pas choisie. Elle a
une contrepartie qu'on garde volontairement : un ``Theme`` reste
constructible sans la couche composants, donc testable seul.

Ce qui reste OUVERT, et doit le rester
---------------------------------------

- ``palette`` / ``palette_dark`` : liste **ouverte** de couleurs nommées
  (charter : « the user can add, remove or override entries »). Fermer
  ces clés casserait la fonctionnalité.
- Les clés de ``variants`` / ``sizes`` / ``paddings``… : y ajouter une
  entrée est le chemin **recommandé** pour dévier du thème livré. Seul
  ``slots`` est fermé — un slot est composé par le code du composant, donc
  un nom qu'il ignore est mort par construction.

Ces trois cas sont testés au même titre que les refus : une gate qui ne
vérifierait que ce qui lève laisserait le durcissement déborder sur ce
qu'il ne doit pas toucher, et c'est la moitié qui coûte.
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from bretzel import Bretzel, page, ui
from bretzel.introspect import theme_vocabulary
from bretzel.theme import Theme, ThemeError

#: Preuve de morsure : contrôle POSITIF — le vocabulaire fermé contre lequel le refus est
#: prononcé n'est pas vide.
MUTATION_PROOF = "test_the_vocabulary_is_not_empty"

_SECRET = "gate-theme-secret-key-1234567890"


def _boot(theme: Theme) -> None:
    """Démarre une app minimale — c'est là que ``components`` est jugé."""

    @page("/")
    def _home() -> None:
        ui.text("gate")

    app = Bretzel(secret_key=_SECRET, mode="dev", theme=theme)
    app.include(_home)
    with TestClient(app) as client:
        assert client.get("/").status_code == 200


# ── Ce qui doit lever, et QUAND ────────────────────────────────────────


@pytest.mark.parametrize("section", ["semantic", "semantic_dark"])
def test_unknown_semantic_slot_raises_at_construction(section: str) -> None:
    """Immédiatement : les 11 slots vivent dans la même couche."""
    with pytest.raises(ThemeError, match="primry"):
        Theme(**{section: {"primry": "#ff0000"}})


@pytest.mark.parametrize(
    ("label", "components"),
    [
        ("composant inconnu", {"crad": {"slots": {"root": "x"}}}),
        ("groupe inconnu", {"card": {"slotz": {"root": "x"}}}),
        ("slot inconnu", {"card": {"slots": {"rooot": "x"}}}),
    ],
)
def test_unknown_component_key_raises_at_startup(
    label: str, components: dict
) -> None:
    """Au démarrage : le vocabulaire vient d'une couche que `theme` ne
    peut pas importer."""
    theme = Theme(components=components)  # la construction, elle, passe
    with pytest.raises(ThemeError):
        _boot(theme)


def test_the_asymmetry_is_real_and_not_an_accident() -> None:
    """Le test qui documente le piège.

    Si un jour ``components`` se met à lever dès la construction, ce test
    rougit — et c'est voulu : ce serait une bonne nouvelle, mais elle
    signifierait que ``theme`` a gagné un accès aux composants, donc que le
    contrat ``base-independent-of-app`` a bougé. Ça se décide, ça ne se
    constate pas après coup.
    """
    theme = Theme(components={"crad": {"slots": {"root": "x"}}})
    assert theme.get_component_overrides()["crad"], (
        "`Theme(components=…)` s'est mis à lever à la construction. Vérifie "
        "que `bretzel.theme` n'importe pas `bretzel.components` — "
        "`lint-imports` doit rester à 4 contrats KEPT."
    )


# ── Ce qui doit rester ACCEPTÉ ─────────────────────────────────────────


def test_palette_stays_open() -> None:
    """Une couleur nommée maison n'est pas une faute — c'est la
    fonctionnalité. Fermer ces clés casserait ``palette=``."""
    theme = Theme(palette={"brandberry": "#8b1e5a"})
    assert "brandberry" in theme.dump()


def test_value_addressed_groups_stay_open() -> None:
    """Ajouter une variante est le chemin RECOMMANDÉ, pas une faute.

    C'est la moitié qui coûte : un durcissement qui déborde ici
    condamnerait la seule sortie propre pour dévier du thème livré, et
    l'utilisateur n'aurait plus que `classes=`, qui perd contre le slot.
    """
    _boot(
        Theme(
            components={
                "button": {"variants": {"brand": "bg-indigo-500"}},
                "badge": {"sizes": {"2xl": "text-2xl"}},
            }
        )
    )


def test_a_shared_theme_key_is_accepted() -> None:
    """`sidebar_section` écrit sous `'sidebar'` — la clé du parent.

    Un validateur bâti sur les noms `ui.*` refuserait `'sidebar'` ou
    accepterait `'sidebar_section'`, qui est mort. Les deux erreurs sont
    invisibles sans ce test.
    """
    _boot(Theme(components={"sidebar": {"slots": {"section_label": "x"}}}))

    with pytest.raises(ThemeError, match="sidebar_section"):
        _boot(Theme(components={"sidebar_section": {"slots": {"section": "x"}}}))


# ── Le plancher : le vocabulaire n'est pas vide ────────────────────────


def test_the_vocabulary_is_not_empty() -> None:
    """Plancher de non-vacuité.

    Toutes les levées ci-dessus reposent sur ``theme_vocabulary()``. S'il
    rendait ``{}``, « composant inconnu » lèverait sur TOUT — les tests
    d'acceptation le verraient — mais un vocabulaire à moitié peuplé,
    lui, passerait inaperçu. On ancre donc sur la DÉCOUVERTE : les clés
    partagées, qui n'existent que si le balayage a vraiment tourné.
    """
    vocabulary = theme_vocabulary()
    assert len(vocabulary) > 50, (
        f"seulement {len(vocabulary)} clés de thème découvertes — le "
        f"balayage des composants s'est vidé, et la validation ne juge "
        f"plus grand-chose."
    )
    assert "root" in vocabulary["card"]["slots"]
    assert "section_label" in vocabulary["sidebar"]["slots"], (
        "la clé partagée `sidebar` a perdu les slots de ses sous-composants "
        "— l'union par THEME_KEY ne se fait plus."
    )
