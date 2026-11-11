"""The element fingerprints behind a patched zone (``render/zone_diff.py``)."""

from __future__ import annotations

from bretzel.core.tree import Element, Node, TextNode
from bretzel.render.zone_diff import (
    Fingerprinter,
    Patch,
    ZoneMaps,
    ZonePrint,
    ZoneVersion,
    changes,
    stamp_zones,
)
from bretzel.runtime.protocol import DATA_BZ_SIG, DATA_BZ_TS, DATA_ZONE, DATA_ZONE_HASH


def row(i: int, text: str = "", **attrs: str) -> Element:
    return Element("div", {"id": f"row-{i}", **attrs}, (TextNode(text or f"r{i}"),))


def zone(*rows: Element, zone_attrs: dict | None = None) -> Element:
    body = Element("div", {"id": "rows"}, rows)
    return Element("div", {"id": "z", DATA_ZONE: "", **(zone_attrs or {})}, (body,))


FP = Fingerprinter()


def spelled(where: dict[str, str]) -> str:
    """An address as ``anchor/0/1``."""
    return "/".join([where["anchor"], *where["path"].split(".")]) if where["path"] else where["anchor"]


def shipped(patch: Patch) -> list[str]:
    """The morphed elements: by ``id``, or by position spelled ``anchor/0/1``."""
    return [e.attrs["id"] for e in patch.morphs] + [spelled(w) for w, _ in patch.placed]


def found(before: Element, after: Element) -> Patch | None:
    return changes(FP.zone(after), after, ZoneVersion.of(FP.zone(before)))


def diff(before: Element, after: Element) -> list[str] | None:
    """The morphed elements — ``None`` when the zone ships whole."""
    patch = found(before, after)
    return None if patch is None else shipped(patch)


def digest(tree: Element, fp: Fingerprinter = FP) -> str:
    return fp.zone(tree).digest


def test_one_changed_row_is_the_only_patch() -> None:
    before = zone(row(1), row(2), row(3))
    after = zone(row(1), row(2, "changed"), row(3))
    assert diff(before, after) == ["row-2"]


def test_the_same_render_patches_nothing() -> None:
    tree = zone(row(1), row(2))
    assert diff(tree, tree) == []


def test_a_new_row_is_inserted_into_its_parent() -> None:
    """The list of ``rows`` changed (one more child), nothing else: a list
    patch, not the parent (cf. the list tests below)."""
    patch = found(zone(row(1), row(2)), zone(row(1), row(2), row(3)))
    assert patch is not None and shipped(patch) == []
    assert [lst.ops for lst in patch.lists] == [["#row-1", "#row-2", "n"]]


def test_a_root_change_ships_the_zone_whole() -> None:
    before = zone(row(1))
    after = zone(row(1), zone_attrs={"class": "other"})
    assert diff(before, after) is None


def test_an_unknown_copy_ships_the_zone_whole() -> None:
    tree = zone(row(1))
    assert changes(FP.zone(tree), tree, ZoneVersion({}, {})) is None


def test_signature_and_render_second_are_not_content() -> None:
    """A button signed one second later is the same button: counted, a
    zone with one clickable element never looked unchanged."""
    def with_button(ts: str, sig: str) -> Element:
        button = Element("button", {"id": "b", "hx-post": "/_bretzel/action/m::f",
                                    DATA_BZ_TS: ts, DATA_BZ_SIG: sig}, ())
        return zone(row(1), button)

    assert digest(with_button("1000", "aaaa")) == digest(with_button("1001", "bbbb"))


def test_an_idempotent_action_keeps_its_timestamp() -> None:
    """Its timestamp is the deduplication key: a re-rendered button must
    get a fresh one, as before the patches."""
    fp = Fingerprinter(is_idempotent=lambda action_id: action_id == "m::pay")

    def with_button(ts: str) -> Element:
        return zone(Element("button", {"id": "b", "hx-post": "/_bretzel/action/m::pay",
                                       DATA_BZ_TS: ts}, ()))

    assert digest(with_button("1000"), fp) != digest(with_button("1001"), fp)


def test_an_expiring_signature_is_resent_by_half_windows() -> None:
    fp = Fingerprinter(action_max_age=60)

    def with_button(ts: str) -> Element:
        return zone(Element("button", {"id": "b", "hx-post": "/_bretzel/action/m::f",
                                       DATA_BZ_TS: ts}, ()))

    assert digest(with_button("60"), fp) == digest(with_button("89"), fp)
    assert digest(with_button("60"), fp) != digest(with_button("90"), fp)


def test_a_repeated_id_ships_the_zone_whole_but_can_stay_silent() -> None:
    printed = FP.zone(zone(row(1), row(1)))
    assert printed.elements is None and printed.digest


