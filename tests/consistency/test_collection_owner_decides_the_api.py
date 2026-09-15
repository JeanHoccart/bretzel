"""Qui possède la boucle décide de l'API — et c'est déclaré, pas deviné.

Le problème que cette gate ferme n'est pas un bug : c'est une **question
sans réponse écrite**. Un composant qui rend une collection peut exposer
son contenu de deux façons — des enfants dans un ``with``, ou un rappel
``render=`` — et jusqu'ici rien ne disait laquelle choisir.

Ce n'est pas théorique. Le 2026-08-18, ``breadcrumb`` a reçu un
``render=`` parce que ``table`` en avait un : un seul exemplaire copié
contre dix qui prennent des enfants. La faute n'était pas d'avoir mal
jugé, c'était qu'il n'y avait **rien à lire**. Et dans un dépôt dont
l'API est presque toujours écrite par une IA, une convention non écrite
n'existe pas.

La règle
--------

Elle tient en une question : **qui écrit le ``for`` ?**

- ``"author"`` — l'auteur. Il lui faut donc un endroit où poser son
  balisage : le composant DOIT accepter des enfants. Un paramètre de
  données reste bienvenu comme raccourci du cas simple
  (``ToggleGroup(options=…)``, ``Breadcrumb(items=…)``), et matérialise
  les mêmes enfants.
- ``"component"`` — le composant. ``Datatable`` cherche, filtre, trie et
  pagine : l'auteur **ne peut pas** écrire cette boucle, donc il n'a
  aucun endroit où mettre son balisage. Le composant DOIT lui offrir un
  rappel de contenu, seul point d'entrée possible.
- ``"client"`` — le navigateur, au runtime. ``Combobox`` bâtit ses
  options une fois côté serveur puis les re-rend en JS à chaque frappe
  du filtre. Ni des enfants ni un rappel Python ne l'atteignent : il
  faut un mécanisme d'une autre nature, et la docstring doit dire
  lequel.
- ``"data"`` — personne, au sens où la question porte. Les éléments
  n'ont **aucun balisage** à porter : ``ui.video(tracks=[…])`` rend un
  ``<track>`` par piste, cinq attributs et rien d'autre. Des enfants et
  un rappel de contenu servent tous deux à placer du balisage ; quand
  il n'y en a pas, les deux sont sans destinataire. Ajoutée le
  2026-08-31 avec ``tracks=``, le premier cas du catalogue qu'aucune
  des trois autres ne décrivait sans mentir — et la gate vérifie les
  deux moitiés de la revendication plutôt que de la croire.

Vérifiée sur les 16 composants-collection du catalogue le 2026-08-18 :
elle prédit l'idiome de 15, et l'unique écart était le ``render=`` de
``breadcrumb`` — écrit la veille, retiré depuis. Une règle qui explique
tout sauf ce qu'on vient d'ajouter n'accuse pas la règle.

Ce que la gate exige
--------------------

1. Tout composant que le détecteur reconnaît comme une collection
   **déclare** ``COLLECTION_OWNER``. C'est le point qui compte : on ne
   peut pas écrire une collection sans répondre à la question.
2. La déclaration **correspond au code** — ``"author"`` sans enfants
   possibles, ``"component"`` sans rappel, ou ``"data"`` qui offre
   pourtant l'un des deux, sont des contradictions.
3. Un ``"client"`` **dit pourquoi** dans sa docstring, sinon il devient
   la case fourre-tout où l'on range ce qu'on n'a pas voulu trancher.

Le détecteur n'est pas une liste
--------------------------------

Une gate qui porterait la liste des collections à la main raterait
précisément le composant neuf — le seul cas qui l'intéresse. D'où un
détecteur **empirique** : un paramètre annoté ``Sequence`` / ``list`` /
``Iterable`` reçoit successivement 1 puis 3 éléments, et si le rendu
gagne des BALISES, le composant itère.

Des balises, pas des caractères : ``textarea.rows`` est l'attribut HTML
``rows``, dont la valeur s'allonge avec la liste sans qu'aucun élément
n'apparaisse. Compté en caractères, il entrait dans la population.
"""

from __future__ import annotations

import pytest

from bretzel.components.base.testing import render_isolated
from bretzel.components.primitives.video import track as _track
from bretzel.core.serialize import serialize
from bretzel.introspect import describe_component
from tests.consistency._discovery import public_component_classes, ui_name_of

#: Les quatre réponses possibles à « qui écrit le ``for`` ? ».
OWNERS = ("author", "component", "client", "data")

