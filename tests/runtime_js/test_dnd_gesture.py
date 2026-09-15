"""The node-DnD gesture engine (``19_dnd.js``), driven by real pointer events.

Exercises the runtime **before** any component emits its markup : the module
reads a DOM contract (``data-bz-dropzone`` / ``data-bz-draggable`` / …), so
it can be tested against a hand-built DOM that honours that contract. That
keeps this file about the *gesture* — activation, hover-insert, drop payload,
cancel — and leaves markup questions to the component tests.

Why real ``PointerEvent``s and not calls into ``$bz.dnd`` : the activation
rules ARE the feature. « souris = seuil de mouvement, tactile = appui long
avec tolérance » only means something if a 3-pixel mouse drag does *not*
grab and a fast touch swipe does *not* grab. Calling ``begin()`` directly
would assert nothing about either.

Run : ``py -m pytest tests/runtime_js/test_dnd_gesture.py -q -m browser``
"""

from __future__ import annotations

import pytest

from tests.audit.harness import audit_server, browser_page

# A zone with three stacked items. Explicit heights so elementFromPoint has
# real geometry to hit — the module derives its axis from measured boxes.
_BUILD = """
() => {
  const old = document.getElementById('dz');
  if (old) old.remove();
  const zone = document.createElement('div');
  zone.id = 'dz';
  zone.setAttribute('data-bz-dropzone', 'tasks');
  zone.style.cssText =
    'position:fixed;top:0;left:0;width:200px;background:#fff;z-index:99999';
  zone.innerHTML =
    ['a', 'b', 'c'].map(k =>
      "<div data-bz-draggable data-bz-key='" + k + "' id='it-" + k + "' " +
      "style='height:60px;background:#eee;border:1px solid #999'>" + k +
      "</div>").join('') +
    "<input type='hidden' data-bz-move-carrier id='carrier'>";
  document.body.appendChild(zone);
  return true;
}
"""

_ORDER = """
() => [...document.querySelectorAll('#dz [data-bz-draggable]')]
        .map(e => e.getAttribute('data-bz-key')).join('')
"""


def _pointer(page, kind: str, x: float, y: float, *, ptype: str = "mouse") -> None:
    """Dispatch one real PointerEvent at viewport coords."""
    page.evaluate(
        """([kind, x, y, ptype]) => {
            const target = document.elementFromPoint(x, y) || document.body;
            target.dispatchEvent(new PointerEvent(kind, {
                pointerId: 1, pointerType: ptype, button: 0, buttons: 1,
                clientX: x, clientY: y, bubbles: true, cancelable: true,
            }));
        }""",
        [kind, x, y, ptype],
    )


@pytest.fixture(scope="module")
def base_url():
    with audit_server() as url:
        yield url


@pytest.fixture(scope="module")
def page(base_url: str):
    with browser_page(base_url, "/button") as p:
        p.wait_for_function("() => window.$bz && window.$bz.dnd", timeout=8000)
        yield p


@pytest.fixture(autouse=True)
def fresh_zone(page):
    page.evaluate(_BUILD)
    yield


def test_the_module_is_loaded(page) -> None:
    """Floor : without ``$bz.dnd`` every assertion below would be measuring
    an inert DOM and passing for the wrong reason."""
    assert page.evaluate("() => typeof window.$bz.dnd === 'object'"), (
        "$bz.dnd is absent — 19_dnd.js did not reach the bundle. Run "
        "`py -m bretzel.runtime._build`."
    )


def test_a_small_mouse_move_does_not_grab(page) -> None:
    """The movement threshold is what preserves the CLICK. Without it every
    click on a card would start a drag."""
    _pointer(page, "pointerdown", 100, 30)
    _pointer(page, "pointermove", 102, 32)   # 2px — under MOUSE_THRESHOLD_PX
    state = page.evaluate("() => !!window.$bz.dnd._state().active")
    _pointer(page, "pointerup", 102, 32)

    assert not state, (
        "a 2-pixel mouse move started a drag — the click is no longer "
        "usable on any draggable card"
    )


