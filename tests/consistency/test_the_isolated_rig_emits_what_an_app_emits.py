"""Le banc isolé émet la MÊME action qu'une vraie app.

Le fait gardé
--------------
``render_isolated`` est le rig de rendu de tout le dépôt : les tests
unitaires s'en servent, et plusieurs probes navigateur bâtissent leur
page avec lui plutôt qu'avec un serveur. Sa docstring promet qu'à
l'intérieur, tout « behaves like in production ».

Cette promesse a été fausse pendant des mois sur le point le plus
coûteux : ``_StubApp`` n'avait pas de ``config``, donc
``RenderContext._action_key`` rendait ``b""``, donc ``register_action``
rendait une signature vide, donc les ``hx-post`` sortaient **sans**
``data-bz-sig``. Sans conséquence tant que personne ne regardait.

Le 2026-08-27, ``ad3b7f33`` a rendu la conséquence maximale : le bridge
REFUSE désormais tout POST dont l'élément n'a pas de porteur de
signature — une action détachée par un morph partait sinon nue, se
faisait refuser par le serveur, et rechargeait la page entière. Du jour
au lendemain, tout montage navigateur bâti sur ce rig a produit des
boutons qu'aucun clic ne pouvait faire partir.

Trois rouges, deux jours, et aucun n'a désigné la cause :
``test_inert_controls`` accusait le garde d'inertie,
``probe_overlay_dual_event`` accusait le porteur d'``on_close``,
``probe_table`` accusait la ligne cliquable. Les trois mesuraient la
même absence, et le seul correctif a été de donner une clé au rig.

Ce que la gate compare
-----------------------
Le même composant rendu des DEUX façons — le rig isolé et une vraie app
servie par ``TestClient`` — et l'égalité porte sur les **noms**
d'attributs de l'élément qui porte l'action, jamais sur leurs valeurs :
une signature et un horodatage diffèrent forcément d'un rendu à l'autre.
C'est ce qui rend la comparaison possible, et c'est aussi sa limite —
un rig qui signerait avec la mauvaise clé passerait ici (le serveur, lui,
le refuserait).

Ce n'est pas une gate sur ``data-bz-sig`` : c'est une gate sur l'écart
ENTRE LES DEUX CHEMINS. Le prochain attribut que la production ajoutera
à une action et que le rig ne saura pas produire rougira ici, sans que
personne ait à y penser.
"""

from __future__ import annotations

import re
import sys
import types

from fastapi.testclient import TestClient

from bretzel import Bretzel, page, ui
from bretzel.components.base.testing import render_isolated
from bretzel.render import serialize_html

#: Preuve de morsure : le contrôle NÉGATIF vit dans
#: ``test_the_detector_still_bites``.
MUTATION_PROOF = "test_the_detector_still_bites"

_SECRET = "x" * 32
#: Marqueur porté par le bouton sous test, pour le retrouver dans un
#: document entier sans dépendre de l'ordre des balises.
_MARK = "zz-rig-probe"


def action_handler() -> None:
    """Handler AU NIVEAU MODULE — une lambda n'est pas adressable."""


def _tag_carrying_the_action(html: str) -> str | None:
    """La balise ouvrante qui porte ``hx-post``, marquée par ``_MARK``."""
    for match in re.finditer(r"<[a-zA-Z][^>]*>", html):
        tag = match.group(0)
        if _MARK in tag and "hx-post" in tag:
            return tag
    return None


def attr_names(tag: str) -> set[str]:
    """Les NOMS d'attributs d'une balise ouvrante.

    Extrait plutôt qu'inline pour être MUTABLE : c'est ce détecteur que
    ``test_the_detector_still_bites`` nourrit de balises fabriquées.
    """
    return set(re.findall(r"([a-zA-Z_:@\-\.]+)=", tag))


def _from_the_isolated_rig() -> str:
    with render_isolated():
        box = ui.vstack()
        with box:
            ui.button("Go", on_click=action_handler, attrs={"data-mark": _MARK})
        return serialize_html(box)


