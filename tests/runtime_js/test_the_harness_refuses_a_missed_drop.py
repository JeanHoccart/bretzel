"""Gate : `Window.drag` REFUSE un glisser qui n'atteint pas sa cible.

Ce qu'elle ferme
----------------
Le glisser du harnais vise le centre de la cible, re-vise avant de
lâcher, puis relâche. Rien, dans cette séquence, ne DIT où l'élément a
fini. Quand le visé rate — une zone qui a bougé sous le geste, une cible
qui n'est pas une zone de dépôt — l'élément atterrit ailleurs et le
harnais se tait ; le rouge tombe trois lignes plus bas, sur un constat
de l'APP, et le diagnostic part dans la mauvaise direction.

C'est arrivé pour de vrai sur ``examples/messagerie`` : le message
atterrissait dans « Envoyés » pendant que le probe visait « Archives ».
Le probe d'origine portait sa propre vérification, à la main, juste
avant ``mouse.up()`` ; le portage sur le harnais l'a d'abord perdue.
:meth:`bretzel.probe.Window._assert_landed` la rend générale, et cette
gate la tient.

Ce que la sonde ne fait PAS, et pourquoi
-----------------------------------------
Aucun ``on_move``, aucun état. Ce qui est mesuré ici est le GESTE, pas
ce qu'un serveur en fait : le moteur reparente le nœud pendant le
glissement, donc l'arbre dit déjà où l'élément a atterri au moment de
lâcher. Brancher un handler ferait dépendre la gate du chemin d'écriture
d'une app, qui a ses propres modes d'échec et qui est couvert ailleurs
(``test_dnd_end_to_end.py``).

Les deux sens
-------------
Le versant ILLICITE seul ne dirait rien : une vérification qui refuse
TOUT ferait aussi rougir les bons gestes. On mesure donc les deux — un
dépôt légitime passe sans lever et pose l'élément dans la zone visée, un
dépôt visé à côté lève en nommant la cible ET la zone réelle.

Run : ``py -m pytest tests/runtime_js/test_the_harness_refuses_a_missed_drop.py -q -m browser``
"""

from __future__ import annotations

import pytest

from bretzel import Bretzel, page, ui
from bretzel.probe import DropMissedError, probe

pytestmark = pytest.mark.browser

GROUPE = "fiches"


def _build_probe_app() -> Bretzel:
    app = Bretzel(secret_key="s" * 32, mode="dev")

    @page("/")
    def plan() -> None:
        # Un leurre : joignable, visible, et surtout PAS une zone de
        # dépôt. C'est le versant illicite de la gate — sans lui, prouver
        # que le refus existe demanderait de casser le harnais.
        ui.input(placeholder="leurre", id="leurre")

        with ui.hstack(gap="md", align="stretch"):
            for nom, fiches in (("gauche", ["alpha", "beta"]), ("droite", [])):
                with ui.dropzone(
                    name=nom, accepts=[GROUPE],
                    classes="w-64 h-64 p-2 bg-text/5 rounded-lg",
                ), ui.vstack(gap="sm"):
                    for fiche in ui.drag_each(fiches, group=GROUPE,
                                              key=lambda f: f):
                        ui.text(fiche, classes="p-3 bg-surface rounded")

    app.include(plan)
    return app


APP = _build_probe_app()

#: Dans quelle zone vit une fiche, à cet instant. Lu dans le DOM et pas
#: dans un état : ce qu'on mesure, c'est le résultat du GESTE.
_WHERE = """
(nom) => {
    const el = [...document.querySelectorAll('[data-bz-draggable]')]
        .find(n => n.innerText.trim() === nom);
    const zone = el && el.closest('[data-bz-dropzone]');
    return zone ? zone.getAttribute('data-bz-dropzone') : null;
}
"""

ALPHA = "[data-bz-draggable]:has-text('alpha')"


def test_a_legitimate_drop_passes_and_lands_in_the_zone() -> None:
    """Le versant LICITE : le harnais ne refuse pas un bon geste."""
    with probe(APP) as p:
        (a,) = p.windows
        a.goto("/")
        p.check("la fiche part de la pile gauche",
                a.page.evaluate(_WHERE, "alpha") == "gauche")

        a.drag(ALPHA, '[data-bz-dropzone="droite"]')

        arrivee = a.page.evaluate(_WHERE, "alpha")
        p.check("elle a atterri dans la zone visée", arrivee == "droite", arrivee)


def test_a_drop_aimed_at_a_non_zone_is_refused_by_the_harness() -> None:
    """Le versant ILLICITE : la cible n'accueille rien, le harnais le DIT.

    Et il le dit AVANT de lâcher, donc avant que l'app n'ait la moindre
    chance de produire un rouge à sa place.
    """
    with probe(APP) as p:
        (a,) = p.windows
        a.goto("/")

        with pytest.raises(DropMissedError) as leve:
            a.drag(ALPHA, "#leurre")

        message = str(leve.value)
        assert "#leurre" in message, (
            "le refus ne nomme pas la cible visée — sans elle, le lecteur "
            f"ne sait pas quel appel corriger :\n{message}"
        )
        # ⚠️ On n'exige PAS une zone en particulier. Le glissement
        # traverse les deux piles avant d'atteindre le leurre et le moteur
        # reparente à chaque survol : la zone nommée est celle où
        # l'élément se trouve AU MOMENT DE LÂCHER, pas celle d'où il
        # vient. Ce qui doit tenir, c'est qu'une zone RÉELLE soit nommée —
        # c'est la moitié utile du diagnostic.
        assert "'gauche'" in message or "'droite'" in message, (
            "le refus ne nomme pas la zone où l'élément se trouve "
            f"vraiment :\n{message}"
        )
        p.check("le harnais a refusé le geste, en le nommant", True)

        # Un glisser abandonné qui laisse le bouton enfoncé, ou le nœud
        # marqué, empoisonne tout ce qui suit dans la même fenêtre.
        p.check("le geste est bien terminé", not a.has("[data-bz-dragging]"))