#: Les formes d'élément qu'on tente. La première qui construit gagne :
#: on cherche à faire itérer le composant, pas à deviner son schéma.
#:
#: ⚠️ La dernière n'est pas un scalaire, et c'est le point. Un composant
#: dont la collection est faite de DESCRIPTEURS TYPÉS était invisible ici
#: jusqu'au 2026-08-31 : les trois premières formes lèvent dans son
#: rendu, ``_iterates`` avale l'exception, et le composant sort de la
#: population sans un mot. ``ui.video(tracks=)`` est arrivé exactement
#: par ce trou — il aurait échappé à la déclaration en étant pourtant
#: une collection. Un descripteur neuf s'ajoute donc ici.
_SHAPES = (
    ["a", "b", "c"],
    [("a", "A"), ("b", "B"), ("c", "C")],
    [{"k": "a"}, {"k": "b"}, {"k": "c"}],
    [_track(f"{c}.vtt", srclang=c, label=c.upper()) for c in "abc"],
)

_SEQ_HINTS = ("Sequence[", "list[", "Iterable[")

#: Plancher de non-vacuité. Mesuré le 2026-08-18 : 6 collections
#: détectées (breadcrumb, combobox, datatable, select, table,
#: toggle_group), **7 le 2026-08-31** avec ``video`` que la quatrième
#: forme de ``_SHAPES`` fait enfin entrer. Sous ce seuil le détecteur a
#: cassé et la gate n'exigerait plus aucune déclaration — ne le baisse
#: pas.
_FLOOR = 7


def _extras(ui_name: str) -> dict:
    """Ce qu'un composant exige EN PLUS pour se construire.

    Sans ça ``table`` et ``datatable`` lèvent, sortent du balayage sans
    un mot, et la gate cesse d'exiger la déclaration des deux seuls
    ``"component"`` du catalogue — exactement les cas qu'elle existe pour
    tenir."""
    from bretzel.components import DatatableState
    from bretzel.components.data.table.table import column

    class _Probe(DatatableState):
        pass

    if ui_name == "table":
        return {"columns": [column("k", label="K")]}
    if ui_name == "datatable":
        return {
            "columns": [column("k", label="K")],
            "state": _Probe,
            "search": False,
        }
    return {}


def _tag_count(cls: type, prop: str, value, extras: dict) -> int:
    with render_isolated():
        return serialize(cls(**{prop: value}, **extras).render()).count("<")


def _iterates(cls: type, prop: str, ui_name: str) -> bool:
    """Le rendu gagne-t-il des balises quand la donnée gagne des
    éléments ?"""
    extras = _extras(ui_name)
    for shape in _SHAPES:
        try:
            one = _tag_count(cls, prop, shape[:1], extras)
            three = _tag_count(cls, prop, shape, extras)
        except Exception:
            continue
        if three > one:
            return True
    return False


def _collections() -> list[type]:
    """Les composants qui rendent une collection — détectés, pas listés."""
    found: list[type] = []
    for cls in public_component_classes():
        name = ui_name_of(cls)
        params = describe_component(name, cls).params
        for p in params:
            if not any(h in p.type_label for h in _SEQ_HINTS):
                continue
            if _iterates(cls, p.name, name):
                found.append(cls)
                break
    return found


_COLLECTIONS = _collections()


@pytest.mark.parametrize(
    "cls", _COLLECTIONS, ids=lambda c: c.__name__
)
def test_a_collection_declares_who_owns_the_loop(cls: type) -> None:
    owner = cls.COLLECTION_OWNER
    assert owner in OWNERS, (
        f"{cls.__name__} rend une COLLECTION (son rendu gagne des balises "
        f"quand sa donnée gagne des éléments) mais ne déclare pas "
        f"``COLLECTION_OWNER``, dont les valeurs sont {OWNERS}.\n\n"
        f"La question à trancher : QUI écrit le ``for`` ?\n"
        f"  • l'auteur → 'author', et le composant accepte des enfants ;\n"
        f"  • le composant (tri, pagination, requête) → 'component', et "
        f"il expose un rappel de contenu ;\n"
        f"  • le navigateur au runtime → 'client', et la docstring dit "
        f"par quel mécanisme l'auteur reprend la main.\n\n"
        f"Cette déclaration n'est pas de la paperasse : sans elle, le "
        f"prochain composant copiera le premier motif qu'il croise. "
        f"C'est ce qui est arrivé à ``breadcrumb`` le 2026-08-18."
    )


