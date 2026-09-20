"""``BottomBar`` / ``BottomBarItem`` test bench.

Nine cards: Reference / Slots / Edge cases / Composability / A11y /
Server playground / Server events / Client playground / Client events.
No §7 card — the family exposes no imperative API (nothing to open, set
or toggle: the active tab is derived from the URL).

⚠️ **Every demo bar is wrapped in a ``ui.vstack()``**, and it is not
decorative. A bottom bar is ALWAYS stuck (there is no ``sticky=`` prop —
cf. the component), and a ``sticky`` element cannot leave its containing
block: giving it a container of its own height immobilises it. Without
that, every bar on this page would come and stick to the bottom of the
window in turn while scrolling, passing in front of the content
(measured: only one at a time, but that is enough to muddle a bench). The
real sticky behaviour is watched on **the bar right at the bottom of this
page**, the only one mounted with no wrapper — scroll down, and it stays
at the edge.

⚠️ The items carry real playground ``href``: a click NAVIGATES (HTMX
partial nav to the shell's outlet). It is intended — it is the wiring we
want to see working. The event cards, for their part, use items with no
``href`` so the handler speaks without leaving the page.
"""

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import ClientExpression, ClientState, PageState, field

from examples.playground.features.inspection import emitted_html_block


PATH = "/bottom-bar"


COLORS = ["primary", "secondary", "success", "warning", "error", "info",
          "muted"]

# Real playground paths: the item pointing at THIS page comes out active
# on its own (auto mode — comparison with ``current_path``), which is
# precisely what we want to look at.
TABS = [
    ("Home",    "home",   "/"),
    ("Tabs",    "layers", "/tabs"),
    ("Bottom",  "panel-bottom", PATH),
    ("Badge",   "tag",    "/badge"),
]


class BottomBarPlayground(PageState):
    # ITEM props, applied to the "Bottom" tile (the one pointing at this
    # page, hence active) so it sits beside tiles at rest serving as
    # controls.
    item_color:   str = field(default="primary")
    item_badge:   str = field(default="")
    item_icon:    str = field(default="bell")
    item_disabled: bool = field(default=False)
    active_mode:  str = field(default="auto")
    # Escape hatches.
    classes:      str = field(default="")
    custom_id:    str = field(default="")
    aria_label:   str = field(default="")
    style:        str = field(default="")
    extra_attrs:  str = field(default="")
    # Universal modifiers.
    visible:      str = field(default="on")
    tooltip:      str = field(default="")


class BottomBarEvents(PageState):
    log: list = field(default_factory=list)


class BottomBarClient(ClientState, persist="memory"):
    active:   bool = field(default=False)
    badge:    int = field(default=0)
    disabled: bool = field(default=False)


class BottomBarClientEvents(ClientState, persist="memory"):
    log: list = field(default_factory=list)


def log(name: str) -> None:
    state = BottomBarEvents()
    state.log = [*state.log, name]


def log_home() -> None:
    log("click(tab='Home')")


def log_search() -> None:
    log("click(tab='Search')")


def log_profile() -> None:
    log("click(tab='Profile')")


def clear_log() -> None:
    BottomBarEvents().log = []


def server_changed(state: BottomBarPlayground) -> None:
    # A typed param → the dispatcher hydrates the changed control's
    # value into ``state`` (coerced + persisted). The panel declares
    # ``deps=[BottomBarPlayground]``, it re-renders on its own.
    pass


def parse_extra_attrs(blob: str) -> dict:
    result: dict = {}
    for raw in blob.splitlines():
        line = raw.strip()
        if not line or "=" not in line:
            continue
        key, _, value = line.partition("=")
        result[key.strip()] = value.strip()
    return result


