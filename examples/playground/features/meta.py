"""``Title`` / ``MetaTag`` / ``Fragment`` test bench.

The three Tier-11 meta primitives have no body footprint :

- ``ui.title`` writes ``ctx.head_title`` (the browser tab + ``<title>``).
- ``ui.meta_tag`` appends an :class:`Element` to ``ctx.head_extras``
  (lands inside ``<head>``, never the body).
- ``ui.fragment`` renders a wrap-less :class:`FragmentNode` (children
  flatten into the parent, no surrounding HTML tag).

The live demo is therefore the **browser tab title** (compare it on
this page vs. the rest of the playground) and the **document head**
(open dev tools → Elements → ``<head>``). The Fragment card stays
in-body because its effect IS the structural side-by-side.
"""

import bretzel
from bretzel import download, refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import (
    ClientExpression,
    ClientState,
    PageState,
    field,
)

from examples.playground.features.inspection import emitted_html_block


PATH = "/meta"


class VerbDemo(ClientState):
    """The value the button copies, LIVE.

    It is a ``ClientState`` and not a literal to show the only case that
    matters: ``bretzel.copy`` interpolates the field's PATH, not its
    value at render time. Type in the field, copy, paste — what comes out
    is what you have just typed, without the server ever having seen it.
    """

    secret: str = field(default="sk-live-4f2a91")


# ── Demo state — drives the Server playground card ───────────────────────


class TitlePlayground(PageState):
    """Title playground — one field for the live text.

    Default matches the page-level ``ui.title()`` so a fresh visit
    shows the panel writing the SAME value the page-level call set —
    the override only becomes visible when the user edits.
    """

    text: str = field(default="Meta primitives — Playground")


class MetaTagPlayground(PageState):
    """MetaTag playground — pick the identifier kind + name + content."""

    identifier_kind: str = field(default="name")  # name / property / http_equiv
    identifier:      str = field(default="description")
    content:         str = field(default="Internal tools demo")


def title_changed(state: TitlePlayground) -> None:
    # Typed param: the dispatcher hydrates the changed control into state.
    pass


def meta_tag_changed(state: MetaTagPlayground) -> None:
    # Typed param: the dispatcher hydrates the changed control into state.
    pass


# ── Title panel ──────────────────────────────────────────────────────────


@refreshable(deps=[TitlePlayground])
def title_panel() -> None:
    state = TitlePlayground()
    # ⚠️ Side effect : changing the text below ACTUALLY updates the
    # browser tab title (partial-nav refresh flips the HX-Trigger
    # ``bretzel:title``). Watch the tab while you type.
    ui.title(state.text)

    with ui.grid(cols={"base": 1, "sm": 2}, gap="md"):
        with ui.vstack(gap="xs"):
            ui.text("text", color="muted", size="xs")
            ui.input(value=state.text, on_change=title_changed,
                     placeholder="Page title")
        with ui.vstack(gap="xs"):
            ui.text("preview (tab title)", color="muted", size="xs")
            ui.text(state.text or "(empty → falls back to decorator)",
                    classes="font-mono")

    ui.divider()

    emitted_html_block(
        "Emitted into <head>",
        f"<title>{state.text}</title>" if state.text else "(no change — decorator wins)",
    )


# ── MetaTag panel ────────────────────────────────────────────────────────