@pytest.mark.parametrize(
    "cls", _COLLECTIONS, ids=lambda c: c.__name__
)
def test_the_declaration_matches_the_code(cls: type) -> None:
    owner = cls.COLLECTION_OWNER

    if owner == "author":
        assert cls.IS_CONTAINER, (
            f"{cls.__name__} déclare que l'AUTEUR possède la boucle, mais "
            f"``IS_CONTAINER`` est False — l'auteur n'a donc nulle part où "
            f"poser son balisage, et la déclaration est un vœu. Soit le "
            f"composant accepte des enfants, soit ce n'est pas 'author'."
        )

    if owner == "component":
        hatch = _content_hatches(cls)
        assert hatch, (
            f"{cls.__name__} déclare que LUI possède la boucle, donc "
            f"l'auteur ne peut pas l'écrire — il lui faut alors un rappel "
            f"de contenu, son seul point d'entrée pour du balisage. Aucun "
            f"paramètre ``Callable`` trouvé sur sa signature."
        )

    if owner == "data":
        # Les deux moitiés de la revendication. ``"data"`` dit « aucun
        # des deux points d'entrée n'a de destinataire » : si l'un des
        # deux existe, la déclaration est fausse, et c'est probablement
        # 'author' ou 'component' qu'il fallait écrire.
        assert not cls.IS_CONTAINER, (
            f"{cls.__name__} déclare 'data' — ses éléments n'ont AUCUN "
            f"balisage à porter — mais il accepte des enfants. Si "
            f"l'auteur a un endroit où écrire du balisage, la boucle est "
            f"la sienne : c'est 'author'."
        )
        assert not _content_hatches(cls), (
            f"{cls.__name__} déclare 'data', mais expose un rappel de "
            f"contenu ({', '.join(_content_hatches(cls))}). Un rappel "
            f"sert à produire du balisage ; s'il y en a, les éléments en "
            f"portent, et c'est 'component'."
        )

    if owner == "client":
        doc = (cls.__doc__ or "") + (
            getattr(__import__(cls.__module__, fromlist=["x"]), "__doc__", "")
            or ""
        )
        assert "client" in doc.lower() or "JS" in doc, (
            f"{cls.__name__} déclare que le CLIENT possède la boucle — "
            f"c'est la case qui n'exige ni enfants ni rappel, donc celle "
            f"où l'on range ce qu'on n'a pas voulu trancher. Sa docstring "
            f"(classe ou module) doit dire POURQUOI le navigateur possède "
            f"la liste, et par quel mécanisme l'auteur reprend la main."
        )


def _content_hatches(cls: type) -> list[str]:
    name = ui_name_of(cls)
    return [
        p.name
        for p in describe_component(name, cls).params
        if "Callable" in p.type_label and not p.name.startswith("on_")
    ]


def test_the_detector_is_not_vacuous() -> None:
    """Sans plancher, un détecteur cassé viderait la population et la
    gate cesserait d'exiger la moindre déclaration, en restant verte."""
    names = sorted(ui_name_of(c) for c in _COLLECTIONS)
    assert len(_COLLECTIONS) >= _FLOOR, (
        f"le détecteur ne trouve plus que {len(_COLLECTIONS)} collections "
        f"(plancher {_FLOOR}, 6 mesurées le 2026-08-18) : {names}. Vérifie "
        f"le détecteur avant de croire que la gate passe."
    )


def test_the_detector_sees_a_collection_of_typed_descriptors() -> None:
    """Le versant qui MORD de la quatrième forme de ``_SHAPES``.

    Retire-la et ce test rougit tout seul : ``video`` sort de la
    population, sa déclaration cesse d'être exigée, et les deux autres
    tests restent verts en n'ayant plus rien à dire de lui. C'est le
    mode d'échec que la gate a réellement eu — pas une hypothèse.

    ``video`` n'est qu'un représentant. Ce qui est gardé ici, c'est que
    le détecteur sache voir une collection dont les éléments sont des
    OBJETS et non des scalaires : le jour où un ``sources=`` ou un
    ``chapters=`` arrive, il entre dans la population sans qu'on ait à
    y penser."""
    from bretzel.components import Video

    assert Video in _COLLECTIONS, (
        "``video`` n'est plus détecté comme une collection alors que son "
        "rendu gagne un ``<track>`` par piste. Le détecteur ne sait "
        "probablement plus construire de descripteurs typés — vérifie "
        "``_SHAPES`` avant de croire que la gate passe."
    )


def test_the_detector_ignores_a_list_that_only_feeds_an_attribute() -> None:
    """``textarea.rows`` est l'attribut HTML ``rows`` : sa valeur
    s'allonge avec la liste, mais aucune balise n'apparaît.

    Ce test garde le choix « compter les BALISES, pas les caractères ».
    Sans lui, quelqu'un peut revenir à ``len(html)`` : la population
    grandit d'un faux positif, reste au-dessus du plancher, et la gate se
    met à exiger d'un attribut HTML qu'il déclare qui possède sa
    boucle."""
    from bretzel.components import Textarea

    assert Textarea not in _COLLECTIONS, (
        "``textarea`` est entré dans la population des collections. Son "
        "``rows`` est un attribut HTML, pas une liste d'items — le "
        "détecteur compte-t-il encore les balises ?"
    )
