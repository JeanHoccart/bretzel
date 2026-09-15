"""The drag-and-drop loop, end to end, on the real playground page.

``test_dnd_gesture.py`` drives the runtime against a hand-built DOM : it
proves the *gesture*. This file proves the **loop** — that the components
emit a contract the runtime recognises, that the drop reaches a handler,
that the handler actually mutates, and that a refusal snaps back. None of that is visible from SSR : ``TestClient`` returns 200 with
every attribute in place whether or not a single card can be moved.

Driven with ``page.mouse``, which produces real browser input rather than
synthesised ``PointerEvent``s — so it also exercises the threshold, the
hit-testing and HTMX's own event plumbing.

Run : ``py -m pytest tests/runtime_js/test_dnd_end_to_end.py -q -m browser``
"""

from __future__ import annotations

import pytest

from tests.audit.harness import audit_server, browser_page


@pytest.fixture(scope="module")
def base_url():
    with audit_server() as url:
        yield url


def _labels(page, zone: str) -> list[str]:
    return page.evaluate(
        """(zone) => [...document.querySelectorAll(
              `[data-bz-dropzone="${zone}"] [data-bz-draggable]`)]
            .map(e => e.innerText.trim())""",
        zone,
    )


def _bring_into_view(page, *zones: str) -> None:
    """Scroll the zones into the viewport before measuring anything.

    ``page.mouse`` takes viewport coordinates, and the runtime hit-tests
    with ``document.elementFromPoint`` — which returns ``null`` outside the
    viewport. A drop aimed below the fold therefore lands nowhere, silently:
    the card simply stays where the last in-viewport move put it. That cost
    an hour of chasing a « the card lands one column short » ghost that was
    really « y = 917 in a 900 px viewport ».
    """
    page.evaluate(
        """(zones) => {
            const els = zones.map(z =>
                document.querySelector(`[data-bz-dropzone="${z}"]`));
            els[0].scrollIntoView({block: 'center'});
        }""",
        list(zones),
    )
    page.wait_for_timeout(150)


def _drag(page, zone: str, from_i: int, to_i: int) -> None:
    """Drag item ``from_i`` onto item ``to_i`` with the real mouse."""
    _bring_into_view(page, zone)
    box = page.evaluate(
        """([zone, a, b]) => {
            const items = [...document.querySelectorAll(
                `[data-bz-dropzone="${zone}"] [data-bz-draggable]`)];
            const r1 = items[a].getBoundingClientRect();
            const r2 = items[b].getBoundingClientRect();
            return {
              x1: r1.left + r1.width / 2, y1: r1.top + r1.height / 2,
              x2: r2.left + r2.width / 2,
              // Aim just PAST the middle of the target, on the side we are
              // travelling towards — that is what the insert rule reads.
              y2: b > a ? r2.bottom - 4 : r2.top + 4,
            };
        }""",
        [zone, from_i, to_i],
    )
    page.mouse.move(box["x1"], box["y1"])
    page.mouse.down()
    # Two steps : the first crosses the activation threshold, the second
    # does the hit-testing. One jump would do both at once and hide which
    # of the two failed.
    page.mouse.move(box["x1"], box["y1"] + 12, steps=3)
    page.mouse.move(box["x2"], box["y2"], steps=8)
    page.mouse.up()


def _drag_across(page, from_zone: str, to_zone: str) -> None:
    """Drag the first card of ``from_zone`` into ``to_zone``.

    ⚠️ **The destination is re-measured mid-gesture, and it has to be.**
    Inserting the card into a column reflows every other column, so
    coordinates computed before ``mouse.down()`` are stale by the time the
    pointer arrives — the first version of this helper aimed at « done »
    and reliably dropped into « doing », one column short. Measure after
    the grab, not before.
    """
    _bring_into_view(page, from_zone, to_zone)
    start = page.evaluate(
        """(zone) => {
            // Grab the handle when there is one, the card itself
            // otherwise — `handle=` is per-zone on this bench.
            const card = document.querySelector(
                `[data-bz-dropzone="${zone}"] [data-bz-draggable]`);
            const grip = card.querySelector('[data-bz-drag-handle]') || card;
            const g = grip.getBoundingClientRect();
            return {x: g.left + g.width / 2, y: g.top + g.height / 2};
        }""",
        from_zone,
    )
    page.mouse.move(start["x"], start["y"])
    page.mouse.down()
    page.mouse.move(start["x"], start["y"] + 12, steps=3)

    target = page.evaluate(
        """(zone) => {
            const z = document.querySelector(`[data-bz-dropzone="${zone}"]`);
            const r = z.getBoundingClientRect();
            // Aim at the zone's own lower half rather than at a card :
            // « append to the end » is the one target that stays valid
            // however the column reflowed.
            return {x: r.left + r.width / 2, y: r.bottom - 6};
        }""",
        to_zone,
    )
    page.mouse.move(target["x"], target["y"], steps=10)
    page.mouse.up()


