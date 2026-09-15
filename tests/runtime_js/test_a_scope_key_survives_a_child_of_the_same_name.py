"""Gate navigateur — écrire dans une clé de scope que porte AUSSI un enfant.

Ce qu'elle garde
----------------
Une expression de directive s'évalue dans ``with($scope) { … }``
(``02_directives.js`` § *Expression compiler*). La question que cette
gate tranche : quand un DESCENDANT porte un attribut HTML du même nom
que la clé de scope — le cas typique, un ``<button value="b">`` dans un
groupe dont la valeur vit sous ``value`` — est-ce que
``bz-on:click="value = 'z'"`` écrit dans **le signal du scope** ou dans
**la propriété DOM du bouton** ?

Pourquoi elle existe
--------------------
Le dépôt a répondu « la propriété DOM » pendant deux ans, et en a tiré
une convention : ``ToggleGroup`` nomme sa clé ``picked`` plutôt que
``value`` pour éviter la collision, ``traps.md`` § *Variable de scope
``bz-data`` shadowée par un attribut HTML du même nom* en fait une règle
générale (« ne JAMAIS nommer une variable de scope comme un attribut
HTML standard »), et cette règle a essaimé : ``val``, ``active``,
``sel``, ``expanded``, ``current`` — **huit orthographes pour une seule
notion**, dont le dépôt sait par ailleurs qu'elle a causé 5 des 8 oublis
de ``_serverSync``.

Or le diagnostic d'origine accuse nommément « des edge-cases d'Alpine 3
/ Proxy traps ». **Alpine n'est plus là** (charter, principe 2 : moteur
maison, aucun Alpine.js), et le compilateur maison ne peut pas
reproduire la faute :

- ``compile()`` est appelée ``fn(scope.proxy, el, …)``, jamais
  ``fn.call(el, …)`` — l'élément n'est PAS sur la chaîne du ``with``,
  c'est un paramètre nommé ``$el`` ;
- le piège ``set`` du Proxy (``03_scope.js``) route vers le signal quand
  la clé est dans ``vars``, et délègue au scope PARENT sinon. Aucune de
  ses branches ne touche un nœud du DOM.

Une convention à huit noms qui repose sur une dépendance supprimée coûte
plus cher que ce qu'elle protège. Cette gate est la mesure qui permet de
la retirer — et de refuser qu'elle revienne : le jour où le compilateur
changerait de contexte d'évaluation (un ``fn.call(el, …)``, un ``$el``
versé dans le ``with``), elle rougit avant que treize composants
n'aient à se re-renommer.

Pourquoi au NAVIGATEUR
----------------------
Aucune lecture de source ne peut trancher : la question porte sur la
résolution d'un identifiant par le moteur JS, pas sur ce que Python
émet. Le HTML est identique dans les deux mondes.

Lourd (uvicorn + Chromium) — lancer explicitement ::

    py -m pytest tests/runtime_js/test_a_scope_key_survives_a_child_of_the_same_name.py -q -m browser
"""

from __future__ import annotations

import pytest

from bretzel import Bretzel, page, ui
from tests.audit.harness import audit_server, browser_page

#: La valeur écrite par le clic. **Différente** de l'attribut ``value=``
#: du bouton, et c'est tout le discriminant : si les deux coïncidaient,
#: une écriture partie dans la propriété DOM rendrait exactement le même
#: résultat qu'une écriture arrivée dans le signal, et la gate serait
#: verte sans rien prouver.
_ECRIT = "z"

#: Ce que le bouton porte en attribut HTML — le nom qui collisionne.
_ATTR = "b"

app = Bretzel(secret_key="d" * 32, title="Bretzel · collision de clé", mode="dev")


@page("/")
def collision() -> None:
    """Un scope dont la clé est ``value``, avec un enfant ``value=``.

    La forme exacte d'un ``ui.toggle_group`` : la valeur choisie vit dans
    le scope de la racine, chaque bouton porte son option en attribut
    HTML ``value=`` (contrat de soumission de formulaire), et le clic
    écrit dans le scope.
    """
    with ui.vstack(gap="md", attrs={"bz-data": "{ value: 'a' }"}):
        ui.button(
            label="Choisir",
            id="bouton",
            attrs={"value": _ATTR, "bz-on:click": f"value = '{_ECRIT}'"},
        )
        # Le témoin : ``bz-attr:`` relit le signal de scope à chaque
        # changement. Ce qui atterrit dans ``data-vu`` EST ce que le
        # scope tient — pas ce que le bouton porte.
        ui.text("témoin", id="temoin", attrs={"bz-attr:data-vu": "value"})


app.include(__name__)

#: Les deux destinations possibles de l'écriture, lues d'un coup pour
#: qu'on puisse dire OÙ elle est partie, pas seulement qu'elle a raté.
_ETAT = """() => ({
  scope: document.getElementById('temoin').dataset.vu,
  dom: document.getElementById('bouton').value,
})"""


@pytest.fixture(scope="module")
def live():
    with audit_server(app) as url, browser_page(url, "/") as pg:
        pg.wait_for_selector("html.bz-ready", state="attached")
        yield pg


def test_the_write_lands_in_the_scope_not_on_the_child(live) -> None:
    """Le clic écrit dans le signal, l'attribut du bouton ne capte rien."""
    avant = live.evaluate(_ETAT)
    assert avant["scope"] == "a", (
        "Le témoin ne reflète pas la valeur initiale du scope "
        f"({avant!r}) — ``bz-attr:`` n'est pas branché, donc la mesure "
        "qui suit ne mesurerait rien."
    )

    live.click("#bouton")
    live.wait_for_timeout(150)
    apres = live.evaluate(_ETAT)

    assert apres["scope"] == _ECRIT, (
        f"``value = '{_ECRIT}'`` n'a pas atteint le signal de scope : "
        f"{avant!r} → {apres!r}.\n"
        f"Si ``dom`` vaut '{_ECRIT}', l'écriture est partie sur la "
        f"propriété DOM du bouton (son attribut ``value=\"{_ATTR}\"`` a "
        "shadowé la clé de scope) — c'est la faute qu'``Alpine 3`` "
        "produisait et que la convention ``picked`` / ``val`` / "
        "``active`` contournait. Elle serait DE RETOUR : le contexte "
        "d'évaluation de ``compile()`` (02_directives.js) a dû changer, "
        "et les treize clés normalisées en ``value`` doivent être "
        "reconsidérées AVANT toute autre correction."
    )
    assert apres["dom"] == _ATTR, (
        "L'attribut ``value=`` du bouton a bougé — il porte le contrat "
        f"de soumission du formulaire et doit rester '{_ATTR}' : "
        f"{apres!r}."
    )
