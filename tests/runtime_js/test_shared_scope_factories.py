"""Les factories de scope partagées gardent leur ``this`` — vérifié dans
un vrai moteur JS.

Trois helpers ont été extraits de copies jumelles (audit F18, F59, F60,
F61) : ``seriesVisibility`` (visibilité par série des légendes),
``$bz.num.cachedPrecision`` (le memo step→décimales) et
``$bz.helpers.emitChange``. Les deux premiers **lisent et écrivent ``this``**
— ``this.visible``, ``this._precCache``, ``this._step`` — donc la façon
dont ils sont greffés sur le scope décide s'ils marchent :

- ``_precision: $bz.num.cachedPrecision`` est une référence de fonction
  posée dans un objet littéral : appelée en ``this._precision()``, elle
  reçoit le scope. Bien.
- ``vis.toggleSeries.call(this, i)`` dans le wrapper de lineScope : sans
  le ``.call(this, …)``, la fonction muterait l'objet interne de la
  factory et le graphique ne bougerait pas.

``node --check`` ne voit rien de tout ça, et le SSR non plus : c'est du
comportement runtime pur. D'où ce probe, qui exerce les factories
directement (aucune dépendance à la structure d'une page).

Lourd (uvicorn + Chromium) — à lancer explicitement ::

    py -m pytest tests/runtime_js/test_shared_scope_factories.py -q -m browser
"""

from __future__ import annotations

import pytest

from tests.audit.harness import audit_server, browser_page


@pytest.fixture(scope="module")
def base_url():
    with audit_server() as url:
        yield url


def test_series_visibility_keeps_its_scope(base_url: str) -> None:
    with browser_page(base_url, "/line_chart") as page:
        page.wait_for_function("() => !!(window.$bz && $bz.charts)", timeout=5000)
        r = page.evaluate(
            """() => {
                const line = $bz.charts.lineScope({n_series: 3});
                const scatter = $bz.charts.scatterScope({n_series: 3});
                const out = {};

                out.line_initial = line.visible.slice();
                out.line_isVisible = line.isVisible(1);
                // Hover series 1, then hide it : line's own extra is to
                // drop the hover index when its series goes away.
                line.active = 1;
                line.toggleSeries(1);
                out.line_after_hide = line.visible.slice();
                out.line_active_reset = line.active;
                // The shared guard : never toggle the last one off.
                line.toggleSeries(2);
                out.line_after_second = line.visible.slice();
                line.toggleSeries(0);
                out.line_last_one_kept = line.visible.slice();

                out.scatter_initial = scatter.visible.slice();
                scatter.toggleSeries(0);
                out.scatter_after_hide = scatter.visible.slice();
                return out;
            }"""
        )

    assert r["line_initial"] == [True, True, True]
    assert r["line_isVisible"] is True
    assert r["line_after_hide"] == [True, False, True], (
        "toggleSeries n'a pas muté le scope de l'appelant — le `.call(this)` "
        f"du wrapper de lineScope est perdu ({r['line_after_hide']})"
    )
    assert r["line_active_reset"] == -1, (
        "l'index de hover doit retomber à -1 quand sa série est cachée "
        f"(extra propre à lineScope) — got {r['line_active_reset']}"
    )
    assert r["line_after_second"] == [True, False, False]
    assert r["line_last_one_kept"] == [True, False, False], (
        "la garde « jamais toute la légende éteinte » a sauté : "
        f"{r['line_last_one_kept']}"
    )
    assert r["scatter_initial"] == [True, True, True]
    assert r["scatter_after_hide"] == [False, True, True], (
        "scatterScope réutilise toggleSeries tel quel — il doit muter le "
        f"scope rendu par la factory ({r['scatter_after_hide']})"
    )


def test_cached_precision_reads_the_calling_scope(base_url: str) -> None:
    with browser_page(base_url, "/number_input") as page:
        page.wait_for_function("() => !!(window.$bz && $bz.num)", timeout=5000)
        r = page.evaluate(
            """() => {
                // Greffé comme les slabs le font : une référence de
                // fonction dans un objet littéral.
                const scope = {_step: 0.01, _precision: $bz.num.cachedPrecision};
                const first = scope._precision();
                const second = scope._precision();      // sert le memo
                const other = {_step: 5, _precision: $bz.num.cachedPrecision};
                return {
                    first, second, cached: scope._precCache,
                    other: other._precision(),
                    // Le memo vit-il bien sur le scope appelant, et pas
                    // sur la fonction partagée ?
                    isolated: other._precCache,
                };
            }"""
        )
    assert r["first"] == 2 and r["second"] == 2, (
        f"step=0.01 doit donner 2 décimales — got {r['first']}/{r['second']}"
    )
    assert r["cached"] == 2, "le memo doit s'écrire sur le scope appelant"
    assert r["other"] == 0 and r["isolated"] == 0, (
        "deux scopes doivent avoir des caches indépendants — le memo "
        f"fuit d'un scope à l'autre ({r['other']}/{r['isolated']})"
    )


def test_emit_change_fires_the_named_event(base_url: str) -> None:
    with browser_page(base_url, "/slider") as page:
        page.wait_for_function("() => !!(window.$bz && $bz.num)", timeout=5000)
        r = page.evaluate(
            """() => {
                const el = document.createElement('input');
                document.body.appendChild(el);
                const seen = [];
                el.addEventListener('change', () => seen.push('change'));
                el.addEventListener('bzchange', () => seen.push('bzchange'));
                $bz.helpers.emitChange(el);                  // slider : natif
                $bz.helpers.emitChange(el, 'bzchange');      // number_input
                $bz.helpers.emitChange(null);                // no carrier : no-op
                return new Promise(r => queueMicrotask(() =>
                    queueMicrotask(() => r(seen))));
            }"""
        )
    assert r == ["change", "bzchange"], (
        f"emitChange doit émettre l'event demandé, différé au microtask — {r}"
    )
