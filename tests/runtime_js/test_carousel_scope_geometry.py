"""Le scope partagé du Carousel — géométrie lue du DOM, dans un vrai
moteur de rendu.

Ce que ce probe protège n'existe **qu'à l'exécution, et qu'avec une mise
en page réelle**. Le HTML rendu ne contient que `goTo(2)` et `_atEnd()` ;
ce que ces appels valent dépend de largeurs, de gaps et de positions que
seul un navigateur qui a fait un layout connaît. Ni le SSR, ni
`node --check`, ni un test Python ne peuvent y toucher.

Trois invariants s'y jouent, et chacun casse en silence :

1. **La foulée est l'écart entre DEUX slides, gap compris.** Prendre la
   largeur d'une seule slide donne un résultat juste tant qu'il n'y a pas
   de gap — donc juste sur l'exemple qu'on teste à la main, et faux de
   `N × gap` sur toute galerie espacée. L'erreur s'accumule : invisible à
   la slide 1, franche à la slide 6.
2. **La borne vient de `scrollWidth - clientWidth`**, pas d'un
   `len(slides) - per_view`. C'est ce qui rend le `per_view` responsive
   gratuit — le JS ne connaît aucun breakpoint. Un retour au calcul
   ferait dériver les flèches désactivées dès que CSS ne dit pas la même
   chose que Python.
3. **L'écriture d'index est débouncée.** Sans ça, un défilement fluide de
   0 à 3 publie 1 puis 2 en passant — et sur un `value` lié au serveur,
   chaque valeur intermédiaire part en `change`.

Le probe monte une piste SYNTHÉTIQUE aux dimensions choisies et y greffe
le scope partagé : il teste la géométrie, pas la structure d'une page
(même forme que ``test_shared_scope_factories``).

Lourd (uvicorn + Chromium) — à lancer explicitement ::

    py -m pytest tests/runtime_js/test_carousel_scope_geometry.py -q -m browser
"""

from __future__ import annotations

import pytest

from tests.audit.harness import audit_server, browser_page

#: Monte une piste réelle (400 px de large, slides de 200 px, gap de 20)
#: et y greffe le scope partagé. ``scrollTo`` est remplacé par une
#: écriture SYNCHRONE de ``scrollLeft`` : on teste les décisions du
#: scope, pas l'animation du navigateur.
_MAKE = """
(opts) => {
  const o = Object.assign({slides: 5, w: 200, gap: 20, view: 400}, opts || {});
  const track = document.createElement('div');
  track.style.cssText =
    'display:flex;overflow-x:auto;width:' + o.view + 'px;gap:' + o.gap + 'px';
  for (let i = 0; i < o.slides; i++) {
    const s = document.createElement('div');
    s.style.cssText = 'flex:0 0 auto;width:' + o.w + 'px;height:40px';
    track.appendChild(s);
  }
  document.body.appendChild(track);
  track.__calls = [];
  track.scrollTo = (arg) => {
    track.__calls.push(arg);
    track.scrollLeft = arg.left;            // synchrone, pas d'animation
  };
  const scope = Object.assign(Object.create($bz.carousel.scope), {
    v: o.value || 0,
    _track: track,
    _read() { return this.v; },
    _write(x) { this.v = x; },
  });
  return {scope, track};
}
"""


@pytest.fixture(scope="module")
def base_url():
    with audit_server() as url:
        yield url


@pytest.fixture(scope="module")
def page(base_url: str):
    with browser_page(base_url, "/carousel") as p:
        p.wait_for_function("() => !!(window.$bz && $bz.carousel)", timeout=5000)
        yield p


def test_step_includes_the_gap(page) -> None:
    r = page.evaluate(
        f"""() => {{
            const make = {_MAKE};
            return {{
                with_gap: make({{w: 200, gap: 20}}).scope._step(),
                no_gap:   make({{w: 200, gap: 0}}).scope._step(),
            }};
        }}"""
    )
    assert r["with_gap"] == 220, (
        "la foulée doit être l'écart entre DEUX slides, gap compris — "
        f"got {r['with_gap']}, ce qui décale de 20 px par slide"
    )
    assert r["no_gap"] == 200


def test_max_index_comes_from_the_scroll_extent(page) -> None:
    # 5 slides de 200 + 4 gaps de 20 = 1080 de contenu dans 400 visibles
    # → 680 de course, soit 3 foulées de 220 (arrondi).
    r = page.evaluate(
        f"""() => {{
            const make = {_MAKE};
            const {{scope, track}} = make({{slides: 5, w: 200, gap: 20, view: 400}});
            return {{
                max: scope._maxIndex(),
                scrollable: track.scrollWidth - track.clientWidth,
            }};
        }}"""
    )
    assert r["scrollable"] > 0
    assert r["max"] == 3, (
        "la borne doit venir de scrollWidth - clientWidth, pas d'un "
        f"len(slides) - per_view — got {r['max']}"
    )


