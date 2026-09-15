"""Gate : aucun composant n'émet une URL de ressource VIDE.

``<img src="">`` ne casse rien à l'écran. Le navigateur résout l'attribut
vide contre l'URL du document et **retélécharge la page courante** en
croyant charger une image ; ``<iframe src="">`` va plus loin et met la
page dans elle-même. Il n'y a ni erreur, ni exception, ni pixel de
travers — seulement des requêtes en trop, visibles nulle part sauf dans
les logs du serveur.

C'est comme ça que le bug a été trouvé le 2026-08-14 : `ui.image` et
`ui.video` faisaient ``attrs["src"] = values.get("src") or ""``, et
l'utilisateur a vu défiler des dizaines de 404 dans uvicorn. **12 000
tests et trois passes de probes visuels ne l'avaient pas vu**, parce
qu'ils regardent le DOM et les pixels, jamais le réseau.

Le fix vit au point d'étranglement (``core/escape.py`` §
``_EMPTY_IS_A_BUG`` : ``serialize_attrs`` saute une chaîne vide sur un
attribut de chargement). Cette gate garde le RÉSULTAT plutôt que
l'implémentation : elle rend chaque composant public sans source et
vérifie la sortie. Elle tient donc même si quelqu'un contourne le
sérialiseur — en écrivant l'attribut à la main dans un `Html` node, par
exemple.

⚠️ Ce qu'elle ne doit PAS attraper, et qui est la moitié délicate : les
chaînes vides **significatives**. ``alt=""`` fait ignorer une image
décorative par le lecteur d'écran (l'omettre lui fait annoncer l'URL,
c'est le contraire) ; ``sandbox=""`` est le bac à sable maximal ;
``value=""`` est un champ vidé. La liste surveillée est donc restreinte
aux attributs qui désignent une ressource à CHARGER — pas ``href`` ni
``action``, où le vide pointe légitimement sur la page courante.
"""

from __future__ import annotations

import inspect
import re

import pytest

from bretzel.core.escape import _EMPTY_IS_A_BUG
from tests.consistency._discovery import (
    public_component_classes,
    rendered_html_of,
)

#: ``src=""`` / ``poster=''`` / ``srcset=""`` … dans la sortie sérialisée.
_EMPTY_RESOURCE = re.compile(
    r"\b(" + "|".join(sorted(_EMPTY_IS_A_BUG)) + r")=([\"'])\2"
)


#: Ce que le bâtisseur partagé ne construit pas, avec sa raison.
#: **VIDE**, et mesuré le 2026-08-19.
#:
#: ⚠️ Avant ce jour, la construction maison de cette gate en sautait
#: TROIS — ``Datatable`` (exige un ``state=``), ``MetaTag`` (exige un
#: identifiant), ``ToggleButton`` (exige un ``ToggleGroup`` parent) —
#: alors que ``CONSTRUCT`` et ``_BARE_ARGS`` savent bâtir les trois
#: depuis le matin. Elle devinait les arguments requis à partir de leur
#: ANNOTATION (« si c'est ``str``, passe ``""`` ; sinon abandonne »), ce
#: qui rate tout ce qui n'est pas une chaîne.
_CANNOT_BUILD: dict[str, str] = {}


def _accepts_src(cls: type) -> bool:
    """``src=`` est-il un paramètre déclaré de ce composant ?

    Le socle REFUSE désormais un kwarg qu'il ne lit pas — sonder ``src``
    sur un composant qui n'en a pas lève, et ce n'est pas une abstention
    mais une non-applicabilité. On filtre donc AVANT de construire.
    """
    try:
        return "src" in inspect.signature(cls.__init__).parameters
    except (TypeError, ValueError):  # pragma: no cover
        return False


def _components_that_can_carry_a_source() -> list[type]:
    """Les composants qui portent un attribut surveillé QUAND on leur en
    donne un.

    C'est le bon ancrage de découverte, et le premier jet se trompait :
    interroger le rendu SANS source ne trouve plus personne une fois le
    fix en place — puisque justement, plus rien n'est émis. On donne donc
    une vraie source et on regarde qui la porte.

    Découverte, pas liste écrite : un nouveau composant média y entre tout
    seul, donc la gate n'a pas à être maintenue.
    """
    found = []
    for cls in public_component_classes():
        if not _accepts_src(cls):
            continue
        out = rendered_html_of(cls, prop="src", value="/ressource")
        if out and "/ressource" in out:
            found.append(cls)
    return found