def build_preview(state: BottomBarPlayground):
    kwargs: dict = {}
    if state.classes:
        kwargs["classes"] = state.classes
    if state.custom_id:
        kwargs["id"] = state.custom_id
    if state.style:
        kwargs["style"] = state.style
    attrs: dict = {}
    if state.aria_label:
        attrs["aria-label"] = state.aria_label
    attrs.update(parse_extra_attrs(state.extra_attrs))
    if attrs:
        kwargs["attrs"] = attrs
    if state.tooltip:
        kwargs["tooltip"] = state.tooltip
    if state.visible == "off":
        kwargs["visible"] = False

    # The item props driven by the controls land on the tile pointing at
    # THIS page — hence active by URL derivation, its neighbours at rest
    # serving as controls.
    #
    # ⚠️ That choice is not cosmetic: `color` paints ONLY the active tile
    # (at rest, a tile is `text-muted` — it is the tab-bar idiom). By
    # putting the controls on an inactive tile, the colour selector
    # looked DEAD although the server round trip worked.
    treated: dict = {
        "color": state.item_color,
        "disabled": state.item_disabled,
        "icon": state.item_icon or None,
    }
    if state.item_badge:
        treated["badge"] = state.item_badge
    if state.active_mode != "auto":
        treated["active"] = state.active_mode == "true"

    bar = ui.bottom_bar(**kwargs)
    with bar:
        for label, icon, href in TABS:
            if href == PATH:
                ui.bottom_bar_item(label, href=href, **treated)
            else:
                ui.bottom_bar_item(label, icon=icon, href=href)
    return bar


def control(label: str):
    block = ui.vstack(gap="xs")
    with block:
        ui.text(label, color="muted", size="xs")
    return block


@refreshable(deps=[BottomBarPlayground])
def server_panel() -> None:
    state = BottomBarPlayground()

    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control("item : color (tuile active)"):
            ui.select(value=state.item_color,
                      options=[(c, c) for c in COLORS],
                      on_change=server_changed)
        with control("item : icon (tuile active)"):
            ui.input(value=state.item_icon,
                     placeholder='bell / heart / (empty = no icon)',
                     on_change=server_changed)
        with control("item : badge (tuile active)"):
            ui.input(value=state.item_badge,
                     placeholder='3 / 99+ / (empty = no badge)',
                     on_change=server_changed)
        with control("item : disabled (tuile active)"):
            ui.switch(checked=state.item_disabled, on_change=server_changed)
        with control('item: active — the resolution mode'):
            ui.select(value=state.active_mode,
                      options=[("auto", 'None — derived from the URL'),
                               ("true", 'True — forced active'),
                               ("false", 'False — forced inactive')],
                      on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes,
                     placeholder="!bg-primary/5",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id,
                     placeholder="my-tab-bar",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label,
                     placeholder="Main navigation",
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style,
                     placeholder="border-top-width: 3px",
                     on_change=server_changed)
        with control('extra_attrs (one per line, key=value)'):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="data-test=tabbar",
                        on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip,
                     placeholder="Navigation",
                     on_change=server_changed)
        with control("visible"):
            ui.select(value=state.visible,
                      options=[("on", "True (default)"),
                               ("off", "False (skip render)")],
                      on_change=server_changed)

    ui.divider()

    build_preview(state)

    ui.divider()

    emitted_html_block(
        "Emitted HTML",
        serialize_html(build_preview(state)),
    )


@refreshable(deps=[BottomBarEvents])
def events_panel() -> None:
    state = BottomBarEvents()

    ui.text(
        "``BottomBarItem`` declares ``EVENTS = ('click',)``. Here the "
            'tiles have NO ``href``: the server handler speaks without the '
            'page navigating. All three are wired.',
        color="muted", size="sm",
    )

    with ui.vstack():   # isolates the bar — cf. the header
        with ui.bottom_bar():
            ui.bottom_bar_item("Home", icon="home", on_click=log_home)
            ui.bottom_bar_item("Search", icon="search", on_click=log_search)
            ui.bottom_bar_item("Profile", icon="user", on_click=log_profile)

    ui.divider()

    with ui.hstack(justify="between", align="center"):
        ui.text("Live log (newest first, last 10)",
                color="muted", size="sm")
        ui.button("Clear", variant="ghost", size="xs",
                  on_click=clear_log, disabled=not state.log)

    if state.log:
        with ui.vstack(gap="xs"):
            for i, evt in enumerate(reversed(state.log[-10:]), 1):
                ui.text(f"{i}. {evt}",
                        color="muted", size="sm", classes="font-mono")
    else:
        ui.text('(no events yet — click a tile above)',
                color="muted", size="sm")

    ui.divider()

    with ui.vstack():
        representative = ui.bottom_bar()
    with representative:
        ui.bottom_bar_item("Home", icon="home", on_click=log_home)
    emitted_html_block(
        'Emitted HTML (BottomBarItem with a server handler)',
        serialize_html(representative),
    )


