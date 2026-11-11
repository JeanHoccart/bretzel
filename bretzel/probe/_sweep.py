"""The free sweep — what nobody rewrites, so nobody forgets.

It runs when the ``with`` exits, on every window, without a probe having
to ask for it.

What it does NOT do, and why: the "distinct colours" and "distinct
sizes" probes of ``creating-a-component.md`` § 9 compare the VARIANTS of
a component mounted on its own. They make no sense on an assembled app,
where there are no two variants to compare. They stay with the component
harness; claiming them here would make two green lines that measure
nothing.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from bretzel.probe._window import Window

#: What the sweep can do with a finding. It receives the function, not
#: the ``Probe``: a policy does not consume the object calling it.
#: Without that, a deferred import was needed "to break a cycle" that did
#: not exist.
Check = Callable[[str, bool, object], None]

#: C1 — "the SMALLEST plausible window, never the largest". Measuring at
#: 1500×940 validates the size where everything fits. The second size is
#: not a luxury: a probe's "every column fits" may hold at its own size
#: only.
SECOND_SIZE = (1366, 640)

#: ⚠️ A RAW string: the JS below carries regular expressions, and a
#: ``\s`` interpreted by Python would arrive at the browser as a literal
#: space — a syntax error at evaluation time, so a sweep that RAISES
#: instead of measuring.
_GEOMETRY_JS = r"""
() => {
    const doc = document.documentElement;
    const vw = doc.clientWidth, vh = doc.clientHeight;
    const scrollers = [];
    const clipped = [];
    const scrolls = (el) => /auto|scroll/.test(getComputedStyle(el).overflowY)
        && el.clientHeight > 0 && el.scrollHeight > el.clientHeight + 1;
    // A region inside a region that scrolls is CAUGHT when that one, scrolled
    // to its end, shows its bottom: the page's ``ui.pane`` brings a plan as
    // tall as the screen into view. Measured at its ancestor's end, not
    // where the scroll stands: otherwise the verdict goes with wherever
    // the 20th Tab of ``_tab_order`` left the page.
    const caught = (el, r) => {
        let up = el.parentElement;
        while (up && up !== document.body && !scrolls(up)) up = up.parentElement;
        if (!up || up === document.body) return false;
        const left = up.scrollHeight - up.clientHeight - up.scrollTop;
        const shown = up.getBoundingClientRect().top + up.clientTop + up.clientHeight;
        return r.bottom - left <= shown + 1;
    };
    for (const el of document.querySelectorAll('*')) {
        const st = getComputedStyle(el);
        const overflows = el.scrollHeight > el.clientHeight + 1
            && el.clientHeight > 0;
        if (/auto|scroll/.test(st.overflowY) && overflows
            && !caught(el, el.getBoundingClientRect())) {
            const r = el.getBoundingClientRect();
            scrollers.push({
                tag: el.tagName.toLowerCase(),
                cls: (el.getAttribute('class') || '').slice(0, 60),
                bottom: Math.round(r.bottom),
            });
        }
        // Clipped FOR GOOD: no scrollbar, no recourse. The 2 px margin
        // sets aside the sub-pixel rounding of a line of text, which
        // hides nothing. A box of 1 px both ways is hidden ON PURPOSE —
        // ``sr-only``: a native input a component drives, a label for
        // screen readers — and shows nothing a reader would miss.
        const visuallyHidden = el.clientWidth <= 1 && el.clientHeight <= 1;
        if (/hidden|clip/.test(st.overflowY)
            && el.clientHeight > 0
            && !visuallyHidden
            && el.scrollHeight > el.clientHeight + 2
            && el.offsetParent !== null) {
            clipped.push({
                tag: el.tagName.toLowerCase(),
                cls: (el.getAttribute('class') || '').slice(0, 40),
                shown: el.clientHeight,
                needed: el.scrollHeight,
                text: (el.innerText || '').split('\n')[0].slice(0, 30),
            });
        }
    }
    return {
        overflowX: Math.max(0, doc.scrollWidth - vw),
        documentScrolls: doc.scrollHeight > vh + 1,
        viewport: [vw, vh],
        scrollers: scrollers.slice(0, 12),
        clipped: clipped.slice(0, 8),
    };
}
"""

_TAB_JS = """
() => {
    const el = document.activeElement;
    if (!el || el === document.body) return null;
    const r = el.getBoundingClientRect();
    return {
        tag: el.tagName.toLowerCase(),
        x: Math.round(r.x), y: Math.round(r.y),
        w: Math.round(r.width), h: Math.round(r.height),
        closed: el.closest('[data-bz-overlay][data-open="false"]') !== null,
    };
}
"""


def sweep(
    windows: Sequence[Window],
    size: tuple[int, int],
    check: Check,
) -> None:
    """Measure every window, at two sizes and in both themes.

    The window is already at its first size, so it is not resized before
    the first measure, and the two theme toggles are not waited for: they
    mutate no DOM, and a screenshot synchronises itself on the render.
    """
    for window in windows:
        # Once only, to absorb what the scenario left in flight. The
        # waits that follow FOLLOW NO GESTURE, so they have no floor to
        # pay.
        window.settle(timeout=2.0)
        _errors_and_requests(check, window)
        _tab_order(check, window)

        _geometry(check, window, f"size-1 {size[0]}×{size[1]}")
        window.resize(SECOND_SIZE)
        window.settle(timeout=2.0, floor=0)
        _geometry(check, window, f"size-2 {SECOND_SIZE[0]}×{SECOND_SIZE[1]}")
        window.resize(size)

        # C4 — light first: it is the one an author who codes in dark
        # never looks at.
        for theme in ("light", "dark"):
            window.page.emulate_media(color_scheme=theme)
            window.shot(theme)


def _errors_and_requests(check: Check, window: Window) -> None:
    check(
        f"[{window.name}] aucune erreur JS",
        not window.errors,
        window.errors[:3],
    )
    check(
        f"[{window.name}] no failed request",
        not window.broken,
        window.broken[:3],
    )
    check(
        f"[{window.name}] aucun avertissement de console",
        not window.console,
        window.console[:3],
    )


def _geometry(check: Check, window: Window, label: str) -> None:
    geo: dict[str, Any] = window.page.evaluate(_GEOMETRY_JS)
    check(
        f"[{window.name}] {label} — the page does not overflow sideways",
        geo["overflowX"] == 0,
        f"{geo['overflowX']} px too many",
    )
    if not geo["documentScrolls"]:
        # FROZEN document: every scrolling region must end ABOVE the
        # edge. A region overflowing at the bottom has nothing to catch it.
        # One that a scrolling ancestor brings into view is caught, and
        # left out (``_GEOMETRY_JS``).
        below = [s for s in geo["scrollers"] if s["bottom"] > geo["viewport"][1] + 1]
        check(
            f"[{window.name}] {label} — the regions end above the edge",
            not below,
            below[:3],
        )
    # C5 — what is CLIPPED, with no bar to catch it.
    #
    # ⚠️ **Overflow and clipping are not the same fault.** The two
    # findings above measure what goes OUT — of a page, of a region. This
    # one measures what stays IN and is not painted: a box with an
    # imposed height on which a theme sets ``overflow:hidden`` keeps its
    # content in the DOM and shows only part of it. No error, no failed
    # request, complete and correct HTML — it is a screen's most
    # expensive failure mode, because one cannot know one is looking at
    # missing information.
    #
    # An author's count of what fits is unreliable: the height is written
    # in the app and the padding in a component theme, and their sum lives
    # nowhere.
    #
    # The cost is nil: this reuses the loop above.
    check(
        f"[{window.name}] {label} — nothing is clipped without recourse",
        not geo["clipped"],
        geo["clipped"][:3],
    )


#: Plants the walk's starting point at the head of ``<body>``.
_TAB_START_JS = """() => {
  const start = document.createElement('span');
  start.id = 'bz-probe-tab-start';
  start.tabIndex = -1;
  document.body.prepend(start);
  start.focus();
}"""


def _tab_order(check: Check, window: Window) -> None:
    """Where tabbing lands — and where it has no business being.

    Off-screen is not enough. A closed ``ui.dialog`` is CENTRED: its
    fields sit right in the middle of the viewport, so a control
    reachable inside a closed dialog would pass this sweep green.

    The marker targeted (``data-bz-overlay``) is that of MODAL overlays —
    ``dialog`` and ``drawer``. The anchored ones (``popover``,
    ``dropdown``) close with ``display:none``, so nothing can take focus
    there and there is nothing to measure; the day one of them moved to
    ``visibility`` to animate its exit, it is the component gate
    (``test_a_closed_overlay_is_out_of_the_tab_order``) that would say
    so, not this sweep.
    """
    reached = False
    offscreen: list[dict[str, Any]] = []
    in_closed: list[dict[str, Any]] = []
    vw, vh = window.page.evaluate(
        "() => [document.documentElement.clientWidth, "
        "document.documentElement.clientHeight]"
    )
    # The walk starts at the TOP of the document, not where the scenario
    # left the focus: ended on the page's last control, the first Tab
    # would leave the document and "tabbing reaches something" would go
    # red on a sound page. ``blur()`` is not enough:
    # Chrome keeps its starting point where the click landed. Focusing a
    # marker at the head of ``<body>`` moves it; ``tabindex=-1`` keeps the
    # marker itself out of the walk.
    window.page.evaluate(_TAB_START_JS)
    for _ in range(20):
        window.press("Tab")
        focused = window.page.evaluate(_TAB_JS)
        if focused is None:
            break
        reached = True
        if focused["closed"]:
            in_closed.append(focused)
        if focused["w"] == 0 and focused["h"] == 0:
            continue  # a deliberately invisible control, not a fault
        if (
            focused["x"] + focused["w"] < 0
            or focused["y"] + focused["h"] < 0
            or focused["x"] > vw
            or focused["y"] > vh
        ):
            offscreen.append(focused)
    window.page.evaluate(
        "() => document.getElementById('bz-probe-tab-start')?.remove()"
    )
    check(
        f"[{window.name}] tabbing reaches something",
        reached,
        "no focusable element",
    )
    check(
        f"[{window.name}] tabbing does not leave the screen",
        not offscreen,
        offscreen[:3],
    )
    check(
        f"[{window.name}] tabbing does not enter a closed overlay",
        not in_closed,
        in_closed[:3],
    )