def test_ids_under_a_template_are_not_targets() -> None:
    """A template's content is inert or moved by the runtime: a patch
    aimed at it would find nothing. Its change ships the ancestor."""
    def with_template(text: str) -> Element:
        template = Element("template", {}, (row(9, text),))
        return zone(Element("div", {"id": "holder"}, (template,)))

    before, after = with_template("a"), with_template("b")
    assert "row-9" not in FP.zone(after).elements
    assert diff(before, after) == ["holder"]


def test_an_id_in_a_teleported_panel_ships_alone() -> None:
    """A ``bz-teleport`` template's content lives under ``<body>``, where
    ``getElementById`` finds it: a box ticked in an open popover ships
    alone, not the popover."""
    def popover(checked: str) -> Element:
        box = Element("input", {"id": "box", "type": "checkbox", "data-checked": checked}, ())
        panel = Element("div", {"role": "dialog"}, (Element("label", {}, (box,)),))
        template = Element("template", {"bz-teleport": "body"}, (panel,))
        return zone(Element("div", {"id": "pop"}, (template,)))

    assert diff(popover("true"), popover("false")) == ["box"]


def test_a_teleported_panel_is_never_walked_by_position() -> None:
    """Its children are not the template's children in the DOM: a change
    with no id around it ships the overlay, never a walk that misses."""
    def popover(text: str) -> Element:
        panel = Element("div", {"role": "dialog"}, (Element("p", {}, (TextNode(text),)),))
        template = Element("template", {"bz-teleport": "body", "id": "tpl"}, (panel,))
        return zone(Element("div", {"id": "pop"}, (template,)))

    assert diff(popover("a"), popover("b")) == ["tpl"]


def test_ids_inside_an_svg_are_not_targets() -> None:
    """Sent alone, an SVG part would parse as HTML: its change ships the
    whole <svg>."""
    def with_svg(color: str) -> Element:
        gradient = Element("linearGradient", {"id": "g", "data-c": color}, ())
        return zone(Element("div", {"id": "chart"}, (Element("svg", {}, (gradient,)),)))

    # The <svg> itself ships (by position), never one of its parts.
    assert diff(with_svg("red"), with_svg("blue")) == ["chart/0"]


def test_the_stamp_is_not_content() -> None:
    assert digest(zone(row(1))) == digest(zone(row(1), zone_attrs={DATA_ZONE_HASH: "abc"}))


def test_a_full_render_stamps_and_caches_its_zones() -> None:
    maps = ZoneMaps()
    page = Element("main", {}, (zone(row(1)),))
    (out,) = stamp_zones([page], FP, maps)
    stamp = out.children[0].attrs[DATA_ZONE_HASH]
    assert maps.get(stamp) is not None


def test_the_cache_drops_the_oldest_versions_first() -> None:
    def version(name: str) -> ZonePrint:
        return ZonePrint(digest=name, elements={"x": b"1", "y": b"2"})

    maps = ZoneMaps(max_elements=4)
    maps.put(version("a"))
    maps.put(version("b"))
    maps.get("a")
    maps.put(version("c"))
    assert maps.get("b") is None
    assert maps.get("a") is not None and maps.get("c") is not None


# ── Elements with no id, found by position ─────────────────────────────


def card(title: str, body: str) -> Element:
    """A zone whose inside carries no id at all — the ticket panel's case."""
    header = Element("header", {}, (Element("h2", {}, (TextNode(title),)),))
    main = Element("section", {}, (Element("p", {}, (TextNode(body),)),
                                   Element("p", {}, (TextNode("static"),))))
    return Element("div", {"id": "z", DATA_ZONE: ""}, (header, main))


def test_a_changed_element_without_id_ships_alone_by_position() -> None:
    """Before, the zone shipped whole: nothing inside had an id."""
    assert diff(card("T", "one"), card("T", "two")) == ["z/1/0"]


def test_a_child_that_changes_tag_is_morphed_in_its_list() -> None:
    """The parent's shape changed, its frame did not: the child is
    replaced in place, ``m0`` — the parent itself is found by the shapes
    ABOVE it, which did not move."""
    def tree(tag: str) -> Element:
        inner = Element(tag, {}, (Element("b", {}, (TextNode("x"),)),))
        box = Element("section", {}, (inner,))
        return Element("div", {"id": "z", DATA_ZONE: ""}, (box, Element("hr", {}, ())))

    assert lists(tree("p"), tree("div")) == ([], [("z/0", 1, ["m0"])])


