"""The element fingerprints behind a patched zone (``render/zone_diff.py``)."""

from __future__ import annotations

from bretzel.core.tree import Element, Node, TextNode
from bretzel.render.zone_diff import (
    Fingerprinter,
    ZoneMaps,
    ZonePrint,
    changed_elements,
    stamp_zones,
)
from bretzel.runtime.protocol import DATA_BZ_SIG, DATA_BZ_TS, DATA_ZONE, DATA_ZONE_HASH


def row(i: int, text: str = "", **attrs: str) -> Element:
    return Element("div", {"id": f"row-{i}", **attrs}, (TextNode(text or f"r{i}"),))


def zone(*rows: Element, zone_attrs: dict | None = None) -> Element:
    body = Element("div", {"id": "rows"}, rows)
    return Element("div", {"id": "z", DATA_ZONE: "", **(zone_attrs or {})}, (body,))


FP = Fingerprinter()


def diff(before: Element, after: Element) -> list[str] | None:
    """The shipped elements, by ``id`` — or by position, spelled
    ``anchor/0/1``."""
    patch = changed_elements(FP.zone(after), after, FP.zone(before).elements)
    return None if patch is None else [k.replace("\x1f", "/") for k in patch]


def digest(tree: Element, fp: Fingerprinter = FP) -> str:
    return fp.zone(tree).digest


def test_one_changed_row_is_the_only_patch() -> None:
    before = zone(row(1), row(2), row(3))
    after = zone(row(1), row(2, "changed"), row(3))
    assert diff(before, after) == ["row-2"]


def test_the_same_render_patches_nothing() -> None:
    tree = zone(row(1), row(2))
    assert diff(tree, tree) == []


def test_a_new_row_ships_its_parent() -> None:
    """The skeleton of ``rows`` changed (one more child): the row alone
    would have nowhere to land."""
    before = zone(row(1), row(2))
    after = zone(row(1), row(2), row(3))
    assert diff(before, after) == ["rows"]


def test_a_root_change_ships_the_zone_whole() -> None:
    before = zone(row(1))
    after = zone(row(1), zone_attrs={"class": "other"})
    assert diff(before, after) is None


def test_an_unknown_copy_ships_the_zone_whole() -> None:
    tree = zone(row(1))
    assert changed_elements(FP.zone(tree), tree, {}) is None


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


# ── refresh(zone, rows=[…]) — the row patch ─────────────────────────────

from bretzel.render.zone_diff import RowReport, ZoneVersion, row_patch  # noqa: E402


def held_version(*rows: Element) -> ZoneVersion:
    return ZoneVersion.of(FP.zone(zone(*rows)))


def report(order: list[int], rendered: dict[int, str] | None = None,
           missing: list[int] = ()) -> RowReport:
    rendered = rendered or {}
    return RowReport(
        supported=True, prefix="row-",
        wanted={f"row-{i}" for i in (*rendered, *missing)},
        order=[f"row-{i}" for i in order],
        rendered={f"row-{i}": row(i, text) for i, text in rendered.items()},
    )


def patch_of(reports: list[RowReport], held: ZoneVersion):
    return row_patch(reports, held, "base", FP)


def test_a_changed_row_is_the_only_patch() -> None:
    patched = patch_of([report([1, 2, 3], {2: "changed"})], held_version(row(1), row(2), row(3)))
    assert patched is not None
    assert [p.attrs["id"] for p in patched.rows] == ["row-2"] and patched.removed == []
    assert patched.version.elements["row-2"] == FP.zone(row(2, "changed")).elements["row-2"]


def test_a_row_that_left_the_list_is_removed() -> None:
    patched = patch_of([report([1, 3], missing=[2])], held_version(row(1), row(2), row(3)))
    assert patched is not None
    assert patched.rows == [] and patched.removed == ["row-2"]
    assert "row-2" not in patched.version.elements
    assert patched.version.children["rows"] == ("row-1", "row-3")


def test_a_new_row_or_a_new_order_ships_the_zone_whole() -> None:
    held = held_version(row(1), row(2))
    assert patch_of([report([1, 2, 3], {3: "new"})], held) is None
    assert patch_of([report([2, 1], {1: "moved"})], held) is None


def test_a_table_without_row_keys_ships_the_zone_whole() -> None:
    assert patch_of([RowReport(supported=False)], held_version(row(1))) is None


def test_the_patched_version_still_diffs_right_against_a_whole_render() -> None:
    """The ancestors' fingerprints are left stale on purpose: the next
    whole diff must still find exactly what changed since."""
    held = held_version(row(1), row(2), row(3))
    version = patch_of([report([1, 2, 3], {2: "changed"})], held).version
    fresh = zone(row(1), row(2, "changed"), row(3, "later"))
    patch = changed_elements(FP.zone(fresh), fresh, version.elements)
    assert patch == ["row-3"]



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


def test_a_child_that_changes_tag_ships_its_parent() -> None:
    """The parent's shape changed: the runtime would not find its way."""
    def tree(tag: str) -> Element:
        inner = Element(tag, {}, (Element("b", {}, (TextNode("x"),)),))
        box = Element("section", {}, (inner,))
        return Element("div", {"id": "z", DATA_ZONE: ""}, (box, Element("hr", {}, ())))

    assert diff(tree("p"), tree("div")) == ["z/0"]


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
