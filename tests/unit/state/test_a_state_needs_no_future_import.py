"""Un état déclaré sans ``from __future__ import annotations`` a ses champs.

Sur Python 3.14 (PEP 649), les annotations d'un corps de classe ne sont
plus rangées dans ``__annotations__`` mais derrière une fonction,
``__annotate_func__``. La métaclasse ne lisait que le premier endroit et
voyait un dict vide.

⚠️ **La gravité a changé le 2026-09-05**, quand tout champ est devenu un
appel à ``field()``. Un champ est désormais un descripteur posé dans le
corps de classe : il EXISTE sans annotation. Ce que la mauvaise lecture
ferait perdre, ce n'est plus le champ — c'est son TYPE, donc la
coercition des valeurs de formulaire (« 3 » resterait la chaîne ``"3"``).
Sérieux, mais plus la panne totale d'avant, où l'état ne stockait
strictement rien. L'obligation de ``field()`` a supprimé la forme
catastrophique par construction.

Le dépôt y échappait en écrivant ``from __future__ import annotations`` en
tête de chaque module, et une règle de lint le réclamait aux autres. Depuis
le 2026-09-04 la métaclasse lit au bon endroit : l'import n'est plus requis,
et la règle a été retirée — elle signalait désormais du code qui marche.

**Aucun test de ce dépôt ne pouvait attraper ça** : ils portent tous le
future import, par convention. D'où la forme de ce fichier — le module
d'essai est COMPILÉ ici, sans le drapeau, ce qui reproduit exactement la
situation d'un utilisateur qui écrit son premier fichier.
"""

from __future__ import annotations

import sys
from typing import Any

import pytest

from bretzel.state import base as state_base

pytestmark = pytest.mark.skipif(
    sys.version_info < (3, 14),
    reason="PEP 649 class annotations are a Python 3.14+ behavior",
)

SOURCE = """
from bretzel.state import AppState, SessionState, field


class Compteur(AppState):
    n: int = field(default=0)
    nom: str = field(default="")


class Panier(SessionState):
    articles: list[str] = field(default_factory=list)
    coupon: str = field(default="")


class Filtre(SessionState):
    plus_tard: "PasEncoreDefini" = field(default=None)


# Le témoin : une métaclasse qui note ce que le corps de classe portait
# VRAIMENT au moment de sa création. C'est la seule façon de le voir —
# après coup, la classe matérialise ses annotations à la demande.
TEMOIN = {}


class _Mouchard(type):
    def __new__(mcs, nom, bases, ns, **kw):
        TEMOIN["annotations_dans_le_corps"] = "__annotations__" in ns
        TEMOIN["fonction_differee"] = "__annotate_func__" in ns
        return super().__new__(mcs, nom, bases, ns)


class Temoin(metaclass=_Mouchard):
    x: int = 0
"""


def _module_sans_future() -> dict[str, Any]:
    """Exécuter ``SOURCE`` comme un module qui n'a PAS le future import.

    ``dont_inherit=True`` est le mot qui compte : sans lui, ``compile``
    reprend les ``__future__`` du module APPELANT — donc celui-ci, qui
    porte l'import — et le harnais testerait le chemin déjà couvert par
    toute la suite. C'est le contrôle positif juste au-dessus qui l'a
    attrapé pendant l'écriture, pas une relecture.
    """
    namespace: dict[str, Any] = {}
    exec(compile(SOURCE, "<sans_future>", "exec", dont_inherit=True), namespace)
    return namespace


def test_the_harness_really_compiles_without_the_future_import() -> None:
    """Le contrôle positif : on exerce bien le chemin PEP 649.

    Sans lui, ce fichier resterait vert le jour où le harnais se mettrait
    à hériter du ``from __future__`` de CE module — il testerait alors le
    chemin déjà couvert par toute la suite, c'est-à-dire rien.
    """
    temoin = _module_sans_future()["TEMOIN"]
    assert not temoin["annotations_dans_le_corps"], (
        "le corps de classe portait des ``__annotations__`` : le harnais "
        "a hérité du future import de CE module et ne prouve plus rien."
    )
    assert temoin["fonction_differee"], (
        "ni annotations matérialisées, ni ``__annotate_func__`` — le "
        "harnais ne compile plus ce qu'on croit."
    )