@refreshable(deps=[MetaTagPlayground])
def meta_tag_panel() -> None:
    state = MetaTagPlayground()
    # Side effect : actually appends a <meta> to this page's head.
    # Open dev tools to see it.
    kind = state.identifier_kind
    if state.identifier and state.content:
        if kind == "name":
            ui.meta_tag(name=state.identifier, content=state.content)
        elif kind == "property":
            ui.meta_tag(property=state.identifier, content=state.content)
        else:
            ui.meta_tag(http_equiv=state.identifier, content=state.content)

    with ui.grid(cols={"base": 1, "sm": 3}, gap="md"):
        with ui.vstack(gap="xs"):
            ui.text("identifier kind", color="muted", size="xs")
            ui.select(
                value=state.identifier_kind,
                options=[
                    ("name",       "name= (description / robots / twitter:*)"),
                    ("property",   "property= (og:*)"),
                    ("http_equiv", "http_equiv= (refresh / X-UA-Compatible)"),
                ],
                on_change=meta_tag_changed,
            )
        with ui.vstack(gap="xs"):
            ui.text("identifier value", color="muted", size="xs")
            ui.input(value=state.identifier, on_change=meta_tag_changed,
                     placeholder="description")
        with ui.vstack(gap="xs"):
            ui.text("content", color="muted", size="xs")
            ui.input(value=state.content, on_change=meta_tag_changed,
                     placeholder="Internal tools demo")

    ui.divider()

    # Mirror what landed in <head> as a hand-formatted string. We
    # don't go through ``serialize_html`` because the actual MetaTag
    # render writes to ``ctx.head_extras`` (no visible body footprint)
    # — the EMITTED HTML for this preview is straightforward to spell
    # out directly from the live state.
    if state.identifier and state.content:
        attr_name = kind.replace("_", "-")
        emitted = (
            f'<meta {attr_name}="{state.identifier}" '
            f'content="{state.content}"/>'
        )
    else:
        emitted = "(missing identifier or content — nothing emitted)"

    emitted_html_block("Emitted into <head>", emitted)



class IntervalDemo(ClientState, persist="memory"):
    """The timer's gate and its counter.

    ``ClientState`` and not ``PageState``: the whole point of
    ``ui.interval`` is that the cadence stops without the server having a
    task to manage. A server state would bring back exactly the life
    cycle being avoided.
    """

    running: bool = field(default=False)
    ticks:   int  = field(default=0)


class FilterDemo(ClientState, persist="memory"):
    """The input that filters. ``ClientState`` for the same reason as
    above: the whole point of ``filter_each`` is to filter WITHOUT a
    round trip, so its state cannot live on the server."""

    query: str = field(default="")


#: The filtered set. Short on purpose — we demonstrate the mechanism,
#: not the pagination.
FRUITS: list[str] = [
    "abricot", "banane", "cerise", "citron", "figue", "fraise",
    "framboise", "grenade", "kiwi", "mangue", "myrtille", 'peach',
]


@download("/meta-demo.csv", filename="fruits.csv")
def fruits_csv() -> list[dict]:
    """The ``@download`` demo — a real file, a real route.

    At MODULE level and not in the page's body: ``@download`` MARKS a
    function, and the app picks the mark up at ``include()``. Declared
    inside a render, it would be re-marked at every request and would
    never be mounted.
    """
    return [{"fruit": f, "lettres": len(f)} for f in FRUITS]

# ── Page ─────────────────────────────────────────────────────────────────


