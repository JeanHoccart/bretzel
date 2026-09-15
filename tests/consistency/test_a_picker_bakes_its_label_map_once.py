"""Gate : un picker n'émet la carte {valeur → libellé} qu'UNE fois.

``Select`` et ``Combobox`` ont besoin, côté client, du libellé d'une
valeur : pour le texte du déclencheur fermé, pour la classe
« placeholder » quand rien n'est pris, et pour l'étiquette de chaque
pastille en mode multi. Chacun de ces trois besoins **inlinait la carte
ENTIÈRE** dans son expression, en plus de celle que le ``bz-data``
portait déjà.

Mesuré le 2026-08-28, sur une liste de 50 options : quatre exemplaires
de la même table dans un seul composant, soit ~11 % du composant. Et le
gabarit de pastille est PARTAGÉ par les deux pickers, donc la faute
était dupliquée aussi.

La forme correcte est une méthode de scope, ``_labelOf(v)``, que chaque
picker résout à sa façon :

- ``Combobox`` balaie ``_options``, dont chaque entrée porte déjà son
  ``label`` — sa carte a donc disparu, pas seulement ses copies ;
- ``Select`` garde ``_labels`` (son ``_options`` ne contient que des
  valeurs), mais une seule fois, dans le ``bz-data``.

⚠️ Ce n'est pas qu'une affaire d'octets. Une carte inlinée dans un
attribut se re-rend avec la zone, alors qu'une carte de scope doit être
**re-semée** — d'où ``_labels`` dans ``_serverSync``. Sans ça, un
refresh qui change les options laisserait le libellé périmé, ce qu'aucun
compteur d'octets ne verrait. C'est pourquoi la gate regarde AUSSI le
marqueur de synchronisation.
"""

from __future__ import annotations

import re

import pytest

from bretzel.components.base import Component
from bretzel.components.base.testing import render_isolated
from bretzel.components.inputs.combobox import Combobox
from bretzel.components.inputs.select import Select
from bretzel.core.serialize import serialize

#: Preuve de morsure : ``test_the_detector_still_bites`` fabrique le
#: doublon et le cas licite, et vérifie que le compteur les sépare.
MUTATION_PROOF = "test_the_detector_still_bites"

#: Des libellés qui NE ressemblent à rien d'autre dans la page : un
#: fragment de la carte doit être reconnaissable sans ambiguïté. Des
#: ``option-0`` se retrouveraient dans ``data-value``, dans le texte, et
#: le compteur mesurerait autre chose que ce qu'il croit.
OPTIONS = [(f"v{i}", f"Zqx{i}Libelle") for i in range(12)]

#: Les quatre formes qu'un picker peut prendre. Le mode multi ajoute les
#: pastilles, qui étaient la troisième copie ; ``bulk_actions`` ajoute le
#: bandeau, qui héberge les pastilles quand il y a un ``trigger``.
CASES = [
    ("select_single", lambda: Select(options=OPTIONS, value="v3")),
    ("select_multi", lambda: Select(options=OPTIONS, value=["v3"],
                                    multiple=True, bulk_actions=True)),
    ("combobox_single", lambda: Combobox(options=OPTIONS, value="v3")),
    ("combobox_multi", lambda: Combobox(options=OPTIONS, value=["v3"],
                                        multiple=True, bulk_actions=True)),
]


def label_map_copies(html: str) -> int:
    """Combien de fois la carte {valeur → libellé} apparaît-elle ?

    On compte un COUPLE sérialisé — ``"v7": "Zqx7Libelle"`` — et pas un
    libellé seul : un libellé apparaît aussi légitimement dans le texte
    de son option et dans ``_options``. C'est l'appariement clé→valeur
    qui signe la carte.

    ⚠️ Les guillemets arrivent **échappés** : la carte vit dans une
    valeur d'attribut à doubles quotes, donc ``"`` y devient ``&quot;``.
    Chercher la forme brute rendait zéro partout — ce qui se lit
    exactement comme « aucune copie ». C'est le contrôle de non-vacuité
    qui l'a attrapé, pas l'interdiction.
    """
    q = r'(?:"|&quot;)'
    return len(re.findall(rf"{q}v7{q}:\s*{q}Zqx7Libelle{q}", html))