def test_mouse_drag_reorders_and_fills_the_carrier(page) -> None:
    """A → past B's middle → the DOM order changes, and the payload the
    server will receive is read FROM that order."""
    assert page.evaluate(_ORDER) == "abc"

    _pointer(page, "pointerdown", 100, 30)    # grab A (0-60)
    _pointer(page, "pointermove", 100, 40)    # past the 5px threshold
    _pointer(page, "pointermove", 100, 100)   # past B's middle (60-120 → 90)
    order_during = page.evaluate(_ORDER)
    _pointer(page, "pointerup", 100, 100)

    payload = page.evaluate(
        "() => document.getElementById('carrier').value"
    )

    assert order_during == "bac", (
        f"the node did not follow the pointer during the drag (got "
        f"{order_during!r}) — the optimistic preview is broken"
    )
    assert page.evaluate(_ORDER) == "bac", "the drop undid the preview"
    assert payload, "no Move payload was written to the carrier"

    import json

    move = json.loads(payload)
    assert move["item_key"] == "a"
    assert move["from_index"] == 0
    assert move["to_index"] == 1, (
        f"the payload disagrees with the DOM the user is looking at: {move}"
    )
    assert move["from_zone"] == "tasks" and move["to_zone"] == "tasks"


def test_escape_puts_the_item_back(page) -> None:
    _pointer(page, "pointerdown", 100, 30)
    _pointer(page, "pointermove", 100, 40)
    _pointer(page, "pointermove", 100, 100)
    assert page.evaluate(_ORDER) == "bac", "precondition: the drag moved A"

    page.keyboard.press("Escape")

    assert page.evaluate(_ORDER) == "abc", (
        "Escape did not restore the original position"
    )
    assert not page.evaluate("() => !!window.$bz.dnd._state().active")


def test_a_drop_that_changes_nothing_sends_nothing(page) -> None:
    """Picking a card up and putting it back must not cost a round-trip."""
    _pointer(page, "pointerdown", 100, 30)
    _pointer(page, "pointermove", 100, 40)
    _pointer(page, "pointermove", 100, 20)    # still inside A's own slot
    _pointer(page, "pointerup", 100, 20)

    assert page.evaluate(_ORDER) == "abc"
    assert page.evaluate("() => document.getElementById('carrier').value") == "", (
        "an inert drag still wrote a Move — the server would re-render for "
        "nothing on every mis-click"
    )


def test_a_fast_touch_swipe_does_not_grab(page) -> None:
    """The touch tolerance is what preserves SCROLL. A finger flicking down
    a list must not carry off the card it brushed."""
    _pointer(page, "pointerdown", 100, 30, ptype="touch")
    _pointer(page, "pointermove", 100, 60, ptype="touch")   # >> tolerance
    grabbed = page.evaluate("() => !!window.$bz.dnd._state().active")
    armed = page.evaluate("() => !!window.$bz.dnd._state().armed")
    _pointer(page, "pointerup", 100, 60, ptype="touch")

    assert not grabbed, "a touch swipe grabbed the card instead of scrolling"
    assert not armed, (
        "the gesture is still armed after the finger moved past the "
        "tolerance — the hold timer will fire and grab a card the user "
        "already stopped touching"
    )


def test_items_nested_under_a_layout_wrapper_still_reorder(page) -> None:
    """Items are NOT necessarily direct children of their zone.

    A dropzone arranges nothing — callers stack their items with the
    container they already use (``ui.vstack``, ``ui.grid``), so in real
    markup there is a wrapper between the zone and the items. Inserting
    relative to the *zone* then throws outright (``insertBefore: the node
    … is not a child of this node``) and the drag dies mid-gesture.

    Found on the playground bench, invisible to every other test in this
    file because they all build items as direct children.
    """
    page.evaluate(
        """() => {
            const old = document.getElementById('dz2');
            if (old) old.remove();
            const zone = document.createElement('div');
            zone.id = 'dz2';
            zone.setAttribute('data-bz-dropzone', 'nested');
            zone.style.cssText =
              'position:fixed;top:0;left:300px;width:200px;background:#fff;'
              + 'z-index:99999';
            zone.innerHTML =
              "<div class='wrapper'>" +
              ['a', 'b', 'c'].map(k =>
                "<div data-bz-draggable data-bz-key='" + k + "' " +
                "style='height:60px;background:#eee'>" + k + "</div>").join('') +
              "</div><input type='hidden' data-bz-move-carrier id='carrier2'>";
            document.body.appendChild(zone);
        }"""
    )
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))

    _pointer(page, "pointerdown", 400, 30)
    _pointer(page, "pointermove", 400, 40)
    _pointer(page, "pointermove", 400, 100)
    order = page.evaluate(
        """() => [...document.querySelectorAll(
              '#dz2 [data-bz-draggable]')]
            .map(e => e.getAttribute('data-bz-key')).join('')"""
    )
    _pointer(page, "pointerup", 400, 100)

    assert not errors, f"the nested drag threw : {errors}"
    assert order == "bac", (
        f"a nested item did not reorder (got {order!r}) — insertion is "
        f"being done relative to the zone instead of the item's own parent"
    )


