"""Idiomorph must PAIR reordered nodes by id, never tear them down.

The invariant the whole drag-and-drop primitive rests on (roadmap
§ « Cadrage #6 »). An optimistic drop means the runtime moves the DOM node
*immediately*, before any server answer. Then the zone re-renders and
idiomorph morphs the container against the server's HTML. Two outcomes
must both be correct, and they are the same mechanism :

- **accept** — the server agrees, sends the NEW order → the order holds ;
- **reject** — the server disagrees, sends the OLD order → the item snaps
  back. That is the entirety of the cadrage's « snap-back = simply no
  server mutation. Pas de mécanisme dédié ».

In both cases the moved node must be **the same node**, not a fresh one :
a recreated node loses its ``bz-data`` scope, its open menus, its focus and
its in-flight animations — every drop would reset the client state of the
card being dragged. This is the same identity property that
``render/iteration.py`` already relies on for keyed ``each`` lists, applied
to a node the CLIENT moved rather than the server.

**Why this is a gate and not a one-off probe.** Idiomorph is a third-party
dependency loaded from a CDN and pinned in ``render/shell.py``
(``DEFAULT_IDIOMORPH_URL``). Nothing in this repo would notice if a version
bump changed the pairing strategy — the DnD would just start resetting
cards on every drop, intermittently and invisibly to SSR tests. Measured
green on idiomorph 0.7.3 the 2026-08-10.

**Mutation-tested both ways** the 2026-08-10, and the result says which
assertion carries what :

- morph replaced by a **no-op** → only ``test_rejected_…`` fails. By
  construction the accepted case cannot catch this : the client's optimistic
  order already *is* the order the server sends, so "converged" and "did
  nothing" are indistinguishable there. Never drop the reject test on the
  grounds that it looks like the accept test mirrored — it is the only one
  proving a morph ran at all.
- morph replaced by **``innerHTML =``** (right order, fresh nodes) → *both*
  identity assertions fail. That is the half the ordering assertions cannot
  see, and the half the DnD actually depends on.

Heavier than ``tests/unit`` (uvicorn + Chromium) — run explicitly :
``py -m pytest tests/runtime_js/test_morph_preserves_reordered_nodes.py -q -m browser``
"""

from __future__ import annotations

import pytest

from tests.audit.harness import audit_server, browser_page

# Three children carrying stable ids, the way a keyed ``each`` list carries
# ``bz-id``. Each item is tagged with a JS property : those survive a morph
# **iff** the node is reused, which is exactly what we are measuring (the
# same lever ``test_bzclass_survives_morph`` uses in the other direction).
_SETUP = """
() => {
  const old = document.getElementById('probe-host');
  if (old) old.remove();
  const host = document.createElement('div');
  host.id = 'probe-host';
  host.innerHTML = ['a', 'b', 'c']
    .map(k => "<div id='it-" + k + "'>" + k + "</div>").join('');
  document.body.appendChild(host);
  for (const k of ['a', 'b', 'c']) {
    document.getElementById('it-' + k)._probeTag = 'tag-' + k;
  }
  return true;
}
"""

# The optimistic drop, literally : move C to the front, client-side, with
# no server round-trip. This is what the DnD runtime will do on drop.
_DRAG = """
() => {
  const host = document.getElementById('probe-host');
  host.insertBefore(document.getElementById('it-c'), host.firstChild);
  return [...host.children].map(c => c.id).join(',');
}
"""

_MORPH = """
(order) => {
  const host = document.getElementById('probe-host');
  const html = "<div id='probe-host'>" +
    order.map(k => "<div id='it-" + k + "'>" + k + "</div>").join('') +
    "</div>";
  if (typeof Idiomorph === 'undefined') return {ok: false, why: 'no Idiomorph'};
  Idiomorph.morph(host, html);
  const after = document.getElementById('probe-host');
  return {
    ok: true,
    order: [...after.children].map(c => c.id).join(','),
    // 'RECREATED' = idiomorph replaced the node instead of moving it.
    tags: [...after.children].map(c => c._probeTag || 'RECREATED').join(','),
  };
}
"""


@pytest.fixture(scope="module")
def base_url():
    with audit_server() as url:
        yield url


@pytest.fixture(scope="module")
def page(base_url: str):
    # Any playground page : we only need the runtime and Idiomorph loaded.
    with browser_page(base_url, "/button") as p:
        p.wait_for_function(
            "() => typeof window.$bz !== 'undefined'", timeout=8000
        )
        yield p


def _reorder_then_morph(page, server_order: list[str]) -> dict:
    page.evaluate(_SETUP)
    dragged = page.evaluate(_DRAG)
    assert dragged == "it-c,it-a,it-b", (
        f"probe precondition failed: the client-side move did not happen "
        f"(got {dragged!r})"
    )
    result = page.evaluate(_MORPH, server_order)
    assert result["ok"], result.get("why")
    return result


def test_idiomorph_is_loaded(page) -> None:
    """Floor : the rest of this file measures nothing if the CDN silently
    failed to load — every morph would be a no-op and the order assertions
    would pass on an untouched DOM."""
    assert page.evaluate("() => typeof Idiomorph !== 'undefined'"), (
        "Idiomorph global is absent — the CDN in render/shell.py "
        "(DEFAULT_IDIOMORPH_URL) did not load. This suite proves nothing "
        "in that state."
    )


def test_accepted_drop_keeps_the_new_order_and_the_same_nodes(page) -> None:
    """The server agrees with the optimistic move."""
    result = _reorder_then_morph(page, ["c", "a", "b"])

    assert result["order"] == "it-c,it-a,it-b", (
        "idiomorph did not converge on the server's order after a "
        f"client-side move (got {result['order']!r})"
    )
    assert "RECREATED" not in result["tags"], (
        "idiomorph TORE DOWN a reordered node instead of moving it "
        f"(tags: {result['tags']}). Every drop would reset the dragged "
        "card's bz-data scope, its open menus and its focus."
    )


def test_rejected_drop_snaps_back_and_keeps_the_same_nodes(page) -> None:
    """The server disagrees : it re-sends the original order. This is the
    cadrage's whole snap-back mechanism — no dedicated code path."""
    result = _reorder_then_morph(page, ["a", "b", "c"])

    assert result["order"] == "it-a,it-b,it-c", (
        "the rejected move did NOT snap back — idiomorph left the "
        f"client's optimistic order in place (got {result['order']!r}). "
        "The cadrage's 'snap-back = no server mutation' would not hold."
    )
    assert "RECREATED" not in result["tags"], (
        "idiomorph tore down a node while snapping back "
        f"(tags: {result['tags']})."
    )
