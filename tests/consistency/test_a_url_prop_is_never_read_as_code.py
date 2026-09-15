"""Gate : une prop qui porte une URL n'est jamais relue comme du code.

Le défaut qu'elle ferme (2026-08-26)
------------------------------------
``looks_like_client_expr`` renifle une chaîne pour décider si c'est du
texte ou une expression client. Sur une URL, elle se trompe **selon le
contenu de l'URL** : ``==`` est un marqueur fort, et c'est exactement ce
qu'écrit le padding d'un blob base64.

Mesuré : l'export CSV du datatable passe son URL signée à
``ui.button(href=…)``. Au repos le lien porte ``href=`` ; après une
recherche, le payload retombe sur le padding, la valeur part en
``bz-attr:href``, et le runtime tente de compiler
``/_bretzel/datatable.csv?q=…`` comme du JS — ``/…/`` est un littéral
regex — puis jette ``Invalid regular expression flags``. Résultat : le
lien n'a **plus d'attribut ``href`` du tout**. Le bouton Export ne
télécharge rien, sans rien afficher.

C'était la **troisième** occurrence de la classe. Les deux premières
(``--w: 200px``, la data-URI de ``signature_pad``) avaient été réparées
par une exclusion de FORME dans l'heuristique — la dernière en date étant
``value.startswith("data:")``. Une exclusion de forme ne ferme que
l'occurrence qu'elle a vue : elle devine sur la VALEUR ce que seule la
PROP peut dire.

L'invariant
-----------
Une prop dont le nom dit qu'elle porte une URL déclare
``reactive_prop(never_code=True)``, et l'heuristique ne tourne pas
dessus. C'est le même patron que ``writes`` / ``scope_keys`` /
``names_field`` : le fait vit sur la prop, pas dans un balayage qui
essaie de le redécouvrir (cf. la memory « la déclaration vit sur la
prop »).

Ce que cette gate NE fait pas
------------------------------
Elle ne devine pas qu'une prop porte une URL autrement que par son
**nom** : le vocabulaire est déclaré ci-dessous, à la main. Une prop qui
porterait une URL sous un nom neuf (``background_url``, ``endpoint``)
doit y être ajoutée — le plancher ne le dira pas, seule une relecture le
dira. C'est assumé : l'alternative serait de renifler la valeur, ce qui
est précisément le mécanisme dont ce fichier documente l'échec.

Les deux versants de la morsure
--------------------------------
Le versant ILLICITE (une URL piégée ne doit jamais devenir un
``bz-attr:``) ne dit rien du taux de faux positifs. C'est le versant
LICITE — ``never_code`` n'a pas fui sur les AUTRES props, une vraie
expression y est toujours détectée — qui garde l'utilité de
l'heuristique, et c'est lui qui sert de preuve de morsure : un détecteur
qui reconnaît encore un cas réel n'est pas aveugle.
"""

from __future__ import annotations

import re

import pytest

from bretzel import ui
from bretzel.components.base.reactive_prop import looks_like_client_expr
from bretzel.components.base.testing import render_isolated
from bretzel.core.serialize import serialize
from tests.consistency._discovery import (
    assert_sweep_is_not_vacuous,
    public_component_classes,
    rendered_html_of,
    ui_name_of,
)

#: Preuve de morsure : le versant licite. Si ``never_code`` fuyait sur
#: toutes les props, ce test tomberait — donc la porte est vraiment
#: sélective, et l'heuristique est toujours branchée là où elle sert.
MUTATION_PROOF = "test_the_door_did_not_leak_to_every_prop"

#: Le vocabulaire des props qui portent une URL. Déclaré, pas deviné —
#: cf. la docstring § *Ce que cette gate NE fait pas*.
_URL_PROP_NAMES: frozenset[str] = frozenset(
    {"href", "src", "poster", "srcset", "action", "cite", "avatar", "formaction"}
)

