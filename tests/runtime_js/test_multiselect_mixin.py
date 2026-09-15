"""``$bz.multiSelect`` : l'algèbre d'appartenance partagée garde son
``this``, et les overrides par composant gagnent bien.

Le mixin (audit F19) est **spread** dans deux scopes
(``$bz.select.multi``, ``$bz.combobox.multi``) qui le surchargent
partiellement. Deux choses ne se voient qu'à l'exécution :

1. les méthodes du mixin lisent et écrivent via le ``_read`` / ``_write``
   **du scope appelant** — elles ne savent pas où vit la valeur (signal
   local ou ``$bz.state.X.Y``) ;
2. l'ordre du spread décide qui gagne : ``_selectAll`` / ``_clearAll``
   viennent APRÈS le spread dans les deux scopes, donc les variantes
   par composant écrasent — Combobox filtre par ce que la requête laisse
   visible et remet ``query`` à zéro, Select non.

Un spread mal ordonné ne casse ni la syntaxe, ni le SSR, ni les tests
Python : le composant se met juste à sélectionner les mauvaises options.

Lourd (uvicorn + Chromium) — à lancer explicitement ::

    py -m pytest tests/runtime_js/test_multiselect_mixin.py -q -m browser
"""

from __future__ import annotations

import pytest

from tests.audit.harness import audit_server, browser_page


@pytest.fixture(scope="module")
def base_url():
    with audit_server() as url:
        yield url


def test_mixin_reads_and_writes_through_the_calling_scope(
    base_url: str,
) -> None:
    with browser_page(base_url, "/select") as page:
        page.wait_for_function(
            "() => !!(window.$bz && $bz.select && $bz.combobox)", timeout=5000)
        r = page.evaluate(
            """() => {
                // Un scope minimal, greffé comme les slabs le font.
                const mk = (proto, opts) => {
                    const s = Object.create(proto);
                    s._store = [];
                    s._read = function () { return this._store; };
                    s._write = function (v) { this._store = v; };
                    s._options = opts;
                    s._value = function () {
                        const v = this._read();
                        return v == null ? [] : v;
                    };
                    s.open = true;
                    return s;
                };
                const out = {};
                const sel = mk($bz.select.multi, ['a', 'b', 'c']);

                sel._togglePick('a');
                sel._togglePick('b');
                out.after_two = sel._picked();
                out.is_picked = sel._isPicked('a');
                out.has_picked = sel._hasPicked();
                sel._togglePick('a');                 // re-toggle = retire
                out.after_untoggle = sel._picked();
                sel._removeOne('b');
                out.after_remove = sel._picked();
                out.empty_now = sel._hasPicked();
                sel._setValue('solo');                // scalaire → liste
                out.set_scalar = sel._picked();
                sel._setValue(null);
                out.set_null = sel._picked();

                // Override par composant : Select prend TOUTES les options.
                sel._selectAll();
                out.select_all = sel._picked();
                sel._clearAll();
                out.select_cleared = sel._picked();
                out.select_closed = sel.open;

                // Combobox : _selectAll ne prend que le visible, et
                // _clearAll remet la requête à zéro.
                const combo = mk($bz.combobox.multi,
                    [{value: 'x'}, {value: 'y'}, {value: 'z'}]);
                combo.query = 'zz';
                combo._visibleIndices = function () { return [0, 2]; };
                combo._selectAll();
                out.combo_visible_only = combo._picked();
                combo._clearAll();
                out.combo_query_reset = combo.query;
                return out;
            }"""
        )

    assert r["after_two"] == ["a", "b"], (
        f"_togglePick n'écrit pas dans le scope appelant : {r['after_two']}"
    )
    assert r["is_picked"] is True and r["has_picked"] is True
    assert r["after_untoggle"] == ["b"], "re-toggle doit retirer la valeur"
    assert r["after_remove"] == [] and r["empty_now"] is False
    assert r["set_scalar"] == ["solo"], (
        f"_setValue(scalaire) doit donner une liste à 1 élément : "
        f"{r['set_scalar']}"
    )
    assert r["set_null"] == [], "_setValue(null) doit vider"

    assert r["select_all"] == ["a", "b", "c"], (
        f"l'override _selectAll de Select doit gagner sur le mixin : "
        f"{r['select_all']}"
    )
    assert r["select_cleared"] == [], r["select_cleared"]
    # ⚠️ Le panneau doit rester OUVERT. Cette assertion exigeait
    # l'inverse jusqu'au 2026-08-10 : elle datait d'avant le
    # 2026-08-06, où le ``this.open = false`` a été RETIRÉ de
    # ``_clearAll`` exprès — « un panneau doit survivre à ses propres
    # commandes d'en-tête », et fermer ici POSTAIT la sélection vide au
    # serveur quand un ``on_close=`` était câblé (cf. le docstring de
    # ``$bz.multiSelect`` dans 06_helpers.js). Le test était donc rouge
    # depuis quatre jours sans que rien ne le dise : la suite navigateur
    # ne tourne pas dans le sous-ensemble rapide.
    assert r["select_closed"] is True, (
        "_clearAll a refermé le panneau — la fermeture a été retirée le "
        "2026-08-06, une commande d'en-tête ne congédie pas ce qu'elle "
        "commande"
    )
    assert r["combo_visible_only"] == ["x", "z"], (
        "l'override _selectAll de Combobox doit gagner et ne prendre que "
        f"les options visibles — got {r['combo_visible_only']}"
    )
    assert r["combo_query_reset"] == "", (
        "_clearAll de Combobox doit aussi vider la requête"
    )
