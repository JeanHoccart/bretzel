"""Gate — le titre et le pied de la barre restent épinglés, même enveloppés.

Le défaut qu'elle ferme (2026-08-23, trouvé à l'usage)
--------------------------------------------------------
``ui.sidebar`` partitionne ses enfants : le titre en haut, le pied en
bas, **tout le reste** dans une box ``flex-1 min-h-0 overflow-y-auto`` —
la seule qui défile. C'est ce qui empêche une nav trop longue d'emporter
le pied hors de l'écran, et c'était déjà l'objet d'une entrée de
``traps.md``.

Le tri se faisait sur le **type Python** de l'enfant
(``isinstance(child, SidebarFooter)``). Or un enfant de barre est très
souvent ENVELOPPÉ — une zone ``@refreshable`` rend un
``_RefreshableSection``, un ``ui.fragment`` rend un ``Fragment`` — et
aucun des deux n'est une instance de ``SidebarFooter``. Le pied tombait
donc dans le milieu, **dans la barre de défilement**.

Mesuré au navigateur sur deux barres côte à côte, même contenu :

===================  ==================  ============================
pied                 dans le scroll ?    position quand on fait défiler
===================  ==================  ============================
nu                   non                 504 px → 504 px (fixe)
``@refreshable``     **oui**             656 px → **504 px** (il glisse)
===================  ==================  ============================

C'est le cas d'``examples/crm``, dont le pied DOIT être une zone — il
affiche le compte connecté et se rafraîchit quand on en change. Le
playground ne l'a jamais montré parce que son pied n'est pas enveloppé :
un défaut qui n'existe que dans la forme la plus réaliste des deux.

Ce qui est traversé, et ce qui ne l'est PAS
--------------------------------------------
Le tri passe par ``base/_wiring.unwrap_transparent``, qui ne traverse que
les enveloppes **déclarées transparentes** — celles qui portent
``IS_TRANSPARENT_WRAPPER``. Il y en a deux, et c'est fermé :

- la section d'une zone ``@refreshable`` (elle se fusionne dans son
  enfant unique ou se rend en ``display:contents``) ;
- ``ui.fragment`` (qui ne rend aucune balise).

Un vrai conteneur — ``ui.vstack``, ``ui.card`` — n'est **pas** traversé,
et c'est délibéré : l'appelant a demandé une BOÎTE, avec ses classes et
son ``gap``. La déplacer en bas de la barre serait décider à sa place, et
« tout conteneur à enfant unique est transparent » est une devinette là
où ``IS_TRANSPARENT_WRAPPER`` est une déclaration. Le cas est donc
mesuré ici comme NON épinglé, avec ce qu'il faut écrire à la place.

L'invariant
-----------
Titre et pied ne sont jamais descendants de la box qui défile, quelle que
soit l'enveloppe transparente. Structurel et non visuel : un nœud hors de
la box ne PEUT pas défiler avec elle, donc la containment suffit et se lit
dans le SSR. Le repère est le CONTENU, pas un attribut — le tri ne pose
aucun marqueur dans le DOM, et une gate qui en exigerait un décrirait un
mécanisme plutôt qu'un résultat.

⚠️ Ce qu'elle n'affirme PAS : que la box défile vraiment, ni que le pied
soit à la bonne hauteur. Ça, c'est
``tests/runtime_js/test_a_sidebar_end_does_not_scroll_away.py``, qui le
mesure en pixels dans Chromium.
"""

from __future__ import annotations

import re

import pytest

from bretzel import refreshable, ui
from bretzel.components.base.testing import render_isolated
from bretzel.core.serialize import serialize
from bretzel.state import SessionState, field


class _Prefs(SessionState):
    tick: int = field(default=0)


def _body() -> None:
    with ui.sidebar_section(label="MENU"):
        for i in range(6):
            ui.sidebar_item(f"Entrée {i}", icon="circle", href=f"/x{i}")


def _title() -> None:
    ui.sidebar_title("MonCRM", icon="zap")


def _footer() -> None:
    with ui.sidebar_footer(name="Aïcha Benali", subtitle="Commercial"):
        ui.sidebar_footer_item(label="Paramètres", icon_left="settings",
                               href="/p")


def _in_fragment(build) -> None:
    with ui.fragment():
        build()


def _in_a_real_box(build) -> None:
    with ui.vstack(gap="none"):
        build()


#: Les enveloppes TRANSPARENTES, plus le cas nu — qui est le contrôle
#: positif : si lui aussi finissait dans le scroll, la gate accuserait
#: l'enveloppement pour un défaut général de la barre.
_TRAVERSED = {
    "nu": lambda build: build(),
    "refreshable": lambda build: refreshable(deps=[_Prefs])(build)(),
    "fragment": _in_fragment,
}

#: L'enveloppe qui n'est PAS traversée, et la raison. Une table nommée
#: plutôt qu'un silence : le jour où quelqu'un s'en étonne, la réponse
#: est ici et pas dans un commit.
_NOT_TRAVERSED = {
    "boite_reelle": (
        _in_a_real_box,
        "un `ui.vstack` est une BOÎTE que l'appelant a demandée, avec ses "
        "classes et son gap — la déplacer en bas serait décider à sa "
        "place. À écrire autrement : mettre le `vstack` DANS le "
        "`ui.sidebar_footer`, ou envelopper avec `ui.fragment`.",
    ),
}