def test_the_preview_follows_the_pointer_and_is_anonymous(page) -> None:
    """A drag must show something « in hand ».

    Without the flying clone only the *list* moves — neighbours shift
    aside — and the gesture reads as a cursor wandering over a page that
    happens to rearrange itself. That is precisely how it was reported.

    The identity assertions are not cosmetic : a clone that kept its
    ``id`` / ``bz-id`` would give idiomorph two candidates for one target
    at the next morph, and a kept ``data-bz-draggable`` would corrupt the
    indices ``itemsOf`` reads — so the payload would describe a list that
    does not exist.
    """
    _pointer(page, "pointerdown", 100, 30)
    _pointer(page, "pointermove", 100, 40)
    first = page.evaluate(
        """() => {
            const p = document.querySelector('.bz-drag-preview');
            if (!p) return null;
            const r = p.getBoundingClientRect();
            return {
              left: r.left, top: r.top, width: Math.round(r.width),
              hasId: !!p.id || p.hasAttribute('bz-id'),
              nestedIds: p.querySelectorAll('[id],[bz-id]').length,
              stillDraggable: p.hasAttribute('data-bz-draggable')
                || p.querySelectorAll('[data-bz-draggable]').length > 0,
              hitTestable: getComputedStyle(p).pointerEvents !== 'none',
            };
        }"""
    )
    _pointer(page, "pointermove", 100, 120)
    moved = page.evaluate(
        """() => {
            const p = document.querySelector('.bz-drag-preview');
            return p ? p.getBoundingClientRect().top : null;
        }"""
    )
    _pointer(page, "pointerup", 100, 120)
    after = page.evaluate("() => !!document.querySelector('.bz-drag-preview')")

    assert first, "no drag preview was created — nothing follows the pointer"
    assert first["width"] > 0, "the preview collapsed to zero width"
    assert not first["hasId"] and first["nestedIds"] == 0, (
        "the preview kept an id — idiomorph would have two candidates for "
        "one target at the next morph"
    )
    assert not first["stillDraggable"], (
        "the preview still declares data-bz-draggable — it would be counted "
        "as a real item and corrupt from_index / to_index"
    )
    assert not first["hitTestable"], (
        "the preview is hit-testable — elementFromPoint would only ever "
        "see it, and the card would never land anywhere"
    )
    assert moved is not None and moved > first["top"] + 40, (
        f"the preview did not follow the pointer ({first['top']} → {moved})"
    )
    assert not after, "the preview outlived the drop"


def test_a_disabled_item_cannot_be_grabbed(page) -> None:
    """The inertia of ``disabled=`` lives in the RUNTIME, not in CSS.

    Worth its own test because the theme deliberately does NOT carry
    ``pointer-events-none`` : putting it on the same element as
    ``cursor-not-allowed`` cancels the cursor (an element that receives no
    pointer events never paints one) — the trap
    ``test_disabled_affordance`` documents and the Tree once shipped. So
    the only thing stopping the drag is the ``pointerdown`` guard, and if
    that guard ever goes, nothing else catches it.
    """
    page.evaluate(
        """() => document.querySelector('#dz [data-bz-draggable]')
                 .setAttribute('data-bz-disabled', 'true')"""
    )
    _pointer(page, "pointerdown", 100, 30)
    _pointer(page, "pointermove", 100, 40)
    _pointer(page, "pointermove", 100, 100)
    grabbed = page.evaluate("() => !!window.$bz.dnd._state().active")
    order = page.evaluate(_ORDER)
    _pointer(page, "pointerup", 100, 100)

    assert not grabbed, "a disabled item was picked up"
    assert order == "abc", f"a disabled item was moved (got {order!r})"


