"""Gate — une page de composant porte `build_preview` et `control`.

Ce qu'elle garde
----------------
Le § 6 du gabarit de playground prescrit deux fonctions au niveau
module : `build_preview(state)`, qui concentre la traduction des props
en kwargs, et `control(label)`, la cellule de contrôle étiquetée. Elles
ne sont pas décoratives : la première EST ce que les autres gates lisent
pour savoir qu'une prop est démontrée (`test_playground_demos_the_api`
retombe sur les `kwargs["…"]` qu'elle construit), la seconde est ce qui
rend un contrôle manipulable plutôt qu'affiché.

L'audit du 2026-09-06 en comptait **six sans** — audio, datatable, html,
iframe, image, video. Les six ont depuis rattrapé ; rien ne les y garde.

Le point qui manquait à la règle : sa PORTÉE
--------------------------------------------
Le § 6 disait « allowed at module scope » sans dire à quelles pages il
s'adresse, et le corpus en contient neuf qui n'ont rien à prévisualiser :

- l'infrastructure du playground (`home`, `app_map`, `inspection`,
  `meta`, `theme_studio`) — ce ne sont pas des pages de composant ;
- les pages de FAMILLE (`stack`, `dnd`, `screen`) — elles montrent
  plusieurs composants en relation, pas un composant et ses props ;
- `notification`, qui est un helper qu'on DÉCLENCHE et non un composant
  qu'on rend : sa propre docstring l'écrit (« fire-and-forget helper »).
  Il n'y a rien à prévisualiser, seulement à tirer.

D'où le critère, qui se DÉRIVE au lieu de se lister : une page dont le
nom est celui d'un composant public est une page de composant. Les neuf
autres sortent du balayage par construction, sans liste d'exemptions à
tenir à jour — donc sans le risque qu'une exemption périmée y cache la
page suivante.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.consistency._discovery import public_component_classes, ui_name_of

FEATURES = Path(__file__).resolve().parents[2] / "examples" / "playground" / "features"

#: Combien de pages de composant le balayage doit trouver. 70 mesurées
#: le 2026-09-07. Ancré sur la DÉCOUVERTE : une gate qui ne compterait
#: que ses fautes resterait verte en ne lisant plus rien.
_PAGES_FLOOR = 60


def _sources() -> dict[str, str]:
    """``nom de page → source``, fichier unique ou dossier réuni."""
    out: dict[str, str] = {}
    for f in sorted(FEATURES.glob("*.py")):
        if not f.name.startswith("__"):
            out[f.stem] = f.read_text(encoding="utf-8-sig")
    for d in sorted(p for p in FEATURES.iterdir() if p.is_dir()):
        if d.name.startswith("__"):
            continue
        out[d.name] = "\n".join(
            p.read_text(encoding="utf-8-sig") for p in sorted(d.rglob("*.py"))
        )
    return out


_SOURCES = _sources()
_CATALOGUE = {ui_name_of(cls) for cls in public_component_classes()}
_PAGES = sorted(nom for nom in _SOURCES if nom in _CATALOGUE)


def test_the_sweep_finds_the_component_pages() -> None:
    assert len(_PAGES) >= _PAGES_FLOOR, (
        f"le balayage ne voit plus que {len(_PAGES)} pages de composant "
        f"sous {FEATURES} (70 mesurées le 2026-09-07). Vérifie le chemin, "
        f"ou que les noms de page suivent encore les noms ``ui.*`` — sans "
        f"quoi « toutes portent leurs helpers » ne veut plus rien dire."
    )


@pytest.mark.parametrize("page", _PAGES)
def test_a_component_page_defines_build_preview(page: str) -> None:
    assert re.search(r"^def build_preview\(", _SOURCES[page], re.M), (
        f"la page ``{page}`` ne définit pas ``build_preview(state)`` "
        f"(gabarit § 6).\n"
        f"  Ce n'est pas une convention d'écriture : c'est la fonction "
        f"qui traduit les props en kwargs, donc celle que "
        f"``test_playground_demos_the_api`` lit pour savoir qu'une prop "
        f"est démontrée. Sans elle, les props de ce composant sortent "
        f"du contrôle de l'autre gate sans que personne ne le voie."
    )


@pytest.mark.parametrize("page", _PAGES)
def test_a_component_page_uses_control(page: str) -> None:
    assert "with control(" in _SOURCES[page], (
        f"la page ``{page}`` n'utilise pas ``control(label)`` (gabarit "
        f"§ 6). Un contrôle sans sa cellule étiquetée s'AFFICHE au lieu "
        f"de se manipuler, et le playground cesse d'être un banc d'essai "
        f"pour devenir une galerie."
    )


def test_the_detector_catches_a_page_without_its_helpers() -> None:
    """Preuve de morsure — les deux versants, sur des sources fabriquées.

    Une gate qui ne rougit que sur un cas fabriqué pourrait rougir sur
    tout ; une gate verte sur le corpus pourrait ne rien détecter. On
    donne donc au détecteur la page fautive ET la page saine.
    """
    fautive = "def page():\n    ui.button('x')\n"
    saine = (
        "def build_preview(state):\n    return ui.button('x')\n\n"
        "def page():\n    with control('variant'):\n        pass\n"
    )
    assert not re.search(r"^def build_preview\(", fautive, re.M)
    assert "with control(" not in fautive
    assert re.search(r"^def build_preview\(", saine, re.M), (
        "le détecteur ne reconnaît plus une page SAINE — un faux positif "
        "sur 70 pages ferait désarmer la gate le jour même."
    )
    assert "with control(" in saine