@pytest.mark.parametrize(
    "cls", public_component_classes(), ids=lambda c: c.__name__
)
def test_no_empty_resource_url(cls: type) -> None:
    out = rendered_html_of(cls)
    if out is None:
        pytest.skip("composant DÉCLARÉ non constructible (CONSTRUCT)")

    hit = _EMPTY_RESOURCE.search(out)
    assert hit is None, (
        f"{cls.__name__} émet {hit.group(0)!r} sans source.\n\n"
        "Un attribut de chargement vide est résolu contre l'URL du "
        "document : le navigateur retélécharge LA PAGE COURANTE en croyant "
        "charger la ressource. Rien ne casse à l'écran — ça ne se voit que "
        "dans les logs du serveur.\n\n"
        "N'écris pas ``attrs[x] = valeur or \"\"`` : laisse la valeur à "
        "``None``, que ``serialize_attrs`` saute déjà. Cf. "
        "``core/escape.py`` § _EMPTY_IS_A_BUG."
    )


def test_the_sweep_finds_components_that_carry_a_source() -> None:
    """Plancher de non-vacuité — ancré sur la DÉCOUVERTE.

    Le test du dessus est une INTERDICTION : il passe tout aussi bien si
    plus aucun composant n'émet d'attribut surveillé, ou si le balayage
    saute tout le monde via ses ``pytest.skip``. On vérifie donc qu'il
    reste des composants qui portent réellement une de ces URLs.

    Le compte n'est pas figé — un plancher qui gèle une population rougit
    au premier composant retiré, pour rien. On exige seulement que la
    famille média soit là, parce que c'est elle qui a produit le bug.
    """
    carriers = {cls.__name__ for cls in _components_that_can_carry_a_source()}
    expected = {"Image", "Video", "Audio", "Iframe"}
    missing = expected - carriers
    assert not missing, (
        f"Ces composants ne portent plus d'attribut de ressource : "
        f"{sorted(missing)}.\n"
        f"Trouvés : {sorted(carriers)}.\n\n"
        "Soit ils ont été retirés (mets à jour cette liste), soit le "
        "balayage ne sait plus les construire — et l'interdiction "
        "ci-dessus ne vérifie alors plus rien sur eux."
    )


def test_the_abstentions_are_declared() -> None:
    """Ce que le bâtisseur partagé ne monte pas est NOMMÉ, pas compté.

    La table est vide aujourd'hui, et c'est le but : une exemption se
    déclare avec sa raison, elle ne s'obtient pas en échouant en silence.
    ``Link`` n'y est pas — il est déjà déclaré dans ``CONSTRUCT``, et le
    ``skip`` du test ci-dessus le nomme.
    """
    missing = {
        cls.__name__ for cls in public_component_classes()
        if _accepts_src(cls) and rendered_html_of(cls, prop="src", value="/x") is None
    }
    surprise = sorted(missing - set(_CANNOT_BUILD))
    assert not surprise, (
        f"{surprise} accepte(nt) `src=` mais ne se construi(sen)t plus avec "
        f"une source : ils sortent du balayage EN SILENCE, et la découverte "
        f"des porteurs d'URL ne les voit plus.\n"
        f"  Répare la construction, ou ajoute l'entrée à `_CANNOT_BUILD` "
        f"AVEC sa raison."
    )
    stale = sorted(set(_CANNOT_BUILD) - missing)
    assert not stale, (
        f"{stale} se construi(sen)t de nouveau — retire l'entrée."
    )


def test_the_detector_still_bites() -> None:
    """Mutation : un attribut de ressource VIDE est encore reconnu.

    Un attribut de chargement vide est résolu contre l'URL du document :
    le navigateur retélécharge la page courante en croyant charger la
    ressource. Rien ne casse à l'écran — donc si la regex cessait de
    matcher, personne ne le verrait.
    """
    for offending in ('<img src="">', "<video poster=''>", '<img srcset="">'):
        assert _EMPTY_RESOURCE.search(offending), f"{offending!r} devrait mordre"
    for licit in ('<img src="/x.png">', '<div data-open="false">', '<a href="">'):
        assert not _EMPTY_RESOURCE.search(licit), f"{licit!r} : faux positif"