#: Les porteurs d'URI dont le NOM ne l'annonce pas. Nominatif et court
#: par construction : chaque entrée est une prop dont le nom ment sur ce
#: qu'elle transporte, donc chacune demande d'être lue une fois.
#:
#: ``SignaturePad.value`` est une data-URL PNG. C'est le porteur qui a
#: motivé l'exclusion ``data:`` de l'heuristique le 2026-08-13, retirée
#: le 2026-08-26 — sans cette entrée, la retirer le re-casserait, et
#: c'est exactement ce qui a failli arriver.
_URI_CARRIERS_BY_NAME: frozenset[tuple[str, str]] = frozenset(
    {("SignaturePad", "value")}
)

#: 15 porteurs mesurés le 2026-08-26. Le plancher attrape un
#: ``__reactive_props__`` mal lu — la pathologie exacte qui avait rendu
#: ``test_palette_color_is_prefixed`` aveugle (0 composant sur 76).
_CARRIERS_FLOOR = 15

#: L'URL qui a produit le bug, réduite à ce qui compte : un padding
#: base64 (``==``) dans une query string, derrière un chemin qui
#: s'ouvre par ``/`` — donc lisible comme un littéral regex.
_BOOBY_TRAPPED_URL = "/_bretzel/datatable.csv?q=eyJzZWFyY2giOiJpc3N1ZSJ9==&sig=ab"


def _url_carriers() -> list[tuple[type, str]]:
    """``(classe, nom de prop)`` pour chaque prop qui porte une URL."""
    found: list[tuple[type, str]] = []
    for cls in public_component_classes():
        for name, descriptor in getattr(cls, "__reactive_props__", {}).items():
            if (
                name in _URL_PROP_NAMES
                or (cls.__name__, name) in _URI_CARRIERS_BY_NAME
            ):
                found.append((cls, name))
    return found


_CARRIERS = _url_carriers()
_IDS = [f"{cls.__name__}.{prop}" for cls, prop in _CARRIERS]


def test_the_sweep_is_not_vacuous() -> None:
    assert_sweep_is_not_vacuous()
    assert len(_CARRIERS) >= _CARRIERS_FLOOR, (
        f"seulement {len(_CARRIERS)} props porteuses d'URL découvertes "
        f"(15 mesurées le 2026-08-26) — vérifie que "
        f"``__reactive_props__`` se lit encore avant de croire que cette "
        f"gate passe. Une gate qui ne sélectionne rien est verte sur rien."
    )


@pytest.mark.parametrize(("cls", "prop"), _CARRIERS, ids=_IDS)
def test_a_url_prop_declares_never_code(cls: type, prop: str) -> None:
    descriptor = cls.__reactive_props__[prop]
    assert descriptor.never_code, (
        f"``{ui_name_of(cls)}({prop}=…)`` porte une URL ou une URI mais ne "
        f"déclare pas "
        f"``reactive_prop(never_code=True)``.\n"
        f"  Sans elle, ``looks_like_client_expr`` tourne sur la valeur — et "
        f"une URL qui contient ``==`` (padding base64), ``&&`` ou un appel "
        f"entre parenthèses en sort classée « expression client ».\n"
        f"  Conséquence mesurée : l'attribut disparaît du HTML et le runtime "
        f"jette une erreur de syntaxe en tentant de compiler l'URL."
    )


