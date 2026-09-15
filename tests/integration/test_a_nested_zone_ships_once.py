"""Gate — une zone imbriquée dans une autre n'expédie qu'UN fragment.

Le défaut qu'elle ferme (2026-08-23, mesuré sur banc)
------------------------------------------------------
``enqueue_deps`` empile **toute** zone dont les ``deps`` contiennent
l'état changé. Deux zones imbriquées qui lisent le même état partaient
donc toutes les deux : le parent rendait son sous-arbre — enfant
compris — et l'enfant rendait le sien une seconde fois, en fragment OOB.
Le morph appliquait les deux, le résultat était correct, et seul le poids
mentait.

=================  ==================  ==================
forme              avant               après
=================  ==================  ==================
2 zones, 200 li.   19 692 o, ``x2``    9 906 o, ``x1``
3 zones, 200 li.   29 720 o, ``x3``    10 027 o, ``x1``
=================  ==================  ==================

C'est O(profondeur) en octets, ça grossit avec la donnée, et **rien ne
prévient** — c'est ce qui l'avait laissé vivre.

Pourquoi la découverte se fait au DRAIN, et pas plus tôt
---------------------------------------------------------
L'imbrication n'est pas une déclaration : ``enqueue_deps`` ne voit que
des ``deps``, et « le parent appelle l'enfant » est un fait de RENDU —
conditionnel de surcroît (cf. ``TestTheLicitSide``). Le seul moment où
l'information existe est celui où l'arbre est construit, c'est-à-dire
dans ``render_partial``. Elle n'y coûte rien : l'arbre est déjà là.

C'est d'ailleurs la question que ``datatable._check_refresh_zone`` pose
déjà (``parent_stack`` x ``zone_ids_watching`` → « un ancêtre va-t-il me
re-rendre ? »), à un autre moment. Aucun concept neuf.

Les DEUX ordres, parce que l'ordre choisit la branche
-------------------------------------------------------
La file suit l'ordre de décoration (``_ZONES_BY_DEP`` se remplit à
l'import). Selon que l'enfant est décoré avant ou après son parent, le
code passe par deux chemins différents : **sauter** une zone déjà
couverte, ou **retirer** un fragment déjà construit. Un seul ordre testé
laisserait la moitié du correctif sans preuve.

La preuve dans les deux sens
------------------------------
Le détecteur est ``partials._zone_ids_inside``. S'il ne trouvait plus
rien, ``TestTheNesting`` rougit ; s'il couvrait trop, c'est
``TestTheLicitSide`` qui rougit — deux zones SŒURS doivent toujours
expédier deux fragments, et une imbrication qui n'a pas eu lieu cette
fois-ci doit rendre son enfant à part. Mutation vérifiée dans les deux
sens le 2026-08-23.

« Contenu » veut dire dans le DOM VIVANT, pas dans le SSR
-----------------------------------------------------------
Un panneau d'overlay ancré part sous ``<body>`` à l'init
(``base/_wiring.teleport_to_body``). Une zone qui vit dedans est sous son
parent dans l'arbre rendu et ailleurs dans la page : morpher le parent ne
l'atteindrait jamais. Le parcours s'arrête donc sous un ``bz-teleport``,
et ``test_a_teleported_panel_keeps_its_own_fragment`` le mesure. C'est
une déclaration lue dans l'arbre, pas une devinette sur la mise en page.

⚠️ Ce qu'elle n'affirme PAS : rien sur un descendant caché dans un nœud
:class:`~bretzel.core.tree.Html` (du balisage brut), que le parcours ne
voit pas — aucun chemin ne produit ça, une zone rend un ``Element``. Et
rien sur un nœud ``hx-preserve`` qui porterait une zone : le morph de
l'ancêtre la figerait, mais la seule coquille ``hx-preserve`` du dépôt
(la barre d'outils de ``ui.datatable``) est vide par construction. Les
deux sont déclarés ici plutôt que gardés pour un cas qui n'existe pas.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from bretzel import Bretzel, page, refreshable, ui
from bretzel.server.handlers import encode_action_id, sign_action
from bretzel.state import AppState, field

_SECRET = "n" * 32
_LIGNES = 40

_app = Bretzel(secret_key=_SECRET, mode="dev")


# ── Les familles. Chacune son état, pour qu'aucun test n'en bouge un
#    autre : une action ne re-rend que les zones de SA famille.
class EnfantDabord(AppState):
    n: int = field(default=0)


class ParentDabord(AppState):
    n: int = field(default=0)


class TroisNiveaux(AppState):
    n: int = field(default=0)


class Soeurs(AppState):
    n: int = field(default=0)


class Conditionnelle(AppState):
    n: int = field(default=0)


class Teleportee(AppState):
    n: int = field(default=0)


def _corps(marque: str, valeur: int) -> None:
    """Du volume, pour que le doublement se voie en octets."""
    for i in range(_LIGNES):
        ui.text(f"{marque}-{i} n={valeur}")


# ── Famille 1 : l'ENFANT est décoré en premier → il passe en premier
#    dans la file, et le correctif doit RETIRER son fragment.
@refreshable(deps=[EnfantDabord])
def ed_enfant() -> None:
    _corps("ED-ENFANT", EnfantDabord().n)


@refreshable(deps=[EnfantDabord])
def ed_parent() -> None:
    ui.text(f"ED-PARENT n={EnfantDabord().n}")
    ed_enfant()


# ── Famille 2 : le PARENT est décoré en premier → l'enfant doit être
#    SAUTÉ, donc jamais rendu.
@refreshable(deps=[ParentDabord])
def pd_parent() -> None:
    ui.text(f"PD-PARENT n={ParentDabord().n}")
    pd_enfant()


@refreshable(deps=[ParentDabord])
def pd_enfant() -> None:
    _corps("PD-ENFANT", ParentDabord().n)


# ── Famille 3 : trois niveaux.
@refreshable(deps=[TroisNiveaux])
def tn_fond() -> None:
    _corps("TN-FOND", TroisNiveaux().n)


@refreshable(deps=[TroisNiveaux])
def tn_milieu() -> None:
    ui.text(f"TN-MILIEU n={TroisNiveaux().n}")
    tn_fond()


@refreshable(deps=[TroisNiveaux])
def tn_dehors() -> None:
    ui.text(f"TN-DEHORS n={TroisNiveaux().n}")
    tn_milieu()


# ── Famille 4 : deux SŒURS — le contrôle positif.
@refreshable(deps=[Soeurs])
def so_gauche() -> None:
    ui.text(f"SO-GAUCHE n={Soeurs().n}")


@refreshable(deps=[Soeurs])
def so_droite() -> None:
    ui.text(f"SO-DROITE n={Soeurs().n}")


# ── Famille 5 : l'imbrication est CONDITIONNELLE, et n'a pas lieu.
@refreshable(deps=[Conditionnelle])
def co_enfant() -> None:
    ui.text(f"CO-ENFANT n={Conditionnelle().n}")


@refreshable(deps=[Conditionnelle])
def co_parent() -> None:
    ui.text(f"CO-PARENT n={Conditionnelle().n}")
    if Conditionnelle().n < 0:  # jamais — le parent ne porte pas l'enfant
        co_enfant()


# ── Famille 6 : la zone vit dans un panneau TÉLÉPORTÉ. Dans le SSR elle
#    est sous le parent ; dans le DOM vivant elle est sous ``<body>``.
@refreshable(deps=[Teleportee])
def te_panneau() -> None:
    ui.text(f"TE-PANNEAU n={Teleportee().n}")


@refreshable(deps=[Teleportee])
def te_parent() -> None:
    ui.text(f"TE-PARENT n={Teleportee().n}")
    with ui.popover(trigger=ui.button("ouvrir")):
        te_panneau()


# Idempotents : chaque test peut tourner dans n'importe quel ordre, et
# ``n=1`` reste la preuve que le fragment est FRAIS (la page rend ``0``).
def bump_ed() -> None:
    EnfantDabord().n = 1


def bump_pd() -> None:
    ParentDabord().n = 1


def bump_tn() -> None:
    TroisNiveaux().n = 1


def bump_so() -> None:
    Soeurs().n = 1


def bump_co() -> None:
    Conditionnelle().n = 1


def bump_te() -> None:
    Teleportee().n = 1


@page("/")
def home() -> None:
    ed_parent()
    pd_parent()
    tn_dehors()
    so_gauche()
    so_droite()
    co_parent()
    co_enfant()
    te_parent()


_app.include(home)


def _post(handler) -> str:
    action_id = encode_action_id(handler)
    sig = sign_action(_app.config._action_key, action_id, "")
    with TestClient(_app) as client:
        client.get("/")  # établit la session et les bz-id
        response = client.post(
            f"/_bretzel/action/{action_id}",
            headers={"X-Bz-Sig": sig},
            data={"_args": ""},
        )
    assert response.status_code == 200, response.text
    return response.text


# ───────────────────────────────────────────────────────────────────────
# ① Le plancher — sans lui, « une seule fois » serait vrai de zéro
# ───────────────────────────────────────────────────────────────────────


def test_the_probe_is_not_vacuous() -> None:
    body = _post(bump_ed)
    assert "hx-swap-oob" in body, "aucun fragment n'est revenu de l'action"
    assert "ED-PARENT n=1" in body, (
        "le parent ne revient pas RAFRAÎCHI : le harnais ne mesure rien, "
        "et « un seul fragment » serait vrai d'une réponse vide."
    )
    assert "ED-ENFANT-0 n=1" in body, (
        "le contenu de l'enfant n'est pas dans le fragment du parent — "
        "or c'est la RAISON pour laquelle on peut jeter le sien."
    )


# ───────────────────────────────────────────────────────────────────────
# ② L'interdiction — dans les deux ordres de file, et en profondeur
# ───────────────────────────────────────────────────────────────────────


class TestTheNesting:
    @pytest.mark.parametrize(
        ("handler", "marque", "ordre"),
        [
            (bump_ed, "ED-ENFANT", "enfant décoré en premier"),
            (bump_pd, "PD-ENFANT", "parent décoré en premier"),
        ],
    )
    def test_a_nested_zone_ships_once(self, handler, marque, ordre) -> None:
        body = _post(handler)
        assert body.count(f"{marque}-0 n=") == 1, (
            f"({ordre}) le contenu de l'enfant part DEUX fois : le parent "
            f"l'a déjà rendu dans son sous-arbre, et son propre fragment "
            f"OOB le répète. `render_partial` doit retirer de la file "
            f"toute zone qu'un fragment déjà émis contient."
        )
        assert body.count("hx-swap-oob") == 1, (
            f"({ordre}) deux fragments pour un seul sous-arbre."
        )

    def test_three_levels_ship_one_fragment(self) -> None:
        body = _post(bump_tn)
        assert body.count("TN-FOND-0 n=") == 1, (
            "à trois niveaux le fond part une fois par ancêtre — le "
            "recouvrement doit être TRANSITIF, pas seulement de parent à "
            "enfant direct."
        )
        assert body.count("hx-swap-oob") == 1
        for marque in ("TN-DEHORS", "TN-MILIEU", "TN-FOND-0"):
            assert f"{marque} n=1" in body, (
                f"{marque} a disparu de la réponse : on a jeté un fragment "
                f"sans que personne ne porte son contenu."
            )


# ───────────────────────────────────────────────────────────────────────
# ③ Le versant LICITE — ce qui doit CONTINUER de partir en double
# ───────────────────────────────────────────────────────────────────────


class TestTheLicitSide:
    """Sans lui, un détecteur qui couvre TOUT resterait vert.

    C'est le versant qui a trouvé les deux seuls bugs de gate de ce dépôt
    (cf. ``gates.md``) : prouver qu'une gate rougit sur un cas fabriqué
    ne dit rien de son taux de faux positifs sur le corpus réel.
    """

    def test_two_sibling_zones_still_ship_twice(self) -> None:
        body = _post(bump_so)
        assert body.count("hx-swap-oob") == 2, (
            "deux zones SŒURS sur le même état ne sont pas imbriquées : "
            "chacune doit avoir son fragment. Une seule ici veut dire que "
            "le recouvrement confond « dans la même réponse » et « dans le "
            "même sous-arbre »."
        )
        assert "SO-GAUCHE n=1" in body and "SO-DROITE n=1" in body

    def test_a_nesting_that_did_not_happen_still_ships_its_child(self) -> None:
        """L'imbrication est un fait de rendu, pas une déclaration."""
        body = _post(bump_co)
        assert "CO-ENFANT n=1" in body, (
            "l'enfant a été jeté alors que le parent ne l'a PAS rendu "
            "cette fois-ci : sa zone ne sera jamais mise à jour. Le "
            "recouvrement doit se lire dans l'arbre PRODUIT, pas dans une "
            "table statique de qui-contient-qui."
        )
        assert body.count("hx-swap-oob") == 2

    def test_a_teleported_panel_keeps_its_own_fragment(self) -> None:
        """Le SSR l'imbrique, le DOM vivant non.

        Un panneau d'overlay ancré part sous ``<body>``
        (``base/_wiring.teleport_to_body``). Morpher l'ancêtre qui le
        porte dans le SSR n'atteindrait donc jamais la zone qui vit
        dedans — lui retirer son fragment la figerait pour de bon.
        """
        body = _post(bump_te)
        assert "TE-PANNEAU n=1" in body
        assert body.count("hx-swap-oob") == 2, (
            "la zone du panneau a été considérée comme couverte par son "
            "parent : le parcours doit S'ARRÊTER sous un `bz-teleport`, "
            "qui déclare que ce sous-arbre change de place dans le DOM."
        )