def _from_a_real_app() -> str:
    """Le même bouton, mais servi par une app complète.

    Module JETABLE plutôt qu'un module de test : ``app.include`` balaie
    les attributs d'un module, donc enregistrer la page ici accrocherait
    aussi tout ce que ce fichier définit par ailleurs.
    """
    app = Bretzel(secret_key=_SECRET, mode="dev")
    module = types.ModuleType("_rig_probe_app")

    @page("/")
    def home() -> None:
        ui.button("Go", on_click=action_handler, attrs={"data-mark": _MARK})

    module.home = home
    sys.modules["_rig_probe_app"] = module
    try:
        app.include(module)
        with TestClient(app) as client:
            return client.get("/").text
    finally:
        sys.modules.pop("_rig_probe_app", None)


def test_the_sweep_is_not_vacuous() -> None:
    """Plancher ancré sur la DÉCOUVERTE : les deux rendus existent.

    Le pire vert serait de comparer deux ``None`` — un bouton qui ne
    porte plus le marqueur, une page qui ne rend plus. On exige donc que
    les DEUX chemins produisent une balise d'action, et qu'elle porte de
    quoi comparer.
    """
    for label, html in (
        ("rig isolé", _from_the_isolated_rig()),
        ("vraie app", _from_a_real_app()),
    ):
        tag = _tag_carrying_the_action(html)
        assert tag is not None, (
            f"{label} : aucune balise ne porte à la fois le marqueur et "
            f"``hx-post``. La comparaison ci-dessous n'aurait rien à lire."
        )
        names = attr_names(tag)
        assert "hx-post" in names and len(names) >= 5, (
            f"{label} : {sorted(names)} — trop peu d'attributs pour que "
            f"l'égalité veuille dire quelque chose."
        )


def test_both_paths_stamp_the_same_attributes() -> None:
    rig = attr_names(_tag_carrying_the_action(_from_the_isolated_rig()) or "")
    app = attr_names(_tag_carrying_the_action(_from_a_real_app()) or "")

    missing = sorted(app - rig)
    extra = sorted(rig - app)
    assert not missing and not extra, (
        "Le banc isolé et une vraie app n'émettent pas la même action.\n"
        f"  absent du rig   : {missing}\n"
        f"  absent de l'app : {extra}\n\n"
        "Un montage navigateur bâti sur ``render_isolated`` rend donc un "
        "élément que la production ne produirait jamais. Le cas vécu : "
        "``data-bz-sig`` manquait, le bridge refusait le POST (ad3b7f33), "
        "et TROIS bancs sont restés rouges deux jours en accusant chacun "
        "un composant différent."
    )


def test_the_detector_still_bites() -> None:
    """Les deux versants, sur des balises FABRIQUÉES."""
    signed = '<button data-mark="zz" hx-post="/a" data-bz-sig="s" data-bz-ts="1">'
    unsigned = '<button data-mark="zz" hx-post="/a" data-bz-ts="1">'

    # ── Versant ILLICITE : l'écart exact qui a coûté trois rouges ─────
    assert attr_names(signed) - attr_names(unsigned) == {"data-bz-sig"}

    # ── Versant LICITE : deux rendus du même chemin sont égaux ────────
    # Les VALEURS diffèrent (signature, horodatage) et ne doivent pas
    # faire rougir — c'est pour ça que la gate compare des noms.
    other = '<button data-mark="zz" hx-post="/a" data-bz-sig="AUTRE" data-bz-ts="99">'
    assert attr_names(signed) == attr_names(other)

    # ── Et le sélecteur ne ramasse pas n'importe quelle balise ────────
    assert _tag_carrying_the_action("<button hx-post='/a'>") is None, (
        "une balise sans le marqueur est prise pour le sujet"
    )
    assert _tag_carrying_the_action(f'<div data-mark="{_MARK}">') is None, (
        "une balise marquée mais SANS action est prise pour le sujet"
    )