def test_everything_fits_means_no_bound(page) -> None:
    r = page.evaluate(
        f"""() => {{
            const make = {_MAKE};
            // 2 slides de 100 dans 400 visibles : rien ne dépasse.
            return make({{slides: 2, w: 100, gap: 0, view: 400}}).scope._maxIndex();
        }}"""
    )
    assert r == 0, f"rien à faire défiler → borne 0, got {r}"


def test_goto_clamps_to_the_real_bound(page) -> None:
    r = page.evaluate(
        f"""() => {{
            const make = {_MAKE};
            const {{scope, track}} = make({{}});
            scope.goTo(99);
            const over = track.scrollLeft;
            scope.goTo(-5);
            return {{over, under: track.scrollLeft, max: scope._maxIndex()}};
        }}"""
    )
    assert r["over"] == r["max"] * 220, (
        f"goTo(99) doit s'arrêter à la borne réelle : {r}"
    )
    assert r["under"] == 0


def test_next_and_prev_wrap(page) -> None:
    r = page.evaluate(
        f"""() => {{
            const make = {_MAKE};
            const {{scope, track}} = make({{}});
            const seen = [];
            scope.v = scope._maxIndex();
            scope.next();
            seen.push(track.scrollLeft);      // bouclé au début
            scope.v = 0;
            scope.prev();
            seen.push(track.scrollLeft);      // bouclé à la fin
            return {{seen, max: scope._maxIndex()}};
        }}"""
    )
    assert r["seen"][0] == 0, (
        "next() au bout doit revenir au début — c'est ce qui fait qu'une "
        f"rotation automatique reste une rotation : {r}"
    )
    assert r["seen"][1] == r["max"] * 220, (
        f"prev() à 0 doit repartir de la fin : {r}"
    )


def test_bounds_drive_the_arrow_disabled_state(page) -> None:
    r = page.evaluate(
        f"""() => {{
            const make = {_MAKE};
            const {{scope}} = make({{}});
            const out = {{}};
            scope.v = 0;
            out.start = [scope._atStart(), scope._atEnd()];
            scope.v = 1;
            out.middle = [scope._atStart(), scope._atEnd()];
            scope.v = scope._maxIndex();
            out.end = [scope._atStart(), scope._atEnd()];
            return out;
        }}"""
    )
    assert r["start"] == [True, False]
    assert r["middle"] == [False, False]
    assert r["end"] == [False, True]


#: Hydrater un vrai carousel dans un shadow root : les feuilles de style
#: du document n'y entrent pas, donc le composant se retrouve exactement
#: dans l'état « le CSS n'est pas encore arrivé » — piste en ``block``,
#: slides empilées, donc ``scrollWidth === clientWidth``. C'est la seule
#: façon de reproduire la course sans dépendre d'un timing.
#:
#: Le ``bz-id`` est effacé sur tout le sous-arbre, sinon ``_ensureScope``
#: REUTILISERAIT le scope du carousel d'origine (il est keyé par cette
#: chaîne, pas par le nœud) et le clone piloterait la piste de l'autre.
_HYDRATE_UNSTYLED = """
() => {
  const src = document.querySelector('[aria-roledescription="carousel"]');
  const clone = src.cloneNode(true);
  for (const el of [clone].concat(Array.from(clone.querySelectorAll('*')))) {
    el.removeAttribute('bz-id');
  }
  const host = document.createElement('div');
  host.id = 'unstyled-host';
  host.style.cssText = 'position:fixed;left:0;top:0;width:600px';
  host.attachShadow({mode: 'open'}).appendChild(clone);
  document.body.appendChild(host);
  $bz._scan(clone);
  const t = clone.querySelector('[bz-ref=bztrack]');
  return {
    track: t,
    arrows: () => Array.from(
      clone.querySelectorAll('button[aria-label$="slide"]')
    ).map(a => a.disabled),
  };
}
"""