def _capture_action(page) -> tuple[list, list]:
    """Collect the action POST bodies and the HTML the server answers with.

    ⚠️ **Asserting on the DOM after a drop proves almost nothing**, and
    that is worth stating because the obvious test does exactly that : the
    runtime already moved the card optimistically, so the DOM shows the new
    order whether or not the handler ever ran. Only the *response* is the
    server's own word.

    ⚠️ And **do not reach for a reload instead.** ``PageState`` is
    documented as « reset on a full page reload (F5) » — a bench backed by
    it legitimately forgets, so a reload assertion would be testing a
    behaviour the framework deliberately does not have.
    """
    posts: list[str] = []
    bodies: list[str] = []
    page.on(
        "request",
        lambda r: posts.append(r.post_data or "") if "/action/" in r.url else None,
    )

    def _grab(r):
        if "/action/" in r.url:
            try:
                bodies.append(r.text())
            except Exception:  # body already consumed / redirected
                bodies.append("")

    page.on("response", _grab)
    return posts, bodies


def _keys_in(html: str) -> list[str]:
    import re

    return re.findall(r'data-bz-key="([^"]+)"', html)


def test_the_drop_reaches_the_handler_and_the_server_re_renders_reordered(
    base_url: str,
) -> None:
    with browser_page(base_url, "/dnd") as page:
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        posts, bodies = _capture_action(page)

        assert _labels(page, "events") == ["Un", "Deux", "Trois"]
        before_keys = page.evaluate(
            """() => [...document.querySelectorAll(
                  '[data-bz-dropzone="events"] [data-bz-draggable]')]
                .map(e => e.getAttribute('data-bz-key'))"""
        )

        _drag(page, "events", 0, 1)
        page.wait_for_timeout(1500)

        assert posts, "the drop fired no server action at all"
        import json
        import urllib.parse

        form = urllib.parse.parse_qs(posts[0])
        assert "bz_move" in form, (
            f"the POST carried no bz_move field : {sorted(form)} — the "
            f"carrier's payload is not being serialised into the request"
        )
        move = json.loads(form["bz_move"][0])
        assert move["item_key"] == before_keys[0]
        assert (move["from_index"], move["to_index"]) == (0, 1), move
        assert move["from_zone"] == move["to_zone"] == "events", move

        # The server's own render, not the optimistic DOM.
        assert bodies and bodies[0], "no response body captured"
        served = _keys_in(bodies[0])
        assert served[:2] == [before_keys[1], before_keys[0]], (
            f"the server re-rendered the OLD order ({served[:2]}) — the "
            f"handler ran on a payload it could not use, or did not run"
        )
        assert _labels(page, "events") == ["Deux", "Un", "Trois"]
        assert not errors, f"JS errors during the drag : {errors}"


def test_the_first_tab_after_a_cross_zone_drop_is_not_swallowed(base_url: str) -> None:
    with browser_page(base_url, "/dnd") as page:
        _drag_across(page, "todo", "done")
        page.wait_for_timeout(1500)

        anchored = page.evaluate(
            "() => document.activeElement !== document.body"
        )
        assert anchored, "the server morph left sequential focus on BODY"

        page.keyboard.press("Tab")
        first_tab = page.evaluate(
            "() => document.activeElement && document.activeElement.tagName"
        )
        assert first_tab != "BODY", "the first Tab after a drop was swallowed"