def rendered(builder) -> str:
    with render_isolated():
        return serialize(Component.render_detached(builder()))


@pytest.mark.parametrize("name,builder", CASES, ids=[c[0] for c in CASES])
def test_the_label_map_is_baked_at_most_once(name: str, builder) -> None:
    copies = label_map_copies(rendered(builder))
    assert copies <= 1, (
        f"{name} : la carte des libellés est sérialisée {copies} fois. "
        f"Chaque copie pèse la liste entière — mesuré à ~11 % du "
        f"composant sur 50 options. Passe par la méthode de scope "
        f"``_labelOf(v)`` au lieu d'inliner la carte dans l'expression."
    )


def test_the_combobox_bakes_no_label_map_at_all() -> None:
    """Le cas le plus fort : sa liste d'options porte déjà les libellés.

    Zéro, pas « au plus une ». Si quelqu'un réintroduit un ``_labels``
    dans le Combobox, il redit la moitié d'``_options``.
    """
    for name, builder in CASES:
        if not name.startswith("combobox"):
            continue
        html = rendered(builder)
        assert label_map_copies(html) == 0, name
        assert "_labels:" not in html, (
            f"{name} : la carte ``_labels`` est de retour — chaque entrée "
            f"d'``_options`` porte déjà son ``label``"
        )


def test_the_select_label_map_is_re_seeded_on_a_refresh() -> None:
    """La contrepartie de la déduplication, et le vrai risque.

    Une carte inlinée dans un attribut repart avec le rendu de la zone.
    Une carte de scope, non : elle doit être dans ``_serverSync``, sinon
    un refresh qui change les options laisse les libellés d'avant —
    silencieusement, et sans qu'aucun octet ne manque.
    """
    for name, builder in CASES:
        if not name.startswith("select"):
            continue
        html = rendered(builder)
        marker = re.search(r"_serverSync:\s*\[([^\]]*)\]", html)
        assert marker, f"{name} : pas de marqueur _serverSync"
        keys = marker.group(1)
        assert "_labels" in keys, (
            f"{name} : ``_labels`` vit dans le scope mais n'est pas "
            f"re-semée — après un refresh qui change les options, le "
            f"déclencheur affichera le libellé d'avant. Ajoute-la aux "
            f"clés de ``server_sync_marker``."
        )
        assert "_options" in keys, f"{name} : ``_options`` non plus"


def test_the_sweep_is_not_vacuous() -> None:
    """Un détecteur qui ne reconnaît plus la carte lirait « zéro copie »
    partout, ce qui se lit exactement comme « tout est propre »."""
    assert len(CASES) == 4
    # Contrôle POSITIF : Select DOIT porter sa carte, exactement une fois.
    single = rendered(dict(CASES)["select_single"])
    assert label_map_copies(single) == 1, (
        "le compteur ne reconnaît plus la carte de Select — il rendrait "
        "zéro partout et la gate serait verte par le vide"
    )
    assert "Zqx7Libelle" in single, "les libellés témoins n'atteignent pas le HTML"


def test_the_detector_still_bites() -> None:
    """Les deux versants, sur du HTML fabriqué."""
    one = '<div bz-data="{&quot;v7&quot;: &quot;Zqx7Libelle&quot;}">'
    two = one + '<span bz-text="({&quot;v7&quot;: &quot;Zqx7Libelle&quot;})[v]">'

    assert label_map_copies(one) == 1
    assert label_map_copies(two) == 2, "le doublon doit se voir"
    # Le versant LICITE : un libellé SEUL n'est pas une carte. C'est ce
    # qui sépare « la carte est inlinée » de « l'option affiche son
    # texte », et sans lui la gate rougirait sur du HTML correct.
    assert label_map_copies('<button data-value="v7">Zqx7Libelle</button>') == 0