def test_arrows_recover_when_the_layout_arrives_after_hydration(page) -> None:
    """La régression qui a coûté une session de debug.

    Symptôme : à la PREMIÈRE visite, aucune flèche ; au refresh, elles
    sont là. Cause : la borne est mesurée, une mesure n'est pas un
    signal, et ``bz-attr:disabled`` n'avait pour seule dépendance
    réactive que ``_read()`` — donc une seule évaluation, au scan, avec
    la mise en page de cet instant. Sans CSS appliqué la piste n'est pas
    ``flex`` : rien ne dépasse, la borne vaut 0, les DEUX flèches
    passent ``disabled``, et ``disabled:opacity-0`` les efface pour de
    bon. Le refresh « réparait » parce qu'il rejouait la course, que le
    compilateur Tailwind du mode dev gagne à chaud et perd à froid.

    Ce que ce probe verrouille n'est donc pas « les flèches sont
    justes » — l'autre probe s'en charge — mais **les flèches se
    RATTRAPENT**. C'est un test de rattrapage : il exige qu'un état faux
    au scan soit corrigé quand la géométrie devient vraie.
    """
    page.evaluate("() => document.getElementById('unstyled-host')?.remove()")
    before = page.evaluate(
        f"""() => {{
            const {{track, arrows}} = ({_HYDRATE_UNSTYLED})();
            return {{
                arrows: arrows(),
                scrollable: track.scrollWidth - track.clientWidth,
                display: getComputedStyle(track).display,
            }};
        }}"""
    )
    assert before["display"] == "block", (
        "le shadow root doit VRAIMENT priver le composant de ses styles, "
        f"sinon le probe ne reproduit rien — display={before['display']!r}"
    )
    assert before["scrollable"] == 0
    assert before["arrows"] == [True, True], (
        "sans mise en page il n'y a rien à faire défiler : les deux "
        f"flèches DOIVENT être désactivées à ce stade — {before['arrows']}"
    )

    after = page.evaluate(
        """() => {
            // Le CSS arrive : on sort le clone du shadow root.
            const host = document.getElementById('unstyled-host');
            const clone = host.shadowRoot.querySelector('[bz-data]');
            const light = document.createElement('div');
            light.style.cssText = 'position:fixed;left:0;top:0;width:600px';
            light.appendChild(clone);
            document.body.appendChild(light);
            const t = clone.querySelector('[bz-ref=bztrack]');
            return new Promise(res => setTimeout(() => res({
                arrows: Array.from(
                    clone.querySelectorAll('button[aria-label$="slide"]')
                ).map(a => a.disabled),
                scrollable: t.scrollWidth - t.clientWidth,
                display: getComputedStyle(t).display,
            }), 400));
        }"""
    )
    assert after["display"] == "flex" and after["scrollable"] > 0, (
        f"la piste doit être devenue défilable : {after}"
    )
    assert after["arrows"] == [True, False], (
        "la géométrie dit maintenant qu'il y a où aller — la flèche "
        "suivante doit s'être RALLUMÉE toute seule. Restée désactivée = "
        "la mesure n'est de nouveau lue qu'une fois, et le bug « aucune "
        f"flèche à la première visite » est revenu : {after['arrows']}"
    )


def test_scroll_writes_once_when_the_position_settles(page) -> None:
    r = page.evaluate(
        f"""() => {{
            const make = {_MAKE};
            const {{scope, track}} = make({{}});
            let writes = 0;
            scope._write = function (x) {{ writes++; this.v = x; }};
            // Un défilement fluide traverse plusieurs positions.
            for (const left of [40, 110, 180, 220, 300, 440]) {{
              track.scrollLeft = left;
              scope._onScroll();
            }}
            return new Promise(r => setTimeout(
              () => r({{writes, value: scope.v}}), 300));
        }}"""
    )
    assert r["writes"] == 1, (
        "l'écriture doit être débouncée : sans ça un défilement de 0 à 2 "
        f"publie chaque position traversée, et un value lié au serveur "
        f"part en change à chacune — got {r['writes']} écritures"
    )
    assert r["value"] == 2, (
        f"la valeur publiée est la position d'ARRIVÉE : {r['value']}"
    )


def test_first_sync_is_instant_then_smooth(page) -> None:
    r = page.evaluate(
        f"""() => {{
            const make = {_MAKE};
            const {{scope, track}} = make({{value: 2}});
            scope._syncFromValue();          // premier accord
            const first = track.__calls[0];
            scope.v = 0;
            scope._syncFromValue();          // écrivain externe
            return {{
                first: first && first.behavior,
                second: track.__calls[1] && track.__calls[1].behavior,
            }};
        }}"""
    )
    assert r["first"] == "auto", (
        "un carousel rendu à value=2 doit S'AFFICHER sur la slide 2, pas "
        f"y défiler sous les yeux au chargement — got {r['first']!r}"
    )
    assert r["second"] == "smooth", (
        f"les accords suivants sont animés — got {r['second']!r}"
    )


def test_sync_is_a_no_op_when_already_there(page) -> None:
    # La garde qui empêche la boucle avec ``_onScroll``.
    r = page.evaluate(
        f"""() => {{
            const make = {_MAKE};
            const {{scope, track}} = make({{value: 0}});
            scope._syncFromValue();
            scope._syncFromValue();
            return track.__calls.length;
        }}"""
    )
    assert r == 0, (
        f"déjà en place → aucun scrollTo, sinon _onScroll et l'effet se "
        f"relanceraient l'un l'autre : {r} appel(s)"
    )