def test_a_two_item_horizontal_row_reorders(page) -> None:
    """L'axe est LU sur deux boîtes réelles, item tiré compris.

    Le détecteur excluait l'item en vol, donc une rangée de DEUX n'avait
    plus qu'un repère et retombait sur l'axe vertical : la comparaison se
    faisait sur un Y que les deux cartes partagent, et l'échange
    n'arrivait jamais. Toute liste horizontale passe par deux items.
    """
    page.evaluate(
        """() => {
            const old = document.getElementById('h'); if (old) old.remove();
            const z = document.createElement('div');
            z.id = 'h'; z.setAttribute('data-bz-dropzone', 'H');
            z.style.cssText = 'position:fixed;top:0;left:0;display:flex;'
                            + 'background:#fff;z-index:99999';
            z.innerHTML = ['a', 'b'].map(k =>
                "<div data-bz-draggable data-bz-key='" + k + "' style='width:120px;"
                + "height:60px;background:#eee;border:1px solid #999'>" + k
                + "</div>").join('')
                + "<input type='hidden' data-bz-move-carrier id='hc'>";
            document.body.appendChild(z);
        }"""
    )
    axis = page.evaluate("() => $bz.dnd._axisOf(document.getElementById('h'))")
    _pointer(page, "pointerdown", 60, 30)
    _pointer(page, "pointermove", 70, 30)
    _pointer(page, "pointermove", 220, 30)
    _pointer(page, "pointerup", 220, 30)
    order = page.evaluate(
        """() => [...document.querySelectorAll('#h [data-bz-draggable]')]
                .map(e => e.getAttribute('data-bz-key')).join('')"""
    )
    assert axis == "x", f"axe déduit {axis!r} sur une rangée horizontale"
    assert order == "ba", (
        f"la rangée horizontale de deux items n'a pas été réordonnée "
        f"(got {order!r})"
    )


def test_a_nested_zone_does_not_steal_its_parents_payload(page) -> None:
    """Le carrier est cherché par ``querySelector``, qui fouille TOUT le
    sous-arbre — et le carrier d'une zone imbriquée précède forcément
    celui du parent, puisqu'il est rendu en dernier. Sans filtre par
    ``zoneOf``, un drop dans la zone extérieure partait au handler de la
    zone intérieure et mutait la mauvaise liste."""
    page.evaluate(
        """() => {
            const old = document.getElementById('outer'); if (old) old.remove();
            const z = document.createElement('div');
            z.id = 'outer'; z.setAttribute('data-bz-dropzone', 'OUTER');
            z.style.cssText = 'position:fixed;top:200px;left:0;width:240px;'
                            + 'background:#fff;z-index:99999';
            z.innerHTML =
              "<div data-bz-dropzone='INNER'>"
              + "<input type='hidden' data-bz-move-carrier id='in-c'></div>"
              + "<div data-bz-draggable data-bz-key='a' style='height:60px;"
              + "background:#eee'>a</div>"
              + "<div data-bz-draggable data-bz-key='b' style='height:60px;"
              + "background:#ddd'>b</div>"
              + "<input type='hidden' data-bz-move-carrier id='out-c'>";
            document.body.appendChild(z);
        }"""
    )
    _pointer(page, "pointerdown", 120, 230)
    _pointer(page, "pointermove", 120, 240)
    _pointer(page, "pointermove", 120, 315)
    _pointer(page, "pointerup", 120, 315)
    res = page.evaluate(
        """() => ({inner: document.getElementById('in-c').value,
                   outer: document.getElementById('out-c').value})"""
    )
    assert res["inner"] == "", (
        "la zone IMBRIQUÉE a reçu le payload du parent — son handler "
        "aurait muté la mauvaise liste"
    )
    assert '"to_zone":"OUTER"' in res["outer"], (
        f"la zone extérieure n'a pas reçu son Move : {res['outer']!r}"
    )


def test_a_touch_hold_grabs(page) -> None:
    """The other half of the same rule : held still, it must grab."""
    _pointer(page, "pointerdown", 100, 30, ptype="touch")
    page.wait_for_function(
        "() => !!window.$bz.dnd._state().active", timeout=2000
    )
    _pointer(page, "pointermove", 100, 100, ptype="touch")
    _pointer(page, "pointerup", 100, 100, ptype="touch")

    assert page.evaluate(_ORDER) == "bac", (
        "a held touch did not produce a drag — the gesture is unusable on "
        "the one input type the user's browser reports"
    )