def _render(wrap, *, which: str) -> str:
    build = _title if which == "title" else _footer
    with render_isolated():
        bar = ui.sidebar(collapsible="rail", open=True)
        with bar:
            if which == "footer":
                _body()
            wrap(build)
            if which == "title":
                _body()
        return serialize(bar.render())


_SCROLL_RE = re.compile(r'<div class="[^"]*overflow-y-auto[^"]*">')


def scroll_box_span(html: str) -> tuple[int, int] | None:
    """Les bornes de la box qui défile, en index de caractères.

    Un découpage par balises plutôt qu'un parseur : le seul ``<div>`` de
    la barre à porter ``overflow-y-auto`` est celle-là, et on veut savoir
    ce qui tombe DEDANS. La profondeur est comptée pour trouver sa
    fermeture — le contenu en contient d'autres.
    """
    m = _SCROLL_RE.search(html)
    if m is None:
        return None
    depth = 0
    for tag in re.finditer(r"<(/?)div\b[^>]*?(/?)>", html[m.start():]):
        if tag.group(2) == "/":
            continue
        depth += -1 if tag.group(1) else 1
        if depth == 0:
            return m.start(), m.start() + tag.end()
    return m.start(), len(html)


def _needle(which: str) -> str:
    return "MonCRM" if which == "title" else "Aïcha Benali"


def test_the_probe_is_not_vacuous() -> None:
    """① Le plancher — la barre rend bien les deux choses qu'on trie."""
    html = _render(_TRAVERSED["nu"], which="footer")
    assert scroll_box_span(html) is not None, (
        "aucune box `overflow-y-auto` dans la barre : le partitionnement "
        "n'a plus lieu, et la gate jugerait sur rien."
    )
    assert "Aïcha Benali" in html, "le pied n'est pas rendu du tout"
    assert "Entrée 0" in html, "la nav n'est pas rendue du tout"


@pytest.mark.parametrize("wrapper", sorted(_TRAVERSED))
@pytest.mark.parametrize("which", ["title", "footer"])
def test_a_transparent_wrapper_keeps_it_pinned(wrapper: str, which: str) -> None:
    """② L'interdiction, sur les trois formes traversées."""
    html = _render(_TRAVERSED[wrapper], which=which)
    span = scroll_box_span(html)
    assert span is not None, f"{wrapper}/{which} : plus de box de défilement"
    start, end = span
    at = html.find(_needle(which))
    assert at != -1, f"{wrapper}/{which} : « {_needle(which)} » n'est pas rendu"
    assert not (start <= at < end), (
        f"le {which} enveloppé en « {wrapper} » se rend DANS la box qui "
        f"défile : il partira avec la nav dès qu'elle déborde.\n"
        f"  `Sidebar.render` déballe ses enfants avec "
        f"`base/_wiring.unwrap_transparent` avant son `isinstance` — un "
        f"enfant enveloppé n'est plus une instance de sa classe. Si tu "
        f"viens d'ajouter une enveloppe, elle doit déclarer "
        f"`IS_TRANSPARENT_WRAPPER`."
    )


@pytest.mark.parametrize("wrapper", sorted(_NOT_TRAVERSED))
@pytest.mark.parametrize("which", ["title", "footer"])
def test_a_real_box_is_declared_as_not_traversed(wrapper: str, which: str) -> None:
    """② bis — l'abstention est MESURÉE, pas supposée.

    Si un jour une vraie boîte se met à être traversée, ce test rougit et
    force la question : est-ce voulu ? Une abstention qu'on n'observe pas
    est une abstention qui a pu disparaître sans qu'on le sache.
    """
    build, reason = _NOT_TRAVERSED[wrapper]
    html = _render(build, which=which)
    start, end = scroll_box_span(html)
    at = html.find(_needle(which))
    assert start <= at < end, (
        f"« {wrapper} » est maintenant TRAVERSÉ pour le {which}, alors que "
        f"la table le déclare comme non traversé :\n  {reason}\n"
        f"Si c'est voulu, déplace l'entrée dans `_TRAVERSED`."
    )


def test_the_containment_check_still_bites() -> None:
    """③ La mutation, dans les deux sens.

    Le détecteur est le découpage de la box : s'il rendait un intervalle
    vide, tout serait « dehors » et la gate serait verte sur rien.
    """
    html = _render(_TRAVERSED["nu"], which="footer")
    start, end = scroll_box_span(html)
    assert end > start + 50, f"intervalle de box absurde : {start}..{end}"
    # Ce qui DOIT être dedans — les entrées de nav.
    assert start < html.index("Entrée 0") < end, (
        "les entrées de nav ne sont pas dans la box qui défile : le "
        "découpage désigne le mauvais nœud, et l'interdiction ci-dessus "
        "ne prouve plus rien."
    )
    # Et ce qui doit être dehors.
    assert not (start < html.index("Aïcha Benali") < end)