def page() -> None:
    # Page-level title : overrides @page(title=...) when present
    # (the playground routes don't pass title= today, so this is the
    # final value).
    ui.title("Meta primitives — Playground")
    # A few static meta_tags so the head of THIS page actually carries
    # the social-card setup any production page would ship.
    ui.meta_tag(name="description",
                content="Bretzel meta primitives — Title / MetaTag / Fragment.")
    ui.meta_tag(property="og:title", content="Bretzel — Meta primitives")
    ui.meta_tag(property="og:type",  content="website")
    ui.meta_tag(name="twitter:card", content="summary")

    with ui.container():
        with ui.vstack():
            ui.heading("Meta primitives", level=1)
            ui.text(
                "Three Tier-11 primitives that don't render into the "
                "page body : ``ui.title`` rewrites the browser tab + "
                "the ``<title>`` element, ``ui.meta_tag`` injects "
                "``<meta>`` into ``<head>``, and ``ui.fragment`` "
                "groups children without a wrapping HTML tag. The live "
                "demo is the **browser tab title** + the document "
                "**``<head>``** (open dev tools to inspect).",
                color="muted",
            )

            # ── Card 1 — Title ──────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Title", level=2)
                    ui.text(
                        "``ui.title(\"…\")`` overrides the "
                        "``@page(title=…)`` decorator value at "
                        "render time. Useful when the title depends on "
                        "data the decorator couldn't know (current "
                        "user, loaded record, etc.). Last call wins ; "
                        "empty string falls through to the decorator.",
                        color="muted", size="sm",
                    )

                    ui.heading("Live playground", level=3)
                    ui.text(
                        "Type below — the browser tab updates "
                        "(partial-nav refresh flips ``bretzel:title``).",
                        color="muted", size="xs",
                    )
                    title_panel()

                    ui.divider()

                    ui.heading("Usage", level=3)
                    ui.code(
                        "@page(\"/users/{user_id}\", title=\"User\")\n"
                        "def user_detail(user_id: int) -> None:\n"
                        "    user = load_user(user_id)\n"
                        "    ui.title(f\"{user.name} — Users\")"
                        "  # overrides decorator\n"
                        "    with ui.container():\n"
                        "        ui.heading(user.name)",
                        lang="python",
                    )

            # ── Card 2 — MetaTag ────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("MetaTag", level=2)
                    ui.text(
                        "``ui.meta_tag(name=/property=/http_equiv=, "
                        "content=)`` appends a ``<meta>`` element to "
                        "the document head. Exactly ONE identifier "
                        "kwarg ; ``content=`` always required. "
                        "``charset`` and ``viewport`` are framework-"
                        "owned (cf. ``render/shell.py``) and "
                        "deliberately NOT exposed — overriding them "
                        "would only invite drift.",
                        color="muted", size="sm",
                    )

                    ui.heading("Live playground", level=3)
                    ui.text(
                        "Tweak below — the rendered ``<meta>`` lands "
                        "in this page's head (open dev tools to see "
                        "it). The emitted HTML preview below mirrors "
                        "what's injected.",
                        color="muted", size="xs",
                    )
                    meta_tag_panel()

                    ui.divider()

                    ui.heading("Common shapes", level=3)
                    ui.code(
                        "ui.meta_tag(name=\"description\",      "
                        "content=\"Internal tool for Acme\")\n"
                        "ui.meta_tag(name=\"twitter:card\",     "
                        "content=\"summary_large_image\")\n"
                        "ui.meta_tag(property=\"og:title\",     "
                        "content=\"Dashboard — Acme\")\n"
                        "ui.meta_tag(property=\"og:image\",     "
                        "content=\"https://acme.com/og.png\")\n"
                        "ui.meta_tag(http_equiv=\"refresh\",    "
                        "content=\"30; url=/logout\")",
                        lang="python",
                    )

            # ── Card 3 — Fragment ───────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Fragment", level=2)
                    ui.text(
                        "``with ui.fragment(): …`` groups children with "
                        "**no surrounding tag**. Use it inside helpers "
                        "that need to emit multiple children without "
                        "imposing a layout wrapper on every caller "
                        "(``ui.flex()`` / ``ui.hstack()`` would change "
                        "the layout context).",
                        color="muted", size="sm",
                    )

                    ui.heading("Side-by-side comparison", level=3)
                    with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
                        with ui.vstack(gap="xs"):
                            ui.text("Without Fragment — wrapper visible",
                                    color="muted", size="xs")
                            with ui.card(padding="sm",
                                         classes="bg-muted/5"):
                                with ui.vstack(gap="sm"):
                                    ui.text("Header")
                                    with ui.hstack(gap="xs"):  # ← wrapper
                                        ui.button("A", size="sm")
                                        ui.button("B", size="sm")
                                    ui.text("Footer")
                            ui.text("→ buttons are nested inside a flex "
                                    "row ; the outer vstack sees 3 "
                                    "children.",
                                    color="muted", size="xs")
                        with ui.vstack(gap="xs"):
                            ui.text("With Fragment — flat children",
                                    color="muted", size="xs")
                            with ui.card(padding="sm",
                                         classes="bg-muted/5"):
                                with ui.vstack(gap="sm"):
                                    ui.text("Header")
                                    with ui.fragment():
                                        ui.button("A", size="sm")
                                        ui.button("B", size="sm")
                                    ui.text("Footer")
                            ui.text("→ buttons are direct children of "
                                    "the outer vstack (4 siblings) ; "
                                    "no wrapper element.",
                                    color="muted", size="xs")

                    ui.divider()

                    ui.heading("Helper composition", level=3)
                    ui.text(
                        "The classic use case : a helper that adds "
                        "buttons to whatever layout the caller uses, "
                        "without locking them into a flex row.",
                        color="muted", size="xs",
                    )
                    ui.code(
                        "def user_actions(user):\n"
                        "    with ui.fragment():\n"
                        "        ui.button(\"Edit\",   "
                        "on_click=...)\n"
                        "        ui.button(\"Delete\", "
                        "on_click=...)\n\n"
                        "with ui.hstack(gap=\"lg\"):\n"
                        "    user_actions(user)"
                        "  # buttons land flat in the hstack\n"
                        "    ui.button(\"Save\")"
                        "  # arrives as a 3rd sibling",
                        lang="python",
                    )

                    ui.divider()

                    ui.heading("Emitted HTML", level=3)
                    ui.text(
                        "The Fragment leaves no marker in the output — "
                        "its children appear in the parent's HTML as "
                        "if they had been written there directly.",
                        color="muted", size="xs",
                    )
                    demo = ui.hstack()
                    with demo:
                        with ui.fragment():
                            ui.button("Edit", size="sm")
                            ui.button("Delete", size="sm")
                        ui.button("Save", size="sm")
                    emitted_html_block("Emitted HTML", serialize_html(demo))

            # ── Card 4 — Edge cases ─────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Edge cases", level=2)
                    ui.text(
                        "Inputs that surface user errors instead of "
                        "silently swallowing them.",
                        color="muted", size="sm",
                    )

                    ui.heading("Title", level=3)
                    with ui.vstack(gap="xs"):
                        ui.text(
                            "• Multiple ``ui.title()`` calls in the "
                            "same render scope → **last call wins**. "
                            "Layouts can set a fallback ; pages "
                            "override.",
                            color="muted", size="sm",
                        )
                        ui.text(
                            "• Empty string → **skipped** (better to "
                            "fall through to the decorator default "
                            "than ship ``<title></title>``).",
                            color="muted", size="sm",
                        )
                        ui.text(
                            "• Called outside a render scope → "
                            "**RuntimeError** (no silent loss).",
                            color="muted", size="sm",
                        )

                    ui.heading("MetaTag", level=3)
                    with ui.vstack(gap="xs"):
                        ui.text(
                            "• No identifier kwarg → **TypeError** "
                            "(``<meta content=…>`` alone is invalid "
                            "HTML).",
                            color="muted", size="sm",
                        )
                        ui.text(
                            "• Multiple identifier kwargs in one "
                            "call → **TypeError** (pick the one that "
                            "matches the semantics).",
                            color="muted", size="sm",
                        )
                        ui.text(
                            "• No auto-dedup — emit "
                            "``<meta name=\"description\">`` once. "
                            "The pipeline appends every call.",
                            color="muted", size="sm",
                        )

                    ui.heading("Fragment", level=3)
                    with ui.vstack(gap="xs"):
                        ui.text(
                            "• Any kwarg (``classes=`` / ``id=`` / "
                            "``style=``) → **TypeError** (no DOM "
                            "element to attach attrs to).",
                            color="muted", size="sm",
                        )
                        ui.text(
                            "• Empty Fragment → serializes to ``\"\"`` "
                            "(safe for ``if cond:`` blocks).",
                            color="muted", size="sm",
                        )
                        ui.text(
                            "• Fragments inside Fragments → fully "
                            "flatten (no \"fragment of fragments\" "
                            "intermediate).",
                            color="muted", size="sm",
                        )

            # ── Card 5 — Composability ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Composability", level=2)
                    ui.text(
                        "Patterns the meta primitives unlock together.",
                        color="muted", size="sm",
                    )

                    ui.heading("Nested fragments flatten all the way",
                               level=3)
                    nested = ui.hstack()
                    with nested:
                        with ui.fragment():
                            ui.badge("A", color="primary")
                            with ui.fragment():
                                ui.badge("B", color="success")
                                ui.badge("C", color="warning")
                            ui.badge("D", color="error")
                    ui.text("→ 4 badges, all direct siblings of the "
                            "outer hstack. No nesting in the HTML.",
                            color="muted", size="xs")
                    emitted_html_block("Emitted HTML",
                                       serialize_html(nested))

                    ui.divider()

                    ui.heading("Fragment + conditional emit", level=3)
                    ui.text(
                        "An empty Fragment serializes to the empty "
                        "string — useful when the children are "
                        "conditional and you don't want a leftover "
                        "wrapper when the condition is false.",
                        color="muted", size="xs",
                    )
                    cond = ui.hstack()
                    with cond:
                        ui.text("Always here.")
                        with ui.fragment():
                            # Empty body — common when wrapped in `if`.
                            pass
                        ui.text("Also always here.")
                    emitted_html_block("Emitted HTML (empty fragment)",
                                       serialize_html(cond))

            # ── Card 6 — Interval ────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Interval", level=2)
                    ui.text(
                        "The group's fourth primitive, and the only one "
                            'that MOVES: a hidden timer. It arrived here on '
                            '2026-08-30, when ``/matrix`` was deleted — which'
                            ' was the only place in the playground where it '
                            'was built.',
                        color="muted", size="sm",
                    )
                    ui.text(
                        '``seconds=`` sets the cadence, ``on_tick=`` what'
                            ' fires on every beat, and ``active=`` the gate. '
                            'It is ``active`` that counts: bound to a '
                            '``ClientBinding``, it makes the cadence '
                            'stoppable WITHOUT a server-side lifecycle — '
                            'nobody has a task to start or to kill, a browser'
                            ' switch is enough.',
                        color="muted", size="sm",
                    )

                    ui.heading('Live — a counter you can cut', level=3)
                    ticker = IntervalDemo()
                    with ui.hstack(gap="sm", align="center"):
                        ui.switch(checked=ticker.running,
                                  label="cadence active")
                        ui.text(
                            ClientExpression(
                                "'battements : ' + "
                                "($bz.state.IntervalDemo.default.ticks"
                                " || 0)"
                            ),
                            color="muted", size="sm",
                            classes="font-mono",
                        )
                    ui.interval(
                        seconds=1.0,
                        active=ticker.running,
                        on_tick=ticker.ticks.increment(),
                    )

                    ui.heading('The emitted HTML', level=3)
                    ui.text(
                        'No visible surface: a hidden node carrying its '
                            'own cadence and its own door. That is why it '
                            'lives in the meta group and not among the '
                            'display components.',
                        color="muted", size="xs",
                    )
                    emitted_html_block(
                        "Emitted HTML (Interval)",
                        serialize_html(
                            ui.interval(seconds=1.0,
                                        active=ticker.running,
                                        on_tick=ticker.ticks.increment())
                        ),
                    )

            with ui.card():
                with ui.vstack():
                    ui.heading("filter_each", level=2)
                    ui.text(
                        "The group's fifth primitive, and it arrives here"
                            ' on 2026-08-31 for a reason worth saying: '
                            '``ui.filter_each`` is PUBLIC and was '
                            'demonstrated NOWHERE. Its only page — the '
                            'filterable hub — went with ``/matrix`` on '
                            '2026-08-30, and all that was left was a browser '
                            'probe launching a deleted bench, hence dead in '
                            'silence.',
                        color="muted", size="sm",
                    )
                    ui.text(
                        'What it does: it wraps every row in a framework-'
                            'derived ``bz-show`` that compares ``text(item)``'
                            ' with ``query``. The filtering is therefore '
                            'ENTIRELY client side — no round trip, no hand-'
                            'written JS — and the rows are hidden, not '
                            'removed.',
                        color="muted", size="sm",
                    )

                    ui.heading('Live — the list narrows as you type',
                               level=3)
                    filtre = FilterDemo()
                    ui.input(value=filtre.query, placeholder="Filtrer…",
                             size="sm", id="meta-filter-input")
                    with ui.vstack(gap="xs", id="meta-filter-rows"):
                        for fruit in ui.filter_each(
                            FRUITS,
                            query=filtre.query,
                            text=lambda f: f,
                            key=lambda f: f,
                            empty=lambda: ui.text(
                                'No fruit matches.',
                                color="muted", size="sm",
                            ),
                        ):
                            ui.text(fruit, size="sm")

                    ui.heading('The emitted HTML', level=3)
                    ui.text(
                        'Every row carries its own ``bz-show``: that is '
                            'what makes the filter instant, and what explains'
                            ' why the DOM count does not move as you type.',
                        color="muted", size="xs",
                    )
                    emitted_html_block(
                        "Emitted HTML (filter_each)",
                        serialize_html(
                            ui.text("abricot", size="sm")
                        ),
                    )

            # ── Card 7 — A11y ────────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Verbes clients", level=2)
                    ui.text(
                        '``bretzel.copy`` / ``print_page`` / '
                            '``fullscreen`` — shipped on 2026-09-01. They are'
                            ' not components, hence their place here: they '
                            'emit no markup, they trigger a BROWSER action.',
                        color="muted", size="sm",
                    )
                    ui.text(
                        'They cost almost nothing because the slot '
                            'already existed: ``on_<event>=`` is polymorphic '
                            '— a callable leaves as a signed POST, a STRING '
                            'is client source evaluated in place. That is '
                            "``dialog.open()``'s contract, and the verbs plug"
                            ' into it with no new plumbing.',
                        color="muted", size="sm",
                    )

                    ui.heading('Live — copies what you type', level=3)
                    ui.text(
                        'The value lives in a ``ClientState``. The verb '
                            'interpolates its PATH, not its value at render '
                            'time: edit the field, copy, paste — what comes '
                            'out is your own input, and the server never saw '
                            'it go by.',
                        color="muted", size="sm",
                    )
                    verbes = VerbDemo()
                    with ui.hstack(gap="sm", align="center"):
                        ui.input(value=verbes.secret, size="sm",
                                 id="meta-verb-input")
                        ui.button("Copier", size="sm",
                                  id="meta-verb-copy",
                                  on_click=bretzel.copy(verbes.secret))
                        ui.button("Imprimer", size="sm", variant="outline",
                                  id="meta-verb-print",
                                  on_click=bretzel.print_page())
                    ui.text(
                        '⚠️ No visual feedback, and that is the contract:'
                            ' the verb copies, the app wires whatever '
                            'feedback it wants. A ``ui.copy_button`` that '
                            'flips for two seconds stays the obvious shape '
                            'the day the need comes up.',
                        color="muted", size="sm",
                    )

                    ui.heading('Full screen', level=3)
                    ui.text(
                        '``fullscreen()`` targets the page; '
                            '``fullscreen(a_component)`` targets an element '
                            'by its ``id`` — the same convention as the '
                            'imperative API. The browser DEMANDS a user '
                            'gesture, which is held by construction: a verb '
                            'always lives inside an ``on_*=``.',
                        color="muted", size="sm",
                    )
                    # We keep the card's REFERENCE, exactly like the
                    # imperative API (``confirm = ui.dialog()`` then
                    # ``confirm.open()``). Building a second component
                    # just to carry the same ``id`` would work on screen
                    # and emit one more empty element — this card's first
                    # version did that.
                    zone = ui.card(padding="sm", id="meta-verb-zone")
                    with zone:
                        ui.text('This card can go full screen.',
                                size="sm")
                        ui.button('Full screen', size="sm",
                                  variant="outline",
                                  id="meta-verb-fullscreen",
                                  on_click=bretzel.fullscreen(zone))

                    ui.heading("Partager et vibrer", level=3)
                    ui.text(
                        '``share()`` opens the native sheet — and when '
                            'there is none, which is the NORMAL case on a '
                            'desktop browser, it COPIES the URL. With no '
                            'argument, it is the current page that goes: '
                            'since state writes itself into the address, the '
                            'URL carries the view, so sharing the page is '
                            'sharing what you are looking at.',
                        color="muted", size="sm",
                    )
                    with ui.hstack(gap="sm", align="center"):
                        ui.button('Share this view', size="sm",
                                  variant="outline", id="meta-verb-share",
                                  on_click=bretzel.share(title="Bretzel · meta"))
                        ui.button("Vibrer", size="sm", variant="outline",
                                  id="meta-verb-vibrate",
                                  on_click=bretzel.vibrate([50, 30, 50]))
                    ui.text(
                        '``vibrate`` does nothing on a computer, and that'
                            ' is normal: the function exists everywhere, it '
                            'simply has no hardware to drive. That is what '
                            'makes it free — there is no absence to handle, '
                            'unlike ``share``.',
                        color="muted", size="sm",
                    )

                    ui.heading('@download — a real file', level=3)
                    ui.text(
                        "This is NOT a verb: an action's response is "
                            'swallowed by the bridge and applied as a ``<bz-'
                            'patch>``, whereas a download must BE the file. '
                            'So it is an ORDINARY link, not an ``on_click=`` '
                            "— and it does not get swallowed by the shell's "
                            '``hx-boost``, which only a browser can check '
                            '(``tests/probes/probe_download.py``).',
                        color="muted", size="sm",
                    )
                    # ``download=True`` is MANDATORY here, and it is
                    # not decoration: without it the shell swallows the
                    # link in ``hx-boost`` and injects the CSV into the
                    # page instead of downloading it. Measured.
                    ui.link('Download the fruits (CSV)',
                            href="/meta-demo.csv", download=True,
                            id="meta-download-link")
                    ui.text(
                        'The function returns a ``list[dict]`` and the '
                            'framework makes a CSV of it: headers derived '
                            'from the keys, a UTF-8 BOM so Excel does not eat'
                            ' the accents, RFC 4180 quoting. It can also '
                            'return a ``str``, ``bytes``, or a hand-built '
                            '``Response``.',
                        color="muted", size="sm",
                    )

                    ui.heading('The clipboard has one condition', level=3)
                    ui.text(
                        '``navigator.clipboard`` demands a SECURE '
                            'context. ``https://`` and ``http://localhost`` '
                            'are ones; ``http://192.168.1.20:8000`` is NOT — '
                            'and that is exactly how an internal tool gets '
                            'used. There the API is ``undefined``, and a bare'
                            ' call would do nothing, without a word. Hence '
                            'the fallback to ``document.execCommand`` in '
                            '``22_verbs.js``: deprecated, and the only route '
                            'that exists there.',
                        color="muted", size="sm",
                    )

            with ui.card():
                with ui.vstack():
                    ui.heading("A11y", level=2)
                    ui.text(
                        "No keyboard-test control here — none of "
                        "these three primitives render a DOM node, "
                        "so there is nothing to Tab onto. What "
                        "actually matters for accessibility :",
                        color="muted", size="sm",
                    )
                    with ui.vstack(gap="xs"):
                        ui.text(
                            "• ``ui.title()`` — most screen readers "
                            "announce a changed ``<title>`` on "
                            "partial-nav (SPA-style) updates, same "
                            "as a full page load. Keep it accurate "
                            "and unique per page ; don't leave it "
                            "on a stale value after navigating.",
                            color="muted", size="sm",
                        )
                        ui.text(
                            "• ``ui.meta_tag()`` — ``name=\"description\"`` "
                            "and the ``og:*`` family are read by "
                            "search engines and social-share "
                            "unfurlers, not assistive tech directly "
                            "— but an accurate description IS part "
                            "of a page's overall accessibility (it's "
                            "often the first thing a screen-reader "
                            "user hears about a link before opening "
                            "it).",
                            color="muted", size="sm",
                        )
                        ui.text(
                            "• ``ui.fragment()`` — zero accessibility "
                            "surface : it emits no element and no "
                            "attribute, purely a Python-side grouping "
                            "construct.",
                            color="muted", size="sm",
                        )
