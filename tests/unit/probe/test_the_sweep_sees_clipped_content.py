"""Le balayage voit ce qui est COUPÉ, et ne crie pas sur ce qui défile.

Pourquoi ce test existe
------------------------
Le balayage gratuit de :func:`bretzel.probe.probe` mesurait deux formes
de débordement — la page qui sort en largeur, une région qui finit sous
le bord — et pas la troisième : **une boîte qui garde son contenu dans
le DOM et n'en peint qu'une partie**.

C'est le mode d'échec le plus coûteux d'un écran. Il ne lève pas, ne
salit pas la console, ne casse aucune requête, et le HTML sérialisé est
COMPLET : un test de rendu voit le bon document. Seule la mise en page
manque, et on ne peut pas savoir qu'on regarde une information absente.

Mesuré sur ``examples/ecole`` le 2026-09-12 : une case d'emploi du temps
affichait sa classe et rien d'autre — la salle et le lien vers le cahier
coupés net par un ``overflow:hidden`` de thème sur une hauteur imposée
par l'app. Le compte de l'auteur s'est trompé **trois fois de suite**,
parce que la hauteur s'écrit dans l'app, le rembourrage dans un thème de
composant, et que leur somme ne vit nulle part.

Ce que ce fichier prouve, dans les DEUX sens
---------------------------------------------
Le constat tombe sur une boîte coupée, et il se tait sur une boîte qui
DÉFILE — dont le contenu reste atteignable. Le second versant est celui
qui coûte : un constat qui condamne tout débordement condamnerait
``ui.pane``, c'est-à-dire le modèle de défilement de la moitié des apps
du dépôt.

⚠️ On exerce la DÉCISION, pas le navigateur. Le JavaScript qui collecte
les boîtes est mesuré pour de vrai par chaque probe qui tourne ; ici on
lui fabrique sa sortie, ce qui rend le test instantané et déterministe.
"""

from __future__ import annotations

from typing import Any

from bretzel.probe._sweep import _geometry


class _Page:
    """Le seul morceau de ``page`` que ``_geometry`` touche."""

    def __init__(self, geo: dict[str, Any]) -> None:
        self._geo = geo

    def evaluate(self, _js: str) -> dict[str, Any]:
        return self._geo


class _Window:
    def __init__(self, geo: dict[str, Any]) -> None:
        self.name = "f1"
        self.page = _Page(geo)


def _balayer(**geo: Any) -> dict[str, bool]:
    """Les verdicts du balayage géométrique, par nom de constat."""
    base: dict[str, Any] = {
        "overflowX": 0,
        "documentScrolls": False,
        "viewport": [1280, 700],
        "scrollers": [],
        "clipped": [],
    }
    base.update(geo)
    verdicts: dict[str, bool] = {}

    def check(nom: str, ok: Any, _detail: Any = None) -> None:
        verdicts[nom] = bool(ok)

    _geometry(check, _Window(base), "taille-1")
    return verdicts


COUPEE = {
    "tag": "div",
    "cls": "rounded-box overflow-hidden",
    "haut": 62,
    "faut": 80,
    "texte": "4e1 C209 cahier",
}

QUI_DEFILE = {"tag": "div", "cls": "bz-pane", "bottom": 600}


def verdict(verdicts: dict[str, bool], fragment: str) -> bool:
    """Le verdict dont le nom contient ``fragment``."""
    trouves = [v for k, v in verdicts.items() if fragment in k]
    assert len(trouves) == 1, (
        f"{fragment!r} devait nommer UN constat, il en nomme "
        f"{len(trouves)} — le balayage a changé de vocabulaire, et un "
        f"test qui ne trouve plus son constat passe au vert en ne "
        f"mesurant rien."
    )
    return trouves[0]


def test_une_boite_coupee_rougit():
    """Le versant interdit : du contenu peint nulle part."""
    verdicts = _balayer(clipped=[COUPEE])
    assert verdict(verdicts, "rien n'est coupé sans recours") is False


def test_une_boite_qui_defile_ne_rougit_pas():
    """Le versant LICITE, celui qui coûte.

    Une région à défilement déborde par construction — c'est ce que
    ``ui.pane`` fait, et c'est le modèle de document gelé de la moitié
    des apps. Son contenu reste ATTEIGNABLE, donc rien n'est perdu.
    """
    verdicts = _balayer(scrollers=[QUI_DEFILE])
    assert verdict(verdicts, "rien n'est coupé sans recours") is True
    assert verdict(verdicts, "finissent au-dessus du bord") is True


def test_une_page_sans_defaut_est_verte_partout():
    """Le plancher : sans faute fabriquée, aucun constat ne tombe."""
    verdicts = _balayer()
    assert all(verdicts.values()), verdicts
    assert len(verdicts) >= 3, (
        f"seulement {len(verdicts)} constat(s) géométriques — le "
        f"balayage en pose trois ; s'il en pose moins, c'est qu'une "
        f"branche ne s'exécute plus."
    )


def test_le_constat_survit_a_un_document_qui_defile():
    """Le rognage se mesure même quand la page entière défile.

    ⚠️ Les régions, elles, ne sont jugées QUE dans un document gelé :
    une page qui défile rattrape ce qui dépasse. Le rognage n'a pas ce
    recours — il est aussi grave dans les deux modèles, et le constat
    devait donc sortir du ``if``. C'est la faute que ce test garde.
    """
    verdicts = _balayer(documentScrolls=True, clipped=[COUPEE])
    assert verdict(verdicts, "rien n'est coupé sans recours") is False
    assert not [k for k in verdicts if "finissent au-dessus" in k]