def test_a_refused_move_snaps_back(base_url: str) -> None:
    """``move_card`` refuses a third card into « Terminé ». The card must
    return on its own.

    ⚠️ **Ce test ne couvre PAS le refus qui ne mute rien**, contrairement
    à ce que cette docstring a dit jusqu'au 2026-09-09 (« by mutating
    nothing »). Le handler du banc incrémente ``state.refused`` avant de
    sortir : un état change, donc la zone se re-rend, donc le morph
    replace le nœud. Le snap-back mesuré ici vient du COMPTEUR. Le cas
    sans mutation — celui que ``Move`` documente et qu'``examples/crm``
    utilise — est gaté par
    ``test_a_refusal_that_mutates_nothing_snaps_back.py``, et il était
    cassé.

    The bench's rule is a CAPACITY and not a one-way ban, on purpose : the
    first version refused to leave « Terminé », which trapped every card
    for good and read as a broken component rather than as a rule.
    """
    with browser_page(base_url, "/dnd") as page:
        posts, bodies = _capture_action(page)
        todo_before = _labels(page, "todo")
        done_before = _labels(page, "done")
        assert todo_before and done_before, (todo_before, done_before)

        # « Terminé » starts with 1 card and takes 2 : the first move is
        # accepted, the second must be refused. Doing both here is what
        # proves the refusal is the RULE and not a broken transfer.
        _drag_across(page, "todo", "done")
        page.wait_for_timeout(1200)
        assert len(_labels(page, "done")) == len(done_before) + 1, (
            "the accepted transfer did not land — the refusal below would "
            "prove nothing"
        )
        # Re-capture : l'état d'avant le REFUS n'est plus celui d'avant le
        # transfert accepté.
        todo_before = _labels(page, "todo")
        done_before = _labels(page, "done")
        posts.clear()
        bodies.clear()
        _drag_across(page, "todo", "done")

        page.wait_for_timeout(1500)
        assert posts, "the refused drop fired no server action"
        assert bodies and "refus serveur" in bodies[0].lower(), (
            "the handler did not take the refusal branch — the Move it "
            "received did not carry the zones it needed to decide"
        )
        assert _labels(page, "todo") == todo_before, (
            "the refused card did not come back to « Terminé » — the morph "
            "did not undo the optimistic move"
        )
        assert _labels(page, "done") == done_before, (
            "the refused card stayed in done — the server said no and the "
            "morph did not undo it"
        )


def test_a_locked_zone_lets_nothing_out(base_url: str) -> None:
    with browser_page(base_url, "/dnd") as page:
        kept_before = _labels(page, "kept")
        free_before = _labels(page, "free")

        _drag_across(page, "kept", "free")

        assert _labels(page, "kept") == kept_before, (
            "an item left a locked zone — `locked=` is not being honoured "
            "client-side"
        )
        assert _labels(page, "free") == free_before


def test_valid_zones_are_highlighted_during_the_gesture(base_url: str) -> None:
    """Requirement 1 of the cadrage. Asserted mid-gesture on purpose : the
    highlight is gated on an attribute the drag sets and the drop clears,
    so measuring after ``mouse.up()`` would read an empty DOM and pass."""
    with browser_page(base_url, "/dnd") as page:
        _bring_into_view(page, "todo")
        box = page.evaluate(
            """() => {
                const s = document.querySelector(
                    '[data-bz-dropzone="todo"] [data-bz-drag-handle]')
                    .getBoundingClientRect();
                return {x: s.left + s.width / 2, y: s.top + s.height / 2};
            }"""
        )
        page.mouse.move(box["x"], box["y"])
        page.mouse.down()
        page.mouse.move(box["x"], box["y"] + 20, steps=4)

        marked = page.evaluate(
            """() => [...document.querySelectorAll('[data-bz-drop-ok]')]
                    .map(z => z.getAttribute('data-bz-dropzone')).sort()"""
        )
        page.mouse.up()

        assert "todo" in marked and "done" in marked, (
            f"the accepting zones were not highlighted mid-drag : {marked}"
        )
        assert "events" not in marked, (
            f"a zone that does NOT accept group='card' was highlighted : "
            f"{marked} — accepts= is being ignored"
        )