def page() -> None:
    with ui.container():
        with ui.vstack():
            ui.heading("BottomBar", level=1)
            ui.text(
                "A bottom-of-screen tab bar — ``ui.navbar``'s mobile "
                    'counterpart. Two pieces: ``ui.bottom_bar`` (the '
                    '``<nav>`` stuck to the edge) and ``ui.bottom_bar_item`` '
                    '(a tab: icon on top, label underneath, equal width). The'
                    ' component is mounted inside an ``if '
                    'Screen().is_mobile:`` — the framework imposes no mobile '
                    'nav, the developer chooses.',
                color="muted",
            )
            ui.text(
                'Two things to know to read this page: a bottom bar is '
                    'always stuck to the edge (no prop for that), so every '
                    'demo is wrapped in a container its own size that pins it'
                    ' down — the only free bar showing it is right at the '
                    'foot of the page. And their items carry real playground '
                    'hrefs, so a click really navigates.',
                color="muted", size="sm",
            )

            # ── Card 1 — Reference ──────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Reference", level=2)
                    ui.text("Visual scan of every prop.",
                            color="muted", size="sm")

                    ui.heading("Basic — 4 onglets", level=3)
                    ui.text(
                        'The active tab is derived from the URL: “Bottom”'
                            ' points at this page, so it stands out on its '
                            'own.',
                        color="muted", size="xs",
                    )
                    with ui.vstack():
                        with ui.bottom_bar():
                            for label, icon, href in TABS:
                                ui.bottom_bar_item(label, icon=icon, href=href)

                    ui.heading('No variant — and that is deliberate',
                               level=3)
                    ui.text(
                        'A rounded pill detached from the edges existed '
                            'here as `variant="floating"`, then was cut: an '
                            'app has only ONE tab bar and picks its look '
                            'once, so it is a theme decision, not a prop. '
                            '`ui.bottom_bar(variant=…)` now raises, instead '
                            'of being silently absorbed as an HTML attribute.'
                            ' The floating look is obtained by overriding the'
                            " `root` slot — see the Server playground's "
                            '`classes` control to try it right away.',
                        color="muted", size="xs",
                    )

                    ui.heading("item : color", level=3)
                    ui.text(
                        'The active one signals itself through the COLOUR'
                            ' of the icon and the label — not through a solid'
                            " background like a navbar's pill.",
                        color="muted", size="xs",
                    )
                    for c in COLORS:
                        with ui.vstack():
                            with ui.bottom_bar():
                                ui.bottom_bar_item("Active", icon="check",
                                                   color=c, active=True)
                                ui.bottom_bar_item("Idle", icon="circle",
                                                   color=c)
                                ui.bottom_bar_item("Idle", icon="circle",
                                                   color=c)

                    ui.heading("item : badge", level=3)
                    with ui.vstack():
                        with ui.bottom_bar():
                            ui.bottom_bar_item("Inbox", icon="inbox", badge=3)
                            ui.bottom_bar_item("Alerts", icon="bell", badge="99+")
                            ui.bottom_bar_item("Chat", icon="message-circle")

                    ui.heading("item : disabled", level=3)
                    with ui.vstack():
                        with ui.bottom_bar():
                            ui.bottom_bar_item("Home", icon="home", href="/")
                            ui.bottom_bar_item("Soon", icon="lock",
                                               disabled=True)
                            ui.bottom_bar_item("Profile", icon="user")

                    ui.heading('item: active — explicit vs derived',
                               level=3)
                    with ui.vstack():
                        with ui.bottom_bar():
                            ui.bottom_bar_item("active=True", icon="check",
                                               active=True)
                            ui.bottom_bar_item("active=False", icon="x",
                                               active=False, href="/")
                            ui.bottom_bar_item("auto (URL)", icon="compass",
                                               href=PATH)

            # ── Card 2 — Slots ──────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Slots", level=2)
                    ui.text(
                        '``icon`` accepts a string shorthand or a '
                            'Component. The shorthand is re-wrapped as '
                            '``ui.icon(size="lg")`` — 24px, the size of a '
                            'touch target; an Icon built by the caller keeps '
                            'ITS size and ITS colour.',
                        color="muted", size="sm",
                    )

                    ui.heading("icon=str (raccourci)", level=3)
                    with ui.vstack():
                        with ui.bottom_bar():
                            ui.bottom_bar_item("Home", icon="home")
                            ui.bottom_bar_item("Search", icon="search")

                    ui.heading("icon=Component", level=3)
                    with ui.vstack():
                        with ui.bottom_bar():
                            ui.bottom_bar_item(
                                "Small", icon=ui.icon("home", size="xs"))
                            ui.bottom_bar_item(
                                "Huge", icon=ui.icon("search", size="xl"))
                            ui.bottom_bar_item(
                                "Tinted",
                                icon=ui.icon("heart", color="error"))

                    ui.heading("badge=Component", level=3)
                    ui.text(
                        'A scalar is wrapped in an ``error`` / ``xs`` '
                            '``ui.badge``; a Component replaces it while '
                            'keeping the anchoring. ⚠️ This sentence already '
                            'announced the red badge before 2026-08-16, while'
                            ' all three nav families rendered a scalar as '
                            'BARE TEXT: it was true of the docs, false of the'
                            ' code. It is the code that came round to it.',
                        color="muted", size="xs",
                    )
                    with ui.vstack():
                        with ui.bottom_bar():
                            ui.bottom_bar_item("Scalar", icon="bell", badge=7)
                            ui.bottom_bar_item(
                                "Component", icon="bell",
                                badge=ui.badge("new", color="success",
                                               size="xs"))

            # ── Card 3 — Edge cases ─────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Edge cases", level=2)
                    ui.text('Edge-case inputs.', color="muted", size="sm")

                    ui.heading("2 onglets", level=3)
                    with ui.vstack():
                        with ui.bottom_bar():
                            ui.bottom_bar_item("Left", icon="arrow-left")
                            ui.bottom_bar_item("Right", icon="arrow-right")

                    ui.heading('6 tabs (beyond the iOS recommendation)',
                               level=3)
                    with ui.vstack():
                        with ui.bottom_bar():
                            for n in range(1, 7):
                                ui.bottom_bar_item(f"Tab {n}", icon="circle")

                    ui.heading('Very long labels (truncate)', level=3)
                    with ui.vstack():
                        with ui.bottom_bar():
                            ui.bottom_bar_item("Notifications et alertes",
                                               icon="bell")
                            ui.bottom_bar_item('Account settings',
                                               icon="settings")
                            ui.bottom_bar_item("Aide", icon="help-circle")

                    ui.heading('Icon only (no label)', level=3)
                    with ui.vstack():
                        with ui.bottom_bar():
                            ui.bottom_bar_item(icon="home")
                            ui.bottom_bar_item(icon="search")
                            ui.bottom_bar_item(icon="user")

                    ui.heading('Label only (no icon)', level=3)
                    with ui.vstack():
                        with ui.bottom_bar():
                            ui.bottom_bar_item("Home")
                            ui.bottom_bar_item("Search")
                            ui.bottom_bar_item("Profile")

                    ui.heading('Emoji + multiple scripts', level=3)
                    with ui.vstack():
                        with ui.bottom_bar():
                            ui.bottom_bar_item("🏠 Home", icon="home")
                            ui.bottom_bar_item("שלום", icon="globe")
                            ui.bottom_bar_item("中文", icon="languages")

                    ui.heading('HTML-special label (escaping)', level=3)
                    with ui.vstack():
                        with ui.bottom_bar():
                            ui.bottom_bar_item("<script>alert(1)</script>",
                                               icon="bug")
                            ui.bottom_bar_item("Safe", icon="shield")

                    ui.heading("Barre vide", level=3)
                    with ui.vstack():
                        ui.bottom_bar()

                    ui.heading('an external href (new tab, no htmx)',
                               level=3)
                    with ui.vstack():
                        with ui.bottom_bar():
                            ui.bottom_bar_item("GitHub", icon="github",
                                               href="https://github.com")
                            ui.bottom_bar_item("Home", icon="home", href="/")

            # ── Card 4 — Composability ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Composability", level=2)
                    ui.text('The bar in its real contexts.',
                            color="muted", size="sm")

                    ui.heading('The shape of a mobile shell', level=3)
                    ui.text(
                        'The content, then the bar — exactly what an ``if'
                            ' Screen().is_mobile:`` produces in a layout.',
                        color="muted", size="xs",
                    )
                    with ui.card():
                        with ui.vstack():
                            ui.heading("Ma page", level=3)
                            ui.text("The app's body lives here.",
                                    color="muted")
                            with ui.vstack():
                                with ui.bottom_bar():
                                    for label, icon, href in TABS:
                                        ui.bottom_bar_item(label, icon=icon,
                                                           href=href)

                    ui.heading('Navbar + BottomBar on the same page',
                               level=3)
                    ui.text(
                        'Both own their own ``current_path`` scope — the '
                            'duplication is intended, each must work without '
                            'the other. They stay in agreement about the '
                            'active item.',
                        color="muted", size="xs",
                    )
                    with ui.navbar():
                        with ui.navbar_section(side="left"):
                            ui.heading("Acme", level=3)
                        with ui.navbar_section(side="right"):
                            ui.navbar_item("Tabs", href="/tabs")
                            ui.navbar_item("Bottom", href=PATH)
                    with ui.vstack():
                        with ui.bottom_bar():
                            for label, icon, href in TABS:
                                ui.bottom_bar_item(label, icon=icon, href=href)

                    ui.heading('A tab with a live badge + an action',
                               level=3)
                    with ui.vstack():
                        with ui.bottom_bar():
                            ui.bottom_bar_item("Home", icon="home", href="/")
                            ui.bottom_bar_item("Alerts", icon="bell",
                                               badge=12, color="error")
                            ui.bottom_bar_item("Profile", icon="user",
                                               href="/badge")

            # ── Card 5 — A11y ───────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("A11y", level=2)
                    ui.text(
                        'The root is a ``<nav>`` — a real navigation '
                            'landmark. No ``aria-label`` is imposed (hard-'
                            'coding an English label would be an i18n '
                            'mistake): pass it through the Server '
                            "playground's ``aria-label`` control, especially "
                            'if the page already carries a navbar (two '
                            'unnamed ``nav`` landmarks are unreadable to a '
                            'screen reader).',
                        color="muted", size="sm",
                    )
                    with ui.vstack():
                        with ui.bottom_bar(
                                aria_label="Navigation principale"):
                            for label, icon, href in TABS:
                                ui.bottom_bar_item(label, icon=icon, href=href)

                    ui.heading('aria-current on the current tab', level=3)
                    ui.text(
                        'The tab derived from the URL emits ``aria-'
                            'current="page"`` reactively — the screen reader '
                            'announces where you are.',
                        color="muted", size="sm",
                    )

                    ui.heading("Ordre de tabulation", level=3)
                    ui.text(
                        '``href`` tabs are native ``<a>``s: Tab walks '
                            'them in order, Enter activates. A ``disabled`` '
                            'tab carries ``tabindex=-1`` AND loses all its '
                            'click channels — it is skipped.',
                        color="muted", size="sm",
                    )
                    with ui.vstack():
                        with ui.bottom_bar():
                            ui.bottom_bar_item("First", icon="home", href="/")
                            ui.bottom_bar_item("Skipped", icon="lock",
                                               href="/tabs", disabled=True)
                            ui.bottom_bar_item("Third", icon="user",
                                               href="/badge")

            # ── Card 6 — Server playground ──────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Server playground", level=2)
                    ui.text(
                        'Every prop AND every escape hatch is wired to a '
                            'control; the preview AND the emitted HTML both '
                            'refresh on every change. The ITEM props land on '
                            'the “Bottom” tile — the one pointing at this '
                            'page, hence active — its resting neighbours '
                            'serving as controls.',
                        color="muted", size="sm",
                    )
                    ui.text(
                        'Worth knowing to read the `color` control: on a '
                            'tab bar, the colour paints ONLY the ACTIVE tab —'
                            ' at rest a tab is deliberately `muted`, that is '
                            'the iOS/Android idiom. Set `active` to `False` '
                            'and the colour disappears: that is the '
                            'behaviour, not a fault. At rest, `color` only '
                            'drives the focus halo.',
                        color="muted", size="xs",
                    )
                    server_panel()

            # ── Card 7 — Server events ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Server events", level=2)
                    events_panel()

            # ── Card 8 — Client playground ──────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Client playground", level=2)
                    ui.text(
                        'Mirror of the ``BottomBarItem.BINDABLE_PROPS = '
                            "('active', 'badge', 'disabled')`` contract. All "
                            'three are bound to a ClientState and driven by '
                            'external controls — zero round trips. '
                            '``BottomBar`` itself has NO bindable prop: the '
                            'bar itself has NO prop at all.',
                        color="muted", size="sm",
                    )
                    client = BottomBarClient()
                    with ui.grid(cols={"base": 1, "sm": 3}, gap="md"):
                        with control("active (bound)"):
                            ui.switch(checked=client.active)
                        with control("badge (bound)"):
                            ui.number_input(value=client.badge,
                                            min=0, max=99)
                        with control("disabled (bound)"):
                            ui.switch(checked=client.disabled)

                    ui.divider()

                    with ui.vstack():
                        with ui.bottom_bar():
                            ui.bottom_bar_item("Home", icon="home")
                            ui.bottom_bar_item("Alerts", icon="bell",
                                               active=client.active,
                                               badge=client.badge,
                                               disabled=client.disabled)
                            ui.bottom_bar_item("Profile", icon="user")

                    ui.divider()

                    with ui.vstack():
                        preview = ui.bottom_bar()
                    with preview:
                        ui.bottom_bar_item("Alerts", icon="bell",
                                           active=client.active,
                                           badge=client.badge,
                                           disabled=client.disabled)
                    emitted_html_block(
                        'Emitted HTML — ``bz-attr:data-active`` + ``bz-'
                            'class`` for the active one, ``bz-text`` + ``bz-'
                            'show`` for the counter (a badge at 0 folds '
                            'away), ``bz-attr:aria-disabled`` + ``bz-'
                            'attr:tabindex`` for the lock.',
                        serialize_html(preview),
                    )

            # ── Card 9 — Client events ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Client events", level=2)
                    ui.text(
                        '``click`` wired to a client expression that '
                            "pushes the tab's name onto a ClientState list. "
                            'Zero network.',
                        color="muted", size="sm",
                    )
                    cevents = BottomBarClientEvents()
                    with ui.vstack():
                        with ui.bottom_bar():
                            ui.bottom_bar_item(
                                "Home", icon="home",
                                on_click=cevents.log.push("Home"))
                            ui.bottom_bar_item(
                                "Search", icon="search",
                                on_click=cevents.log.push("Search"))
                            ui.bottom_bar_item(
                                "Profile", icon="user",
                                on_click=cevents.log.push("Profile"))

                    ui.divider()

                    with ui.hstack(justify="between", align="center"):
                        ui.text("Live log (client-reactive)",
                                color="muted", size="sm")
                        ui.button("Clear", variant="ghost", size="xs",
                                  on_click=cevents.log.clear())

                    log_text = ClientExpression(
                        '($bz.state.BottomBarClientEvents.default.log'
                        ' || []).join("\\n") || "(no events yet)"'
                    )
                    ui.text(log_text,
                            color="muted", size="sm",
                            classes="font-mono whitespace-pre")

                    ui.divider()

                    with ui.vstack():
                        preview = ui.bottom_bar()
                    with preview:
                        ui.bottom_bar_item(
                            "Home", icon="home",
                            on_click=cevents.log.push("Home"))
                    emitted_html_block(
                        'Emitted HTML — ``bz-on:click`` carries the '
                            'client expression as is, no ``hx-post`` at all.',
                        serialize_html(preview),
                    )

        # ── The real bar, sticky — outside the cards ─────────────────
        # The page's only bar WITHOUT a wrapper — hence the only one free
        # to stick. Its containing block is the page's container, much
        # taller than it: it stays at the bottom of the viewport through
        # the whole scroll, then settles into its place at the end of the
        # document.
        with ui.bottom_bar():
            for label, icon, href in TABS:
                ui.bottom_bar_item(label, icon=icon, href=href)
