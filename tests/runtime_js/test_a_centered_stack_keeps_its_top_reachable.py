"""Gate navigateur — un ``ui.vstack`` centré qui défile ne coupe pas son haut.

Ce qu'elle garde, et ce que sa jumelle ne pouvait pas
-----------------------------------------------------
``test_a_centered_pane_keeps_its_top_reachable`` garde ``ui.pane``, dont
le thème déclare le défilement ET le centrage au même endroit. Ici, le
défilement est posé au **CALL-SITE** ::

    ui.vstack(align="center", classes="h-full overflow-y-auto")

C'est la forme réelle du dépôt — la recette d'``outlet``, une zone de
dépôt du CRM — et elle était structurellement hors de portée : le
centrage vient de ``flex/theme.py``, qui ne déclare aucun débordement,
donc aucune lecture locale ne pouvait rapprocher les deux moitiés. La
table de ``flex`` porte ``safe`` depuis le 2026-08-29 ; ce fichier est ce
qui le PROUVE au pixel.

Pourquoi au navigateur
----------------------
``tests/consistency/test_a_scrolling_container_never_centers_unsafely``
garde l'orthographe de la classe. Elle ne peut dire ni que
``[align-items:safe_center]`` atteint le DOM, ni que Tailwind compile
cette propriété arbitraire, ni que le moteur l'applique — et c'est
précisément la chaîne qui casse en silence (memory
``project_assembled_tailwind_class_dev_only``).

Le témoin, et ce qu'il prouve
-----------------------------
``/haut`` rend le même contenu en ``align="start"``, qui n'a jamais eu le
défaut. Sans lui, « le haut est atteignable » serait vrai même si la
sonde lisait toujours zéro.

Lourd (uvicorn + Chromium) — à lancer explicitement ::

    py -m pytest tests/runtime_js/test_a_centered_stack_keeps_its_top_reachable.py -q -m browser
"""

from __future__ import annotations

import pytest

from bretzel import Bretzel, page, ui
from tests.audit.harness import audit_server, browser_page

#: De quoi dépasser LARGEMENT un cadre de 600 px. Cf. le piège documenté
#: par la gate jumelle : « ça déborde » ne suffit pas, il faut dépasser
#: le padding, sinon le haut reste atteignable pour la mauvaise raison.
_ENOUGH = 40
_MIN_OVERFLOW = 150

app = Bretzel(secret_key="d" * 32, title="Bretzel · pile centrée", mode="dev")

#: Le défilement est ici, PAS dans le thème — c'est tout le propos.
#:
#: ⚠️ ``flex-1 min-h-0`` et pas ``h-full`` : mesuré, ``h-full`` sur un
#: enfant de conteneur flex ne borne RIEN (hauteur non définie chez le
#: parent), donc la pile grandissait avec son contenu et le débordement
#: valait **0**. La gate serait passée sans rien garder ; c'est le
#: plancher qui l'a refusée. C'est aussi la recette réelle d'``outlet``.
_SCROLLING = "flex-1 min-h-0 overflow-y-auto"

#: ⚠️ Sans lui, le débordement vaut **0** et la gate ne garde rien :
#: un enfant de conteneur flex a ``flex-shrink: 1``, donc la carte
#: se comprimait à la hauteur du cadre et c'est SON contenu à elle
#: qui débordait, en silence. ``ui.pane`` pose ``[&>*]:shrink-0``
#: sur ses enfants pour exactement cette raison ; une pile nue ne
#: le fait pas, et c'est au call-site de le dire.
_NO_SHRINK = "shrink-0"


def _tall(marker: str) -> None:
    for i in range(_ENOUGH):
        ui.text(f"Ligne {i + 1}", size="sm", id=f"{marker}_l{i}" if i == 0 else None)


@page("/")
def centre() -> None:
    """Une pile centrée dont le contenu dépasse — le cas gardé."""
    with ui.viewport(direction="col"):
        with ui.vstack(align="center", justify="center", gap="md",
                       classes=_SCROLLING, id="centre"):
            with ui.card(padding="lg", classes=_NO_SHRINK), ui.vstack(gap="md"):
                ui.heading("Le premier élément", level=1, size="xl",
                           id="centre_premier")
                _tall("centre")