def test_positions_skip_fragments_like_the_dom() -> None:
    from bretzel.core.tree import FragmentNode

    def tree(text: str) -> Element:
        frag = FragmentNode((Element("i", {}, (TextNode("a"),)),
                             Element("b", {}, (Element("em", {}, (TextNode(text),)),))))
        return Element("div", {"id": "z", DATA_ZONE: ""}, (frag,))

    assert diff(tree("x"), tree("y")) == ["z/1/0"]


def test_raw_markup_stops_the_walk_and_bz_if_is_not_counted() -> None:
    """Raw markup may hold elements the browser counts: the parent ships.
    A ``bz-if`` element is mounted by the runtime, which marks it and
    skips it: the server does not count it either."""
    from bretzel.core.tree import HtmlNode

    def tree(text: str, extra: Node) -> Element:
        item = Element("p", {}, (Element("span", {}, (TextNode(text),)),))
        box = Element("div", {"id": "box"}, (extra, item))
        return Element("div", {"id": "z", DATA_ZONE: ""}, (box,))

    raw = HtmlNode("<span>raw</span>")
    assert diff(tree("x", raw), tree("y", raw)) == ["box"]
    cond = Element("span", {"bz-if": "open"}, ())
    assert diff(tree("x", cond), tree("y", cond)) == ["box/0/0"]


def test_an_id_inside_a_custom_element_stays_addressable() -> None:
    """A custom element builds its own content: no walk by position
    inside it, but an ``id`` there is still found by the browser."""
    def tree(text: str) -> Element:
        named = Element("span", {"id": "named"}, (TextNode(text),))
        widget = Element("bz-widget", {"id": "w"}, (Element("div", {}, (named,)),))
        return Element("div", {"id": "z", DATA_ZONE: ""}, (widget, Element("hr", {}, ())))

    assert diff(tree("x"), tree("y")) == ["named"]


# ── A list that changed: patched, not shipped whole (2026-10-26) ──────
#
# A layout editor: removing one table out of 30 shipped the whole
# room, 320 KB. The parent now receives a list patch — keep, morph,
# insert — in any configuration.


def lists(before: Element, after: Element) -> tuple[list[str], list[tuple[str, int, list[str]]]] | None:
    """``(morphed elements, [(parent, count before, ops)])`` — positions
    spelled ``anchor/0/1``."""
    patch = found(before, after)
    if patch is None:
        return None
    return shipped(patch), [(spelled(p.where), p.count, p.ops) for p in patch.lists]


def replay(old: list[str], ops: list[str], new: list[str]) -> list[str]:
    """What the browser holds after the ops: the kept old children and
    the inserted ones, in order (an inserted or morphed child is taken
    from ``new`` at its place)."""
    return [new[i] if op == "n" or op[0] == "m" else op[1:] if op[0] == "#"
            else old[int(op[1:])] for i, op in enumerate(ops)]


def test_a_new_row_is_inserted_not_its_parent_shipped() -> None:
    assert lists(zone(row(1), row(2)), zone(row(1), row(2), row(3))) == (
        [], [("rows", 0, ["#row-1", "#row-2", "n"])])


def test_a_removed_row_goes_alone() -> None:
    assert lists(zone(row(1), row(2), row(3)), zone(row(1), row(3))) == (
        [], [("rows", 0, ["#row-1", "#row-3"])])


def test_a_kept_row_that_changed_is_diffed_like_any_element() -> None:
    assert lists(zone(row(1), row(2)), zone(row(1), row(2, "changed"), row(3))) == (
        ["row-2"], [("rows", 0, ["#row-1", "#row-2", "n"])])


def test_children_without_id_are_matched_by_content() -> None:
    """Tables addressed by position: the same holds."""
    def box(*texts: str) -> Element:
        kids = tuple(Element("div", {}, (TextNode(t),)) for t in texts)
        return Element("div", {"id": "z", DATA_ZONE: ""}, (Element("div", {"id": "box"}, kids),))

    assert lists(box("a", "b", "c"), box("a", "c")) == ([], [("box", 3, ["k0", "k2"])])
    assert lists(box("a", "c"), box("a", "b", "c")) == ([], [("box", 2, ["k0", "n", "k1"])])


def test_the_root_list_is_patched_too() -> None:
    def root(*rows: Element) -> Element:
        return Element("div", {"id": "z", DATA_ZONE: ""}, rows)

    assert lists(root(row(1), row(2)), root(row(2))) == ([], [("z", 0, ["#row-2"])])


def test_a_parent_that_changed_itself_still_ships_whole() -> None:
    before = zone(row(1), row(2))
    body = Element("div", {"id": "rows", "class": "new"}, (row(1),))
    after = Element("div", {"id": "z", DATA_ZONE: ""}, (body,))
    assert lists(before, after) == (["rows"], [])


