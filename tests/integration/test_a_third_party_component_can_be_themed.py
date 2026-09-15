"""Une bibliotheque TIERCE peut etre thémée par l'app qui l'installe.

Le defaut que ca ferme
-----------------------
Depuis le 2026-08-29 une bibliotheque tierce voit ses classes Tailwind
compilees : elle declare une racine dans ``bretzel.scan_roots``. Mais la
porte du THEME restait fermee ::

    Theme(components={"gauge": {...}})
    # ThemeError: aucun composant n'a cette cle de theme

``_validate_theme`` jugeait contre ``theme_vocabulary()``, qui balaie la
surface ``ui.*`` du **framework** uniquement. L'app qui installait un
paquet ne pouvait donc pas surcharger ses slots — il lui restait
``classes=`` au point d'appel, repete partout, sans cascade ni coherence
de theme sombre. C'est la difference entre un composant theme et du HTML
copie, et c'est la moitie qui manquait pour qu'un ecosysteme vaille mieux
qu'un copier-coller.

Ce que ce fichier eprouve
--------------------------
Un vrai paquet, fabrique a la volee : un module avec un ``Component`` qui
porte un ``THEME_KEY``, publie par un point d'entree ``bretzel.components``
fabrique. Puis les trois verdicts qui comptent — la cle est acceptee, une
cle inconnue est TOUJOURS refusee, et une collision avec le framework
leve en nommant les deux cotes.

⚠️ Le validateur n'est pas assoupli, et c'est le point : refuser une cle
inconnue a deja attrape de vraies fautes de frappe. Ce qui lui manquait,
c'est de SAVOIR que le paquet existe.
"""

from __future__ import annotations

import sys
import types
from typing import Any, ClassVar

import pytest

from bretzel.components.base import Component
from bretzel.introspect.packages import (
    ThemeKeyCollision,
    third_party_components,
    third_party_theme_vocabulary,
)


class _FauxPoint:
    """Ce que ``metadata.entry_points`` rend : un nom et un module."""

    def __init__(self, name: str, module: str) -> None:
        self.name = name
        self.module = module


def _publier(monkeypatch: pytest.MonkeyPatch, *modules: str) -> None:
    """Fait comme si ces modules etaient declares par des paquets installes."""
    from bretzel.introspect import packages

    points = [_FauxPoint(m.replace("_", "-"), m) for m in modules]
    monkeypatch.setattr(
        packages.metadata, "entry_points", lambda group=None: points
    )
    third_party_components.cache_clear()
    monkeypatch.setattr(
        packages, "third_party_components", third_party_components, raising=False
    )


@pytest.fixture
def paquet_tiers(monkeypatch: pytest.MonkeyPatch):
    """Un vrai module, avec un vrai ``Component``, publie comme un paquet.

    Pas un objet factice : la decouverte lit ``THEME_KEY`` et ``THEME``
    sur une sous-classe reelle, donc un faux la ferait passer pour bonne
    sans rien prouver.
    """
    module = types.ModuleType("faux_paquet_jauge")

    class Gauge(Component):
        THEME: ClassVar[dict[str, Any]] = {
            "slots": {"root": "block", "fill": "bg-primary"},
            "sizes": {"sm": "h-1", "md": "h-2"},
        }
        THEME_KEY: ClassVar[str] = "gauge"
        DEFAULT_TAG: ClassVar[str] = "div"

    Gauge.__module__ = "faux_paquet_jauge"
    module.Gauge = Gauge
    monkeypatch.setitem(sys.modules, "faux_paquet_jauge", module)
    _publier(monkeypatch, "faux_paquet_jauge")
    yield Gauge
    third_party_components.cache_clear()


def test_the_package_is_discovered(paquet_tiers) -> None:
    """Plancher : sans lui, les verdicts suivants porteraient sur zero
    composant et seraient verts pour rien."""
    trouves = third_party_components()
    assert paquet_tiers in trouves, (
        f"le composant du paquet n'est pas decouvert. Vu : {trouves}"
    )


def test_its_slots_enter_the_vocabulary(paquet_tiers) -> None:
    vocabulaire = third_party_theme_vocabulary()
    assert "gauge" in vocabulaire, (
        f"la cle du paquet n'entre pas dans le vocabulaire : "
        f"{sorted(vocabulaire)}"
    )
    assert vocabulaire["gauge"]["slots"] == frozenset({"root", "fill"})
    assert vocabulaire["gauge"]["sizes"] == frozenset({"sm", "md"})


def test_the_app_can_now_override_them(paquet_tiers) -> None:
    """Le but de tout ce fichier : l'app SURCHARGE la bibliotheque."""
    from bretzel.introspect import theme_vocabulary
    from bretzel.theme.slots import validate_component_overrides

    vocabulaire = {**theme_vocabulary(), **third_party_theme_vocabulary()}
    # Ne leve pas — c'est l'assertion.
    validate_component_overrides(
        {"gauge": {"slots": {"fill": "bg-success"}}}, vocabulaire
    )


