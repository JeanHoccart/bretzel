"""L'inertie d'un contrôle ``aria-disabled`` — les trois canaux, au navigateur.

Depuis le 2026-08-13, « un contrôle désactivé ne fait rien » est une
propriété du **socle**, dérivée du seul ``aria-disabled="true"``, et non
plus quelque chose que chaque composant réinvente. Trois gardes, trois
canaux : les handlers ``bz-on:`` (``02_directives.js``), la navigation
native d'une ancre (idem), l'action serveur (``05_bridge.js``).

Pourquoi ce fichier est INDISPENSABLE et pourquoi il est ici. Aucun test
Python ne peut voir ces trois propriétés : elles ne sont pas dans le HTML
rendu, elles sont dans ce que le navigateur *refuse de faire* avec. C'est
exactement le trou par lequel le bug est passé — ``dropdown_item`` posait
``bz-attr:disabled`` sur un ``<a>``, un attribut sans effet sur une ancre,
et 12 000 tests verts n'en savaient rien.

Chaque test porte son **témoin** : la même action sur un jumeau NON
désactivé. Sans lui, « il ne s'est rien passé » ne distingue pas un garde
qui marche d'un harnais qui n'a rien déclenché — l'erreur exacte qu'un
probe de ce dépôt a déjà commise (cf. ``traps.md`` § getComputedStyle).

⚠️ **``data-bz-sig`` sur les deux boutons n'est pas décoratif.** Depuis
``ad3b7f33`` (2026-08-27), le bridge refuse tout POST dont l'élément n'a
pas de porteur de signature — une action détachée par un morph partait
sinon nue, se faisait refuser par le serveur, et RECHARGEAIT la page.
Ce montage écrit son HTML à la main : sans l'attribut, ses boutons ne
ressemblent à rien que ``action_attrs`` produise, et le TÉMOIN se fait
bloquer par ce garde-là au lieu de poster.

C'est arrivé, et c'est resté rouge deux jours sans que la cause soit
lue : mesuré au navigateur le 2026-08-28, htmx émettait ``confirm`` puis
``configRequest`` pour ``btn-on`` et s'arrêtait — aucun
``beforeRequest``, aucune requête réseau. Le garde d'inertie, lui,
n'avait rien à voir : ``$bz._inert(btn-on)`` valait bien ``false``.

La leçon vaut au-delà de ce fichier : **un montage qui écrit du HTML
htmx à la main doit ressembler à ce que le Python émet**, sinon il
dérive du framework en silence et son rouge accuse le mauvais coupable.

Run : ``py -m pytest tests/runtime_js/test_inert_controls.py -q -m browser``
"""

from __future__ import annotations

import pytest

from tests.audit.harness import audit_server, browser_page

pytestmark = pytest.mark.browser

# Deux jumeaux à chaque fois : l'un inerte, l'autre témoin. Position fixe
# et z-index haut — le layout du playground recouvre le corps de page.
_BUILD = """
() => {
  document.querySelectorAll('.probe-inert').forEach(n => n.remove());
  window.__fired = [];
  const box = document.createElement('div');
  box.className = 'probe-inert';
  box.style.cssText =
    'position:fixed;top:0;left:0;z-index:99999;background:#fff';
  box.innerHTML =
    "<a id='lnk-off'  aria-disabled='true' href='#gone'>off</a>" +
    "<a id='lnk-on'                        href='#gone'>on</a>" +
    "<button id='btn-off' aria-disabled='true' data-bz-sig='probe' " +
    "        hx-post='/_bz_probe_never_exists' hx-swap='none'>off</button>" +
    "<button id='btn-on'                       data-bz-sig='probe' " +
    "        hx-post='/_bz_probe_never_exists' hx-swap='none'>on</button>" +
    "<div bz-data='{}'>" +
    "  <span id='on-off' aria-disabled='true'></span>" +
    "  <span id='on-on'></span>" +
    "</div>";
  document.body.appendChild(box);
  // Les deux <span> reçoivent le MÊME handler bz-on:click, posé après coup
  // pour que le scan du runtime les lie tous les deux.
  ['on-off', 'on-on'].forEach(id => {
    document.getElementById(id)
      .setAttribute('bz-on:click', "window.__fired.push('" + id + "')");
  });
  window.$bz._scan(box);
  window.htmx.process(box);
  document.body.addEventListener('htmx:beforeRequest', (e) => {
    window.__fired.push('POST:' + e.detail.elt.id);
  });
  return true;
}
"""


@pytest.fixture(scope="module")
def page():
    with audit_server() as base_url:
        with browser_page(base_url, "/bottom-bar") as p:
            p.wait_for_function("() => !!window.htmx && !!window.$bz")
            yield p


def _click(page, node_id: str) -> None:
    """Clic DOM et pas clic pointeur : les nœuds injectés sont recouverts
    par le layout, et ce qu'on teste est le traitement de l'ÉVÉNEMENT."""
    page.evaluate(f"() => document.getElementById('{node_id}').click()")


def test_bz_on_handler_does_not_run_on_an_inert_control(page) -> None:
    page.evaluate(_BUILD)
    _click(page, "on-off")
    _click(page, "on-on")
    fired = page.evaluate("() => window.__fired")
    assert "on-on" in fired, (
        "TÉMOIN muet : le jumeau actif n'a pas exécuté son handler non "
        "plus, donc l'absence de l'autre ne prouve rien"
    )
    assert "on-off" not in fired, (
        "un `bz-on:click` s'est exécuté sur un contrôle aria-disabled"
    )


def test_a_server_action_is_aborted_on_an_inert_control(page) -> None:
    page.evaluate(_BUILD)
    _click(page, "btn-off")
    _click(page, "btn-on")
    page.wait_for_timeout(400)
    fired = page.evaluate("() => window.__fired")
    assert "POST:btn-on" in fired, (
        "TÉMOIN muet : le bouton actif n'a pas posté non plus"
    )
    assert "POST:btn-off" not in fired, (
        "une action serveur est partie depuis un contrôle aria-disabled — "
        "le garde `htmx:configRequest` de 05_bridge.js ne mord pas"
    )


def test_native_navigation_is_blocked_on_an_inert_anchor(page) -> None:
    page.evaluate(_BUILD)
    page.evaluate("() => { location.hash = ''; }")
    _click(page, "lnk-off")
    assert page.evaluate("() => location.hash") == "", (
        "une ancre aria-disabled a navigué"
    )
    _click(page, "lnk-on")
    assert page.evaluate("() => location.hash") == "#gone", (
        "TÉMOIN muet : l'ancre ACTIVE n'a pas navigué non plus, donc le "
        "test précédent ne prouve rien sur le garde"
    )


def test_the_guard_reads_the_ancestor_not_just_the_target(page) -> None:
    """Un clic atterrit sur l'ENFANT — l'icône, le label — pas sur le
    contrôle qui porte l'état. Un garde qui lirait ``event.target`` seul
    laisserait passer tous les composants à contenu, c'est-à-dire presque
    tous."""
    page.evaluate(_BUILD)
    page.evaluate("""
      () => {
        const host = document.getElementById('on-off');
        host.innerHTML = "<span id='deep'>x</span>";
        window.$bz._scan(host);
      }
    """)
    page.evaluate("() => document.getElementById('deep').click()")
    assert "on-off" not in page.evaluate("() => window.__fired"), (
        "le handler s'est exécuté pour un clic sur un DESCENDANT d'un "
        "contrôle aria-disabled"
    )