def test_a_template_among_the_children_ships_the_parent() -> None:
    def tree(*rows: Element) -> Element:
        body = Element("div", {"id": "rows"}, (Element("template", {}, ()), *rows))
        return Element("div", {"id": "z", DATA_ZONE: ""}, (body,))

    assert lists(tree(row(1)), tree(row(1), row(2))) == (["rows"], [])


def test_any_reshuffle_replays_to_the_new_list() -> None:
    """Random inserts, removals and moves: replayed in order, the ops
    always give the new list — the claim the runtime relies on."""
    import random

    rng = random.Random(2026_10_26)
    for _ in range(300):
        old = [f"r{i}" for i in rng.sample(range(30), rng.randint(0, 12))]
        new = [k for k in old if rng.random() > 0.3]
        rng.shuffle(new) if rng.random() < 0.3 else None
        for extra in rng.sample(range(30, 60), rng.randint(0, 4)):
            new.insert(rng.randint(0, len(new)), f"r{extra}")

        def tree(keys: list[str]) -> Element:
            body = Element("div", {"id": "rows"}, tuple(
                Element("div", {"id": k}, (TextNode(k),)) for k in keys))
            return Element("div", {"id": "z", DATA_ZONE: ""}, (body,))

        found = lists(tree(old), tree(new))
        assert found is not None
        _, patches = found
        if old == new:
            assert patches == []
            continue
        if not patches:   # an empty list either side: the parent may ship
            continue
        (_, count, ops), = patches
        assert count == 0          # every child has an id: no rank
        assert replay(old, ops, new) == new, (old, new, ops)


def test_children_whose_ids_slid_with_their_rank_are_noted() -> None:
    """Without ``key=``, the ids inside a child follow its rank: remove
    the first, the others are kept for their content and their ids slide
    — noted, so ``partials`` can warn when a client state sits there.
    Children with nothing named by rank inside slide nothing."""
    def ranked(*texts: str) -> Element:
        kids = tuple(Element("div", {}, (Element("span", {"id": f"s-{i}"}, (TextNode(t),)),))
                     for i, t in enumerate(texts))
        return Element("div", {"id": "z", DATA_ZONE: ""}, (Element("div", {"id": "box"}, kids),))

    patch = found(ranked("a", "b", "c"), ranked("b", "c"))
    assert patch is not None
    assert [(spelled(w), e.children[0].attrs["id"]) for w, e in patch.slid] == [
        ("box", "s-0"), ("box", "s-1")]

    def plain(*texts: str) -> Element:
        kids = tuple(Element("div", {}, (TextNode(t),)) for t in texts)
        return Element("div", {"id": "z", DATA_ZONE: ""}, (Element("div", {"id": "box"}, kids),))

    patch = found(plain("a", "b", "c"), plain("b", "c"))
    assert patch is not None and patch.slid == []


def test_each_parent_shape_is_computed_once(monkeypatch) -> None:
    """A shape is a pass over all of a parent's children: computed again
    for each element sent below it, 375 changed cells under one grid cost
    1 500 shapes and 363 ms."""
    from bretzel.render import zone_diff

    def tree(changed: set[int]) -> Element:
        cells = tuple(Element("div", {}, (Element("b", {}, (TextNode("x" if i in changed else "."),)),))
                      for i in range(60))
        grid = Element("div", {"class": "grid"}, cells)
        return Element("div", {"id": "z", DATA_ZONE: ""}, (Element("section", {}, (grid,)),))

    calls: list[int] = []
    real = zone_diff.shape_of
    monkeypatch.setattr(zone_diff, "shape_of", lambda e: calls.append(1) or real(e))
    patch = found(tree(set()), tree(set(range(0, 60, 2))))
    assert patch is not None and len(patch.placed) == 30
    # One per distinct level: the zone, the section, the grid, and each
    # changed cell.
    assert len(calls) == 3 + 30, f"{len(calls)} shapes for 33 levels"


def test_an_id_htmx_cannot_select_ships_by_position() -> None:
    """``id="137"`` is legal HTML, and ``querySelectorAll("#137")`` throws:
    htmx would drop the whole response. Measured on the component audit,
    74 of 75 components red (a custom ``id`` cycled to ``"137"``)."""
    def tree(ident: str, text: str) -> Element:
        inner = Element("span", {"id": ident}, (TextNode(text),))
        return Element("div", {"id": "z", DATA_ZONE: ""}, (Element("p", {}, (inner,)),))

    assert diff(tree("137", "one"), tree("137", "two")) == ["z/0/0"]
    assert diff(tree("a 1", "one"), tree("a 1", "two")) == ["z/0/0"]
    assert diff(tree("x137", "one"), tree("x137", "two")) == ["x137"]