def test_an_unknown_key_is_still_refused(paquet_tiers) -> None:
    """Le versant LICITE du validateur, qui n'est PAS assoupli.

    Sans lui, « le tiers passe » serait indistinguable de « on ne juge
    plus rien » — et refuser une cle inconnue a deja attrape de vraies
    fautes de frappe.
    """
    from bretzel.introspect import theme_vocabulary
    from bretzel.theme.slots import validate_component_overrides

    vocabulaire = {**theme_vocabulary(), **third_party_theme_vocabulary()}
    with pytest.raises(Exception) as leve:
        validate_component_overrides({"jauge": {"slots": {"x": "y"}}}, vocabulaire)
    assert "jauge" in str(leve.value)


def test_a_key_that_collides_with_the_framework_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``"card"`` est pris. Un paquet ne peut pas le reprendre.

    Sinon un ``Theme(components={"card": …})`` devient ambigu : l'app
    croit styler l'un et style l'autre.
    """
    module = types.ModuleType("faux_paquet_carte")

    class Carte(Component):
        THEME: ClassVar[dict[str, Any]] = {"slots": {"root": "block"}}
        THEME_KEY: ClassVar[str] = "card"
        DEFAULT_TAG: ClassVar[str] = "div"

    Carte.__module__ = "faux_paquet_carte"
    module.Carte = Carte
    monkeypatch.setitem(sys.modules, "faux_paquet_carte", module)
    _publier(monkeypatch, "faux_paquet_carte")

    with pytest.raises(ThemeKeyCollision) as leve:
        third_party_theme_vocabulary()
    message = str(leve.value)
    assert "card" in message, "le message doit nommer la cle en conflit"
    assert "faux_paquet_carte" in message, "et le paquet fautif"
    assert "faux-paquet-carte-card" in message, (
        "et proposer une cle prefixee — un message qui refuse sans dire "
        "quoi ecrire a la place coute une recherche a chaque fois"
    )
    third_party_components.cache_clear()


def test_a_reexported_framework_class_is_not_claimed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Un ``from bretzel import ui`` en tete de module ne publie RIEN.

    Sans ce garde-fou, tout paquet qui importe le framework — donc tous —
    reclamerait le catalogue entier et ferait lever la collision au
    premier demarrage.
    """
    from bretzel.components.feedback.avatar.avatar import Avatar

    module = types.ModuleType("faux_paquet_vide")
    module.Avatar = Avatar  # reexport, pas une publication
    monkeypatch.setitem(sys.modules, "faux_paquet_vide", module)
    _publier(monkeypatch, "faux_paquet_vide")

    assert third_party_components() == (), (
        "une classe du framework reexportee ne doit pas compter comme "
        "publiee par le paquet"
    )
    third_party_components.cache_clear()


def test_a_broken_entry_point_warns_but_does_not_crash(
    monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """L'app n'est pas responsable des metadonnees d'un tiers.

    Mais ca ne passe pas en silence : ses composants resteraient
    inthematisables et rien d'autre ne le dirait. Meme arbitrage que
    ``discovered_source_roots``, dont c'est le jumeau.
    """
    _publier(monkeypatch, "paquet_qui_n_existe_pas_du_tout")
    assert third_party_components() == ()
    sortie = capsys.readouterr().out
    assert "WARN" in sortie and "paquet_qui_n_existe_pas_du_tout" in sortie
    third_party_components.cache_clear()


def test_the_app_actually_starts_with_that_override(paquet_tiers) -> None:
    """Bout en bout : l'app DEMARRE, ce qui est le seul verdict qui compte.

    ⚠️ Les tests ci-dessus appellent ``validate_component_overrides``
    directement avec le dictionnaire fusionne — ils ne prouvent donc RIEN
    du cablage dans ``_validate_theme``. Retirer la fusion du demarrage
    les laisserait tous verts. Celui-ci passe par le vrai chemin.
    """
    from starlette.testclient import TestClient

    from bretzel import Bretzel, page, ui
    from bretzel.theme import Theme

    app = Bretzel(
        secret_key="g" * 32,
        mode="dev",
        theme=Theme(components={"gauge": {"slots": {"fill": "bg-success"}}}),
    )

    @page("/")
    def home() -> None:
        ui.text("ok")

    app.include(home)

    # ``TestClient`` en gestionnaire de contexte JOUE le cycle de vie,
    # donc ``_validate_theme``. Sans le ``with``, rien ne demarre et le
    # test serait vide.
    with TestClient(app) as client:
        assert client.get("/").status_code == 200
