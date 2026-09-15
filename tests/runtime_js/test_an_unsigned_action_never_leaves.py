"""Un POST d'action sans porteur de signature ne part pas.

Ce que cette gate ferme
-----------------------

Le bridge lit ``data-bz-sig`` sur ``elt.closest("[data-bz-sig]")`` au
moment du ``htmx:configRequest``. Jusqu'au 2026-08-27, quand ce
``closest`` rendait ``null``, **la requête partait quand même** — nue.

Elle ne pouvait pas aboutir : côté Python, ``action_attrs`` est le seul
endroit qui écrit un ``hx-post``, et il y pose ``data-bz-sig`` dans le
même dict. Tout POST htmx est donc une action, et toute action naît
signée. Un porteur absent au ``configRequest`` ne veut dire qu'une
chose : l'élément a été **détaché** entre le déclenchement et l'envoi,
typiquement par le morph d'une zone ``@refreshable``.

Et le prix de la laisser partir n'est pas un échec silencieux : le
serveur répond à toute signature invalide par un ``_error: reload``, que
le bridge exécute. Une requête déjà obsolète **recharge donc la page
entière**, sous les doigts de l'utilisateur.

Reproduit le 2026-08-27 sur ``/carousel`` : un autoplay tique pendant
qu'un flip re-rend le panneau serveur, le nœud disparaît, le POST part
nu, 403, rechargement. L'audit voyait ``Execution context was
destroyed`` et le comptait comme un **flake de concurrence** — c'était
déterministe, 2 fois sur 2 en isolation.

Pourquoi retirer l'attribut plutôt que détacher le nœud
--------------------------------------------------------

Détacher vraiment l'élément empêcherait htmx de déclencher quoi que ce
soit : il n'y aurait plus d'événement, donc plus rien à mesurer. Retirer
``data-bz-sig`` reproduit exactement ce que le bridge OBSERVE — un
``closest`` qui rend ``null`` — sans changer le reste du chemin.
"""

from __future__ import annotations

import pytest

from bretzel import Bretzel, ui
from bretzel.render import page
from tests.audit.harness import audit_server, browser_page


#: Le handler et la page vivent au niveau MODULE, et il le faut : un
#: ``action_id`` est ``<module>::<qualname>``, et le résolveur le relit
#: par ``getattr`` sur le module. Une fonction imbriquée porte
#: ``_app.<locals>.touched`` dans son qualname — donc pas d'action du
#: tout, pas de ``hx-post``, et une gate verte sur une page vide.
_APP = Bretzel(secret_key="s" * 32, mode="dev")


def touched() -> None:
    """Cible d'action — jamais atteinte par le cas nu."""


@page("/")
def home() -> None:
    ui.button("Agir", on_click=touched)


_APP.include(home)


@pytest.fixture(scope="module")
def live():
    with audit_server(_APP) as url:
        with browser_page(url, "/", wait_until="load") as page_obj:
            yield page_obj


def _click_and_watch(page_obj, *, strip_sig: bool) -> dict:
    """Clique l'acteur et rend ce qui est parti, plus l'état de la page."""
    return page_obj.evaluate(
        """async (strip) => {
            const el = document.querySelector('[hx-post]');
            if (!el) return {posts: [], avaitPorteur: false, absent: true};
            const carrier = el.closest('[data-bz-sig]');
            if (strip && carrier) carrier.removeAttribute('data-bz-sig');
            const posts = [];
            const vrai = window.fetch;
            const vraiOpen = XMLHttpRequest.prototype.open;
            XMLHttpRequest.prototype.open = function (m, u) {
                if (String(m).toUpperCase() === 'POST') posts.push(u);
                return vraiOpen.apply(this, arguments);
            };
            window.fetch = function (u, o) {
                if (o && String(o.method).toUpperCase() === 'POST') posts.push(String(u));
                return vrai.apply(this, arguments);
            };
            el.click();
            await new Promise(r => setTimeout(r, 700));
            XMLHttpRequest.prototype.open = vraiOpen;
            window.fetch = vrai;
            return {posts, avaitPorteur: !!carrier};
        }""",
        strip_sig,
    )


def test_a_signed_action_does_leave(live) -> None:
    """Le plancher, et le versant LICITE.

    Sans lui, l'interdiction serait verte sur une page où RIEN ne poste
    jamais — un bouton mal câblé la rendrait tout aussi verte.
    """
    out = _click_and_watch(live, strip_sig=False)
    assert not out.get("absent"), "aucun élément `hx-post` sur la page"
    assert out["avaitPorteur"], "le bouton d'action n'a pas de `data-bz-sig`"
    assert any("/_bretzel/action/" in u for u in out["posts"]), (
        f"une action SIGNÉE n'est pas partie : {out['posts']}"
    )


def test_an_action_whose_carrier_vanished_is_dropped(live) -> None:
    """L'interdiction : nu, ça ne part pas.

    Le même bouton, le même clic — seul le porteur a disparu.
    """
    out = _click_and_watch(live, strip_sig=True)
    assert not [u for u in out["posts"] if "/_bretzel/action/" in u], (
        f"une action NON SIGNÉE est partie : {out['posts']}. Le serveur "
        "y répondra par un `_error: reload`, donc la page entière se "
        "rechargera pour une requête déjà obsolète."
    )


def test_the_page_did_not_reload(live) -> None:
    """Ce que l'utilisateur voit, et la seule chose qui compte vraiment.

    Ce test tourne APRÈS celui qui retire la signature, sur la MÊME page
    (fixture de module) : si le POST nu était parti, le 403 aurait
    rechargé, et le marqueur posé ici juste avant ne survivrait pas.
    """
    live.evaluate("() => { window.__temoin = 'vivant'; }")
    live.wait_for_timeout(500)
    assert live.evaluate("() => window.__temoin") == "vivant", (
        "la page s'est rechargée — le POST nu a bien atteint le serveur."
    )