@pytest.mark.parametrize(("cls", "prop"), _CARRIERS, ids=_IDS)
def test_a_booby_trapped_url_stays_an_attribute(cls: type, prop: str) -> None:
    """Le versant ILLICITE, au rendu — pas sur le drapeau.

    Vérifier que ``never_code`` est posé ne prouve pas qu'il est LU :
    c'est la porte du constructeur qui compte, et elle vit ailleurs
    (``Component.__init__``). On rend donc pour de vrai.
    """
    html = rendered_html_of(cls, prop=prop, value=_BOOBY_TRAPPED_URL)
    if html is None:
        pytest.skip(f"{cls.__name__} déclare avoir besoin d'un contexte")
    # ⚠️ On ne peut PAS exiger l'absence de tout ``bz-attr:<prop>`` : une
    # prop ``writes=True`` en émet un par construction, qui pointe sa clé
    # de scope (``bz-attr:value="value"`` sur SignaturePad). Ce qui est
    # interdit, c'est que l'URL ELLE-MÊME y atterrisse — c'est elle que le
    # navigateur compilerait.
    #
    # Et pas non plus « l'URL apparaît quelque part dans un ``bz-attr:`` » :
    # les items de nav (Navbar / Sidebar / BottomBar) bâtissent leur
    # ``aria-current`` en encastrant le href ENTRE GUILLEMETS dans une
    # comparaison (``current_path === "/x" ? 'page' : null``). L'URL y est
    # une chaîne JS, pas du code — c'est licite, et l'exiger absente
    # casserait trois composants sans qu'aucun bug n'existe.
    #
    # L'interdit exact : l'URL EST l'expression, seule et nue.
    needle = _BOOBY_TRAPPED_URL.replace("&", "&amp;")
    leaked = [
        found
        for found in re.findall(r'bz-attr:[a-zA-Z0-9_:-]+="([^"]*)"', html)
        if found.strip() in (needle, _BOOBY_TRAPPED_URL)
    ]
    assert not leaked, (
        f"``{ui_name_of(cls)}({prop}=<url avec padding base64>)`` fait "
        f"partir l'URL dans un ``bz-attr:`` : {leaked[0][:80]!r}.\n"
        f"  Le navigateur va la compiler comme du JavaScript, échouer, et "
        f"l'attribut ne sera JAMAIS posé — le lien ou l'image est mort, "
        f"en silence."
    )
    # Le pendant POSITIF : l'URL doit être arrivée quelque part. Une prop
    # qui l'avalerait entièrement passerait l'assertion ci-dessus sans
    # rien rendre — vert sur rien, la pathologie que ce répertoire traque.
    assert needle in html or _BOOBY_TRAPPED_URL in html, (
        f"``{ui_name_of(cls)}({prop}=…)`` ne rend l'URL nulle part dans son "
        f"HTML — la sonde n'a rien mesuré, donc l'absence de ``bz-attr:`` "
        f"ne prouve rien ici."
    )


def test_the_door_did_not_leak_to_every_prop() -> None:
    """Le versant LICITE : l'heuristique sert toujours là où elle sert.

    ``never_code`` est une porte PAR PROP. Si elle avait été branchée
    trop haut — sur toutes les props, ou sur toutes les chaînes — le
    tier-2 de l'API (« écris ton expression client à la main ») serait
    mort sans que rien ne rougisse : les expressions partiraient en
    attributs HTML littéraux, inertes.
    """
    with render_isolated():
        html = serialize(ui.button("x", disabled="count >= 10").render())
    assert 'bz-attr:disabled="count &gt;= 10"' in html or (
        'bz-attr:disabled="count >= 10"' in html
    ), (
        "``ui.button(disabled='count >= 10')`` n'émet plus de "
        "``bz-attr:disabled`` — l'expression part en attribut littéral, "
        f"donc inerte. La porte ``never_code`` a fui hors des props "
        f"qui la déclarent.\n  HTML : {html[:400]}"
    )
    # Et l'heuristique elle-même reconnaît toujours ses deux versants.
    assert looks_like_client_expr("count >= 10")
    assert not looks_like_client_expr("Helpful hint")


def test_the_escape_hatch_survives_on_a_url_prop() -> None:
    """Forcer une expression sur une prop ``never_code`` reste possible.

    ``never_code`` retire la DEVINETTE, pas la capacité. Un appelant qui
    veut vraiment un ``href`` piloté par le client écrit la directive,
    et elle doit passer — sinon la déclaration serait une perte de
    fonctionnalité déguisée en correction de bug.
    """
    with render_isolated():
        html = serialize(
            ui.button("x", **{"bz-attr:href": "state.target"}).render()
        )
    assert 'bz-attr:href="state.target"' in html, (
        "l'échappatoire ``**{'bz-attr:href': …}`` ne passe plus sur une "
        f"prop ``never_code``.\n  HTML : {html[:400]}"
    )