def test_plain_annotations_become_fields() -> None:
    espace = _module_sans_future()
    assert list(espace["Compteur"]._all_fields()) == ["n", "nom"]
    assert list(espace["Panier"]._all_fields()) == ["articles", "coupon"]


def test_a_field_is_tracked_and_serialised() -> None:
    """Le vrai symptôme : muter puis regarder ce que le commit enverrait."""
    espace = _module_sans_future()
    etat = espace["Compteur"]()
    etat.n += 1
    assert etat.n == 1
    assert etat._dirty, "la mutation n'est pas suivie — rien ne se rafraîchira"
    assert etat.to_dict() == {"n": 1}, (
        "le champ n'est pas sérialisé : l'état ne serait jamais persisté, "
        "sans la moindre erreur."
    )


def test_the_declared_type_is_resolved() -> None:
    """Les annotations arrivent en TEXTE ; la métaclasse doit les résoudre.

    Sans cette résolution, la coercition des valeurs de formulaire
    (« 3 » → ``3``) n'aurait plus de type cible.
    """
    espace = _module_sans_future()
    assert espace["Compteur"]._all_fields()["n"].type_ is int
    assert espace["Compteur"]._all_fields()["nom"].type_ is str


def test_an_unresolvable_forward_reference_does_not_raise() -> None:
    """Une référence avant ne doit pas faire exploser la déclaration.

    C'est la raison du format TEXTE : évaluer les annotations à la
    construction de la classe lèverait ``NameError`` sur un nom défini
    plus loin, ou pas défini du tout.
    """
    espace = _module_sans_future()
    assert list(espace["Filtre"]._all_fields()) == ["plus_tard"]


def test_a_subclass_no_longer_shadows_an_inherited_field() -> None:
    """Le second mode d'échec, plus retors que le premier.

    Quand le nom redéclaré existe déjà chez le parent, l'attribut simple
    MASQUAIT le ``Field`` hérité : la lecture rendait la bonne valeur —
    donc l'écran paraissait juste — pendant que le suivi de changement
    lisait, lui, le défaut du parent. Mesuré à l'époque : 25 affiché,
    20 vu par le diff.
    """
    espace = _module_sans_future()
    source_enfant = """
class Grand(Compteur):
    n: int = field(default=8)
"""
    exec(
        compile(source_enfant, "<sans_future>", "exec", dont_inherit=True),
        espace,
    )
    enfant = espace["Grand"]()
    enfant.n = 25
    assert enfant.n == 25
    assert enfant._field_values()["n"] == 25, (
        "le suivi de changement lit une autre valeur que l'écran — "
        "l'attribut masque le ``Field`` du parent."
    )


def test_the_old_reader_would_stop_enforcing_the_rule(monkeypatch) -> None:
    """Le versant qui MORD, et il a changé de nature deux fois.

    Ce que la mauvaise lecture coûte AUJOURD'HUI n'est ni les champs (ce
    sont des descripteurs posés par ``field()``) ni leurs types (l'étape 5
    les résout depuis la CLASSE, où Python les matérialise à la demande).
    C'est le **refus** : la métaclasse ne peut interdire une déclaration
    nue que si elle la voit. Avec l'ancienne lecture, ``n: int = 0`` passe
    sans un mot dans un module sans le ``__future__`` — et là, comme
    aucun ``field()`` n'a été appelé, le champ n'existe vraiment pas.

    Autrement dit : la règle de déclaration unique et la lecture correcte
    des annotations se tiennent l'une l'autre. Débrancher la seconde
    rouvre la panne muette d'origine, pour le seul code que la première
    est censée refuser.
    """
    monkeypatch.setattr(
        state_base,
        "_body_annotations",
        lambda namespace: namespace.get("__annotations__", {}),
    )
    source_nu = "\n".join(
        ["from bretzel.state import AppState", "class Nu(AppState):", "    n: int = 0"]
    )
    espace: dict[str, Any] = {}
    exec(
        compile(
            source_nu,
            "<sans_future>",
            "exec",
            dont_inherit=True,
        ),
        espace,
    )
    assert list(espace["Nu"]._all_fields()) == [], (
        "la déclaration nue a produit un champ : le harnais n'exerce donc "
        "pas le chemin qu'on croit."
    )