@page("/haut")
def haut() -> None:
    """Le TÉMOIN — même contenu, aligné en haut. Il n'a jamais coupé."""
    with ui.viewport(direction="col"):
        with ui.vstack(align="center", justify="start", gap="md",
                       classes=_SCROLLING, id="haut"):
            with ui.card(padding="lg", classes=_NO_SHRINK), ui.vstack(gap="md"):
                ui.heading("Le premier élément", level=1, size="xl",
                           id="haut_premier")
                _tall("haut")


app.include(__name__)

#: Remonte au maximum, puis compare le haut du contenu à celui du cadre.
#: Un écart positif = des pixels que rien ne permet d'atteindre. Lit AUSSI
#: la propriété calculée : la classe peut être posée et ne rien produire
#: si le compilateur Tailwind n'a pas émis la règle.
_REACH = """(marker) => {
  const box = document.getElementById(marker);
  const first = document.getElementById(marker + '_premier');
  box.scrollTop = 0;
  return {
    deborde: box.scrollHeight - box.clientHeight,
    coupe: Math.round(box.getBoundingClientRect().top
                      - first.getBoundingClientRect().top),
    justify: getComputedStyle(box).justifyContent,
    align: getComputedStyle(box).alignItems,
  };
}"""


def _goto(pg, path: str) -> None:
    origin = pg.url.split("/", 3)
    pg.goto(f"{origin[0]}//{origin[2]}{path}")
    pg.wait_for_selector("html.bz-ready", state="attached")
    pg.wait_for_timeout(300)


@pytest.fixture(scope="module")
def live():
    with audit_server(app) as url, browser_page(url, "/") as pg:
        pg.set_viewport_size({"width": 1280, "height": 600})
        pg.wait_for_selector("html.bz-ready", state="attached")
        yield pg


@pytest.mark.browser
def test_the_content_overflows_past_the_padding(live) -> None:
    """Le plancher : sans débordement franc, la gate ne garde rien."""
    _goto(live, "/")
    overflow = live.evaluate(_REACH, "centre")["deborde"]
    assert overflow >= _MIN_OVERFLOW, (
        f"{overflow} px de débordement seulement : en dessous de "
        f"{_MIN_OVERFLOW}, le centrage ne pousse rien hors du cadre et la "
        "gate passerait pour la mauvaise raison. Augmente _ENOUGH."
    )


@pytest.mark.browser
def test_the_browser_really_applies_safe(live) -> None:
    """La classe ne suffit pas — le moteur doit la CALCULER.

    ``[align-items:safe_center]`` est une propriété arbitraire Tailwind.
    Si le compilateur ne l'émet pas, le HTML est identique et le style
    absent : exactement le mode d'échec de la memory
    ``project_assembled_tailwind_class_dev_only``.
    """
    _goto(live, "/")
    seen = live.evaluate(_REACH, "centre")
    assert "safe" in seen["justify"], (
        f"``justify-content`` calculé = {seen['justify']!r} : le mot-clé "
        "``safe`` n'a pas atteint le moteur. La règle Tailwind pour "
        "``[justify-content:safe_center]`` n'a pas été émise."
    )
    assert "safe" in seen["align"], (
        f"``align-items`` calculé = {seen['align']!r} : idem pour "
        "``[align-items:safe_center]``."
    )


@pytest.mark.browser
def test_a_centered_stack_keeps_its_first_element_reachable(live) -> None:
    _goto(live, "/")
    coupe = live.evaluate(_REACH, "centre")["coupe"]
    assert coupe <= 0, (
        f"{coupe} px du haut sont INATTEIGNABLES : même à scrollTop=0, le "
        "premier élément commence au-dessus du cadre. C'est le centrage "
        "flex sans ``safe`` — cf. ``flex/theme.py``."
    )


@pytest.mark.browser
def test_the_witness_never_cut(live) -> None:
    """``align="start"`` n'a jamais eu le défaut — l'instrument le voit."""
    _goto(live, "/haut")
    assert live.evaluate(_REACH, "haut")["coupe"] <= 0
