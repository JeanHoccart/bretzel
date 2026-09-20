"""The ``Sidebar`` bench's rendering — the ten cards.

Ten cards: Reference / Slots / Edge cases / Composability / A11y /
Server playground / Server events / Client playground / External
controls / Client events.

⚠️ **Every demo sidebar is mounted in a fixed-height frame, and carries
``slots=FIT``.** It is not decorative. The theme's ``root`` slot is
``h-screen`` (100vh): placed as it is in a card, the sidebar measures the
viewport's height and its ``mt-auto`` footer goes outside the frame
(measured: a 720px sidebar in a 380px box, footer at y=649, invisible).
``h-screen`` is also the reason the visual harness had to mount the
sidebar "bare", with no container — the workaround went with the visual
suite on 2026-08-16, the constraint did not.

And the override must be ``h-full!`` with Tailwind v4's ``!``, not
``h-full``: both utilities have the SAME specificity, so the winner is
the last in the compiled sheet, not the last in the ``class`` attribute.
Measured: a bare ``h-full`` loses (720px), ``h-full!`` wins (378px in a
380px box, footer visible).

The day ``h-screen`` leaves the theme — the sidebar today only mounts in
a ``fixed inset-0`` + ``align="stretch"`` parent, where the height
already comes from the flex, so the utility serves nothing there —
``FIT`` disappears from here in one line.

⚠️ The items carry real playground ``href``: a click NAVIGATES (HTMX
partial nav to the shell's outlet). It is intended, it is the wiring we
want to see working. The event cards use items with no ``href`` so the
handler speaks without leaving the page.
"""

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import ClientExpression

from examples.playground.features.inspection import emitted_html_block
from examples.playground.features.sidebar.logic import (
    clear_log,
    log_home,
    log_issues,
    log_logout,
    log_settings,
    parse_extra_attrs,
    server_changed,
)
from examples.playground.features.sidebar.state import (
    COLORS,
    FIT,
    MODES,
    NAV,
    PATH,
    WIDTHS,
    SidebarClient,
    SidebarClientEvents,
    SidebarEvents,
    SidebarPlayground,
)

def frame(height: str = "h-[400px]"):
    """The fixed-height frame a demo sidebar lives in.

    ``align="stretch"`` reproduces exactly what ``examples/``'s six
    shells do (all ``fixed inset-0`` + stretch): it is the flex that
    gives the aside its height, not the theme's utility."""
    return ui.hstack(
        gap="none", align="stretch",
        classes=(
            f"{height} w-full overflow-hidden "
            "rounded-lg border border-text/10"
        ),
    )


def control(label: str):
    block = ui.vstack(gap="xs")
    with block:
        ui.text(label, color="muted", size="xs")
    return block

def build_preview(state: SidebarPlayground):
    kwargs: dict = {
        "width": state.width,
        "collapsible": state.collapsible,
        "open": state.open,
        "slots": FIT,
    }
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

    # The item props driven by the controls land on the entry pointing
    # at THIS page — hence active by URL derivation, its neighbours at
    # rest serving as controls. The same reason as on the bottom_bar
    # bench: `color` paints ONLY the active row, a selector set on an
    # inactive row would look dead.
    treated: dict = {
        "color": state.item_color,
        "disabled": state.item_disabled,
        "icon": state.item_icon or None,
    }
    if state.item_badge:
        treated["badge"] = state.item_badge
    if state.active_mode != "auto":
        treated["active"] = state.active_mode == "true"

    box = ui.sidebar(**kwargs)
    with box:
        ui.sidebar_title("Playground", icon="zap")
        with ui.sidebar_section(label="OVERVIEW"):
            for label, icon, href in NAV:
                if href == PATH:
                    ui.sidebar_item(label, href=href, **treated)
                else:
                    ui.sidebar_item(label, icon=icon, href=href)
        with ui.sidebar_footer(name="Jean Hoccart",
                               subtitle="jean@acme.com"):
            ui.sidebar_footer_item(label="Settings", icon_left="settings")
            ui.sidebar_footer_item(label="Log out", icon_left="log-out",
                                   color="error")
    return box


@refreshable(deps=[SidebarPlayground])
def server_panel() -> None:
    state = SidebarPlayground()

    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control('width (unfolded state)'):
            ui.select(value=state.width, options=[(w, w) for w in WIDTHS],
                      on_change=server_changed)
        with control('collapsible — what "collapsed" means'):
            ui.select(
                value=state.collapsible,
                options=[
                    ("rail", 'rail — a 64px strip of icons, in the flow'),
                    ("offcanvas", 'offcanvas — width 0, in the flow'),
                    ("overlay", "overlay — au-dessus, fond assombri"),
                    ("none", "none — ne se replie jamais"),
                ],
                on_change=server_changed,
            )
        with control("open"):
            ui.switch(checked=state.open, on_change=server_changed)
        with control("item : color (ligne active)"):
            ui.select(value=state.item_color,
                      options=[(c, c) for c in COLORS],
                      on_change=server_changed)
        with control("item : icon (ligne active)"):
            ui.input(value=state.item_icon,
                     placeholder='home / bug / (empty = no icon)',
                     on_change=server_changed)
        with control("item : badge (ligne active)"):
            ui.input(value=state.item_badge,
                     placeholder='3 / 99+ / (empty = no badge)',
                     on_change=server_changed)
        with control("item : disabled (ligne active)"):
            ui.switch(checked=state.item_disabled, on_change=server_changed)
        with control('item: active — the resolution mode'):
            ui.select(value=state.active_mode,
                      options=[("auto", 'None — derived from the URL'),
                               ("true", 'True — forced active'),
                               ("false", 'False — forced inactive')],
                      on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes, placeholder="bg-primary/5",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id, placeholder="my-sidebar",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label, placeholder="Main navigation",
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style, placeholder="border-right-width: 3px",
                     on_change=server_changed)
        with control('extra_attrs (one per line, key=value)'):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="data-test=sidebar",
                        on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip, placeholder="Navigation",
                     on_change=server_changed)
        with control("visible"):
            ui.select(value=state.visible,
                      options=[("on", "True (default)"),
                               ("off", "False (skip render)")],
                      on_change=server_changed)

    ui.divider()

    with frame():
        build_preview(state)
        with ui.vstack(classes="flex-1 min-w-0 p-4"):
            ui.text("Contenu de page", color="muted", size="sm")

    ui.divider()

    emitted_html_block("Emitted HTML", serialize_html(build_preview(state)))


@refreshable(deps=[SidebarEvents])
def events_panel() -> None:
    state = SidebarEvents()

    ui.text(
        "``SidebarItem`` declares ``EVENTS = ('click',)`` — it is the "
            "family's only server event (``Sidebar`` itself declares none: "
            'opening and closing is pure client). Here the entries have NO '
            '``href``: the server handler speaks without the page navigating.'
            ' ``sidebar_footer_item`` carries the same ``on_click`` as '
            '``dropdown_item``, and it is wired too.',
        color="muted", size="sm",
    )

    with frame("h-[340px]"):
        with ui.sidebar(slots=FIT, collapsible="none"):
            with ui.sidebar_section(label="SERVER EVENTS"):
                ui.sidebar_item("Home", icon="home", on_click=log_home)
                ui.sidebar_item("Issues", icon="bug", on_click=log_issues)
                ui.sidebar_item("Settings", icon="settings",
                                on_click=log_settings)
            with ui.sidebar_footer(name="Jean Hoccart", subtitle="compte"):
                ui.sidebar_footer_item(label="Log out", icon_left="log-out",
                                       color="error", on_click=log_logout)
        with ui.vstack(classes="flex-1 min-w-0 p-4"):
            ui.text('Click an entry →', color="muted", size="sm")

    ui.divider()

    with ui.hstack(justify="between", align="center"):
        ui.text("Live log (newest first, last 10)", color="muted", size="sm")
        ui.button("Clear", variant="ghost", size="xs",
                  on_click=clear_log, disabled=not state.log)

    if state.log:
        with ui.vstack(gap="xs"):
            for i, evt in enumerate(reversed(state.log[-10:]), 1):
                ui.text(f"{i}. {evt}", color="muted", size="sm",
                        classes="font-mono")
    else:
        ui.text('(no events yet — click an entry above)',
                color="muted", size="sm")

    ui.divider()

    representative = ui.sidebar(slots=FIT)
    with representative:
        ui.sidebar_item("Home", icon="home", on_click=log_home)
    emitted_html_block(
        'Emitted HTML (SidebarItem with a server handler)',
        serialize_html(representative),
    )


def page() -> None:
    client = SidebarClient()
    client_events = SidebarClientEvents()

    with ui.container():
        with ui.vstack():
            ui.heading("Sidebar", level=1)
            ui.text(
                'A desktop navigation rail. Six pieces: ``ui.sidebar`` '
                    '(the ``<aside>``), ``ui.sidebar_title`` (the header: '
                    'logo + title + toggle), ``ui.sidebar_section`` (a group '
                    'with a subheading), ``ui.sidebar_item`` (a nav row), '
                    '``ui.sidebar_footer`` (the account row pinned at the '
                    'bottom, which opens a popover) and '
                    '``ui.sidebar_footer_item`` (a row of that popover). The '
                    'mobile nav is NOT in the component: it is the '
                    "developer's ``if Screen().is_mobile:``.",
                color="muted",
            )
            ui.text(
                'Two things to know to read this page. Every demo lives '
                    "in a fixed-height frame and carries ``slots={'root': "
                    "'h-full!'}``: the theme puts ``h-screen`` on the root, "
                    'so without the override the sidebar measures 100vh and '
                    'its footer falls out of the frame. And the entries carry'
                    ' real playground ``href``s — a click really navigates.',
                color="muted", size="sm",
            )

            # ── Card 1 — Reference ──────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Reference", level=2)
                    ui.text("Visual scan of every prop.",
                            color="muted", size="sm")

                    ui.heading("Basic — titre, section, items, footer",
                               level=3)
                    ui.text(
                        'The active entry is derived from the URL: '
                            '“Sidebar” points at this page, so it stands out '
                            'on its own.',
                        color="muted", size="xs",
                    )
                    with frame():
                        with ui.sidebar(slots=FIT):
                            ui.sidebar_title("Playground", icon="zap")
                            with ui.sidebar_section(label="OVERVIEW"):
                                for label, icon, href in NAV:
                                    ui.sidebar_item(label, icon=icon,
                                                    href=href)
                            with ui.sidebar_footer(
                                name="Jean Hoccart",
                                subtitle="jean@acme.com",
                            ):
                                ui.sidebar_footer_item(
                                    label="Settings", icon_left="settings")
                                ui.sidebar_footer_item(
                                    label="Log out", icon_left="log-out",
                                    color="error")
                        with ui.vstack(classes="flex-1 min-w-0 p-4"):
                            ui.text("Contenu de page", color="muted",
                                    size="sm")

                    ui.heading('open — unfolded vs collapsed', level=3)
                    ui.text(
                        '``open`` drives ``data-open`` on the root; the '
                            'whole collapse is CSS reading that attribute. '
                            "The title's chevron toggles it.",
                        color="muted", size="xs",
                    )
                    with ui.grid(cols={"base": 1, "lg": 2}, gap="md"):
                        for is_open in (True, False):
                            with ui.vstack(gap="xs"):
                                ui.text(f"open={is_open}", color="muted",
                                        size="xs", classes="font-mono")
                                with frame("h-[300px]"):
                                    with ui.sidebar(slots=FIT, open=is_open):
                                        ui.sidebar_title("App", icon="zap")
                                        with ui.sidebar_section(
                                                label="MAIN"):
                                            ui.sidebar_item(
                                                "Home", icon="home")
                                            ui.sidebar_item(
                                                "Issues", icon="bug",
                                                badge=12)
                                    with ui.vstack(
                                            classes="flex-1 min-w-0 p-3"):
                                        ui.text("page", color="muted",
                                                size="xs")

                    ui.heading('collapsible — what "collapsed" means',
                               level=3)
                    ui.text(
                        'One axis, four values. ``rail`` keeps a 64px '
                            'strip of icons and ``offcanvas`` vanishes — both'
                            ' IN the flow, hence gated on ``md:``. '
                            '``overlay`` leaves the flow and goes over the '
                            'content with a dimmed backdrop: it is the mode '
                            'one mounts on a phone, and the only one not '
                            'gated. ``none`` never collapses and renders no '
                            'chevron.',
                        color="muted", size="xs",
                    )
                    with ui.grid(cols={"base": 1, "lg": 2}, gap="md"):
                        for v in MODES:
                            with ui.vstack(gap="xs"):
                                ui.text(f'collapsible="{v}" · open=False',
                                        color="muted", size="xs",
                                        classes="font-mono")
                                with frame("h-[300px]"):
                                    sb = ui.sidebar(slots=FIT, collapsible=v,
                                                    open=False)
                                    with sb:
                                        ui.sidebar_title("App", icon="zap")
                                        with ui.sidebar_section(
                                                label="MAIN"):
                                            ui.sidebar_item(
                                                "Home", icon="home")
                                            ui.sidebar_item(
                                                "Issues", icon="bug")
                                    with ui.vstack(
                                            classes="flex-1 min-w-0 p-3"):
                                        # ``offcanvas`` and ``overlay``
                                        # take the bar off screen:
                                        # without this button the cell
                                        # shows a bar that can no longer
                                        # be reopened. The page mounts
                                        # several, hence the argument.
                                        ui.sidebar_trigger(sb, size="sm")
                                        ui.text("page", color="muted",
                                                size="xs")

                    ui.heading('width — the UNFOLDED width', level=3)
                    with ui.vstack(gap="md"):
                        for w in WIDTHS:
                            with ui.vstack(gap="xs"):
                                ui.text(f'width="{w}"', color="muted",
                                        size="xs", classes="font-mono")
                                with frame("h-[220px]"):
                                    with ui.sidebar(slots=FIT, width=w):
                                        with ui.sidebar_section(
                                                label="MAIN"):
                                            ui.sidebar_item(
                                                "Dashboard", icon="home")
                                    with ui.vstack(
                                            classes="flex-1 min-w-0 p-3"):
                                        ui.text("page", color="muted",
                                                size="xs")

                    ui.heading("Replier, et revenir", level=3)
                    ui.text(
                        'Every mode EXCEPT ``none`` renders a **clickable'
                            " edge** on the bar's border, in both states; a "
                            '``sidebar_title`` adds its own button. Both live'
                            ' INSIDE the aside, so they leave with it: in '
                            '``offcanvas`` or ``overlay``, the way back is '
                            'placed outside — ``ui.sidebar_trigger()``, '
                            'wherever the app wants. The framework refuses to'
                            ' render a collapsible bar that nothing can '
                            'reopen.',
                        color="muted", size="xs",
                    )
                    ui.text(
                        '``ui.sidebar_trigger`` — only two axes: '
                            '``icon=`` (the repository writes ``panel-left`` '
                            'in chat, ``menu`` in the CRM) and ``size=``, to '
                            'follow the density of the bar it is placed in. '
                            '``variant=`` and ``color=`` RAISE: an app has '
                            'one trigger, and it looks like the rest of its '
                            'top bar.',
                        color="muted", size="xs",
                    )
                    with frame("h-[220px]"):
                        trg = ui.sidebar(slots=FIT, collapsible="overlay",
                                         open=False)
                        with trg:
                            with ui.sidebar_section(label="MAIN"):
                                ui.sidebar_item("Home", icon="home")
                        with ui.vstack(classes="flex-1 min-w-0 p-3",
                                       gap="sm"):
                            with ui.hstack(align="center", gap="sm"):
                                ui.sidebar_trigger(trg, icon="menu",
                                                   size="sm")
                                ui.text("icon=\"menu\" · size=\"sm\"",
                                        color="muted", size="xs",
                                        classes="font-mono")
                            with ui.hstack(align="center", gap="sm"):
                                ui.sidebar_trigger(trg)
                                ui.text('the default', color="muted",
                                        size="xs", classes="font-mono")

                    with ui.grid(cols={"base": 1, "lg": 2}, gap="md"):
                        for coll in ("rail", "none"):
                            with ui.vstack(gap="xs"):
                                ui.text(f'collapsible="{coll}" · untitled',
                                        color="muted", size="xs",
                                        classes="font-mono")
                                with frame("h-[220px]"):
                                    with ui.sidebar(slots=FIT,
                                                    collapsible=coll):
                                        with ui.sidebar_section(
                                                label="MAIN"):
                                            ui.sidebar_item(
                                                "Home", icon="home")
                                    with ui.vstack(
                                            classes="flex-1 min-w-0 p-3"):
                                        ui.text("page", color="muted",
                                                size="xs")

                    ui.heading("item : color", level=3)
                    ui.text(
                        'The colour paints ONLY the active row — at rest '
                            'a row is ``text-muted``.',
                        color="muted", size="xs",
                    )
                    with frame("h-[420px]"):
                        with ui.sidebar(slots=FIT, collapsible="none"):
                            with ui.sidebar_section(label="COLORS"):
                                for c in COLORS:
                                    ui.sidebar_item(c, icon="circle",
                                                    color=c, active=True)
                        with ui.vstack(classes="flex-1 min-w-0 p-3"):
                            ui.text("page", color="muted", size="xs")

                    ui.heading("item : badge / disabled / active", level=3)
                    with frame("h-[340px]"):
                        with ui.sidebar(slots=FIT, collapsible="none"):
                            with ui.sidebar_section(label="STATES"):
                                ui.sidebar_item("Inbox", icon="inbox",
                                                badge=3)
                                ui.sidebar_item("Alerts", icon="bell",
                                                badge="99+")
                                ui.sidebar_item("Soon", icon="lock",
                                                disabled=True)
                                ui.sidebar_item("active=True", icon="check",
                                                active=True)
                                ui.sidebar_item("active=False", icon="x",
                                                active=False, href="/")
                                ui.sidebar_item("auto (URL)", icon="compass",
                                                href=PATH)
                        with ui.vstack(classes="flex-1 min-w-0 p-3"):
                            ui.text("page", color="muted", size="xs")

            # ── Card 2 — Slots ──────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Slots", level=2)
                    ui.text(
                        '``SidebarItem`` declares ``NAMED_SLOTS = '
                            "('icon',)`` and ``ICON_SLOTS = ('icon',)``: a "
                            'string shorthand or a Component. '
                            '``sidebar_title`` and ``sidebar_footer`` accept '
                            'both forms too, for ``icon=`` / ``avatar=``.',
                        color="muted", size="sm",
                    )

                    ui.heading("item : icon=str vs icon=Component", level=3)
                    with frame("h-[280px]"):
                        with ui.sidebar(slots=FIT, collapsible="none"):
                            with ui.sidebar_section(label="ICON SLOT"):
                                ui.sidebar_item("Raccourci", icon="home")
                                ui.sidebar_item(
                                    'Tinted component',
                                    icon=ui.icon("heart", color="error"))
                                ui.sidebar_item(
                                    "Component xs",
                                    icon=ui.icon("search", size="xs"))
                                ui.sidebar_item('With no icon')
                        with ui.vstack(classes="flex-1 min-w-0 p-3"):
                            ui.text("page", color="muted", size="xs")

                    ui.heading('title: icon=str (tinted primary) vs icon=Component '
                        '(keeps ITS colour)', level=3)
                    with ui.grid(cols={"base": 1, "lg": 2}, gap="md"):
                        with frame("h-[200px]"):
                            with ui.sidebar(slots=FIT, collapsible="none"):
                                ui.sidebar_title("String", icon="zap")
                                with ui.sidebar_section():
                                    ui.sidebar_item("Home", icon="home")
                            with ui.vstack(classes="flex-1 min-w-0 p-3"):
                                ui.text("page", color="muted", size="xs")
                        with frame("h-[200px]"):
                            with ui.sidebar(slots=FIT, collapsible="none"):
                                ui.sidebar_title(
                                    "Component",
                                    icon=ui.icon("flame", color="warning"))
                                with ui.sidebar_section():
                                    ui.sidebar_item("Home", icon="home")
                            with ui.vstack(classes="flex-1 min-w-0 p-3"):
                                ui.text("page", color="muted", size="xs")

                    ui.heading("footer : avatar=initiales / str / Component",
                               level=3)
                    ui.text(
                        'With no ``avatar``, the initials are derived '
                            'from the ``name`` (“Jean Hoccart” → “JH”).',
                        color="muted", size="xs",
                    )
                    with ui.grid(cols={"base": 1, "lg": 3}, gap="md"):
                        for label, kw in (
                            ('derived from the name', {}),
                            ("avatar='ZZ'", {"avatar": "ZZ"}),
                            ("avatar=ui.avatar(...)",
                             {"avatar": ui.avatar(initials="BZ",
                                                  color="success")}),
                        ):
                            with ui.vstack(gap="xs"):
                                ui.text(label, color="muted", size="xs",
                                        classes="font-mono")
                                with frame("h-[200px]"):
                                    with ui.sidebar(slots=FIT,
                                                    collapsible="none"):
                                        with ui.sidebar_section():
                                            ui.sidebar_item("Home",
                                                            icon="home")
                                        with ui.sidebar_footer(
                                            name="Jean Hoccart",
                                            subtitle="jean@acme.com",
                                            **kw,
                                        ):
                                            ui.sidebar_footer_item(
                                                label="Log out",
                                                icon_left="log-out",
                                                color="error")
                                    with ui.vstack(
                                            classes="flex-1 min-w-0 p-3"):
                                        ui.text("page", color="muted",
                                                size="xs")

            # ── Card 3 — Edge cases ─────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Edge cases", level=2)

                    ui.heading('A very long label — truncate', level=3)
                    with frame("h-[220px]"):
                        with ui.sidebar(slots=FIT, width="sm",
                                        collapsible="none"):
                            with ui.sidebar_section(
                                    label='A SUBHEADING THAT IS ALSO VERY LONG'):
                                ui.sidebar_item(
                                    'An entry label far too long for the '
                                        "rail's width", icon="home")
                                ui.sidebar_item(
                                    "Long + badge", icon="bug", badge="99+")
                        with ui.vstack(classes="flex-1 min-w-0 p-3"):
                            ui.text("page", color="muted", size="xs")

                    ui.heading('Overflow — the footer stays pinned',
                               level=3)
                    ui.text(
                        'Only the middle area scrolls (the ``scroll`` '
                            'slot, ``flex-1 min-h-0 overflow-y-auto``). The '
                            'title and the footer are ``shrink-0``: a list of'
                            ' 30 entries does not carry them away.',
                        color="muted", size="xs",
                    )
                    with frame("h-[360px]"):
                        with ui.sidebar(slots=FIT, collapsible="none"):
                            ui.sidebar_title('Pinned', icon="zap")
                            with ui.sidebar_section(label='30 ENTRIES'):
                                for i in range(1, 31):
                                    ui.sidebar_item(f"'Entry '{i}",
                                                    icon="circle")
                            with ui.sidebar_footer(name="Jean Hoccart",
                                                   subtitle='pinned'):
                                ui.sidebar_footer_item(label="Log out",
                                                       icon_left="log-out",
                                                       color="error")
                        with ui.vstack(classes="flex-1 min-w-0 p-3"):
                            ui.text("page", color="muted", size="xs")

                    ui.heading('Sections with no label / empty sidebar', level=3)
                    ui.text(
                        'A section with no ``label`` emits neither a '
                            'subheading nor a rail separator — there is no '
                            'caption to fold away.',
                        color="muted", size="xs",
                    )
                    with ui.grid(cols={"base": 1, "lg": 2}, gap="md"):
                        with frame("h-[200px]"):
                            with ui.sidebar(slots=FIT, collapsible="none"):
                                with ui.sidebar_section():
                                    ui.sidebar_item('With no label',
                                                    icon="home")
                                    ui.sidebar_item('No separator either',
                                                    icon="circle")
                            with ui.vstack(classes="flex-1 min-w-0 p-3"):
                                ui.text("page", color="muted", size="xs")
                        with frame("h-[200px]"):
                            ui.sidebar(slots=FIT)
                            with ui.vstack(classes="flex-1 min-w-0 p-3"):
                                ui.text("sidebar vide", color="muted",
                                        size="xs")

                    ui.heading('an external href — no partial nav', level=3)
                    ui.text(
                        'An ``href`` with a scheme (``https:`` / '
                            '``mailto:`` / ``tel:``) steps outside the guard:'
                            ' ``target=_blank``, no ``hx-get`` injected.',
                        color="muted", size="xs",
                    )
                    with frame("h-[200px]"):
                        with ui.sidebar(slots=FIT, collapsible="none"):
                            with ui.sidebar_section(label="LIENS"):
                                ui.sidebar_item("Interne", icon="home",
                                                href="/")
                                ui.sidebar_item(
                                    "Externe", icon="external-link",
                                    href="https://example.com")
                                ui.sidebar_item("Mail", icon="mail",
                                                href="mailto:a@b.c")
                        with ui.vstack(classes="flex-1 min-w-0 p-3"):
                            ui.text("page", color="muted", size="xs")

            # ── Card 4 — Composability ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Composability", level=2)
                    ui.text(
                        'Several sections, a popover footer, and '
                            'arbitrary components between the sections: '
                            'everything that is neither ``sidebar_title`` nor'
                            ' ``sidebar_footer`` lands in the scrolling area.',
                        color="muted", size="sm",
                    )
                    with frame("h-[460px]"):
                        with ui.sidebar(slots=FIT):
                            ui.sidebar_title("Acme", icon="box", href="/")
                            with ui.sidebar_section(label="MAIN"):
                                ui.sidebar_item("Dashboard", icon="home",
                                                href="/")
                                ui.sidebar_item("Issues", icon="bug",
                                                badge=42)
                                ui.sidebar_item("Releases", icon="rocket")
                            with ui.sidebar_section(label="INSIGHTS"):
                                ui.sidebar_item("Analytics",
                                                icon="bar-chart-3")
                                ui.sidebar_item("Reports", icon="file-text")
                            with ui.sidebar_section(label="ACCOUNT"):
                                ui.sidebar_item("Settings", icon="settings")
                                ui.sidebar_item("Billing", icon="credit-card")
                            with ui.sidebar_footer(name="Jean Hoccart",
                                                   subtitle="jean@acme.com",
                                                   color="secondary"):
                                ui.sidebar_footer_item(
                                    label="Profile", icon_left="user",
                                    href="/")
                                ui.sidebar_footer_item(
                                    label="Settings", icon_left="settings",
                                    shortcut="⌘,")
                                ui.sidebar_footer_item(
                                    label="Docs", icon_left="book",
                                    icon_right="external-link",
                                    href="https://example.com")
                                ui.sidebar_footer_item(
                                    label='Soon', icon_left="lock",
                                    disabled=True)
                                ui.sidebar_footer_item(
                                    label="Log out", icon_left="log-out",
                                    color="error")
                        with ui.vstack(classes="flex-1 min-w-0 p-4"):
                            ui.text("Contenu de page", color="muted",
                                    size="sm")

            # ── Card 5 — A11y ───────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("A11y", level=2)
                    ui.text(
                        'The root is ``role=navigation`` + ``aria-'
                            'label=Sidebar`` (both overridable). Every entry '
                            'carries an ``aria-label`` with its own text — in'
                            ' the collapsed rail the visible label is '
                            '``hidden``, and a hover tooltip is an affordance'
                            ' for neither the keyboard nor a screen reader. '
                            'The shared tooltip panel is therefore ``aria-'
                            'hidden``. A ``disabled`` entry carries ``aria-'
                            'disabled`` AND loses its ``href`` + its ``hx-*``'
                            ' + its ``tabindex``.',
                        color="muted", size="sm",
                    )

                    ui.heading("Parcours au clavier", level=3)
                    ui.text(
                        'Tab into the list: the focus ring must be '
                            'entirely visible and its offset must blend into '
                            "the sidebar's background. It does not yet — the "
                            'offset is painted ``ring-offset-background`` '
                            '(#020617) while the sidebar is ``bg-surface`` '
                            '(#0f172a), and the row sits at 0px from its '
                            'scrolling box in ``overflow-x-hidden``, so the '
                            'ring is clipped left and right.',
                        color="muted", size="xs",
                    )
                    with frame("h-[300px]"):
                        with ui.sidebar(slots=FIT, collapsible="none"):
                            with ui.sidebar_section(label="TAB ORDER"):
                                ui.sidebar_item("Premier", icon="home",
                                                href="/")
                                ui.sidebar_item('Second', icon="bug",
                                                href="/badge")
                                ui.sidebar_item('Locked', icon="lock",
                                                disabled=True, href="/")
                                ui.sidebar_item('Third', icon="settings",
                                                href="/icon")
                        with ui.vstack(classes="flex-1 min-w-0 p-3"):
                            ui.text("page", color="muted", size="xs")

            # ── Card 6 — Server playground ──────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Server playground", level=2)
                    ui.text(
                        'Every prop of the container and of the entry, '
                            'plus the universal escape hatches. The panel re-'
                            'renders on the server at every change.',
                        color="muted", size="sm",
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
                        "``Sidebar.BINDABLE_PROPS = ('open',)`` and "
                            "``SidebarItem.BINDABLE_PROPS = ('active', "
                            "'badge', 'disabled')``. All four are wired below"
                            ' to a ``ClientState``: no server round trip, the'
                            ' runtime writes into the DOM.',
                        color="muted", size="sm",
                    )

                    with ui.grid(cols={"base": 1, "sm": 2, "md": 4},
                                 gap="md"):
                        with control("sidebar : open"):
                            ui.switch(checked=client.expanded)
                        with control("item : active"):
                            ui.switch(checked=client.active)
                        with control("item : disabled"):
                            ui.switch(checked=client.disabled)
                        with control("item : badge"):
                            ui.number_input(value=client.badge, min=0, max=99)

                    with frame("h-[300px]"):
                        with ui.sidebar(slots=FIT, open=client.expanded):
                            ui.sidebar_title("Client", icon="zap")
                            with ui.sidebar_section(label="BOUND"):
                                ui.sidebar_item('Driven', icon="home",
                                                active=client.active,
                                                badge=client.badge,
                                                disabled=client.disabled)
                                ui.sidebar_item('Control', icon="circle")
                        with ui.vstack(classes="flex-1 min-w-0 p-3"):
                            ui.text("page", color="muted", size="xs")

                    ui.divider()

                    bound = ui.sidebar(slots=FIT, open=client.expanded)
                    with bound:
                        ui.sidebar_item('Driven', icon="home",
                                        active=client.active,
                                        badge=client.badge,
                                        disabled=client.disabled)
                    emitted_html_block(
                        'Emitted HTML (SSR snapshot — the runtime takes over)',
                        serialize_html(bound),
                    )

            # ── Card 9 — External controls — the 3 modes ────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("External controls — the 3 modes", level=2)
                    ui.text(
                        "``Sidebar.IMPERATIVE = ('open', 'close', "
                            "'toggle')``. Bretzel's three imperative-contract"
                            ' modes, side by side.',
                        color="muted", size="sm",
                    )

                    ui.heading('Mode 1 — imperative only (no binding)',
                               level=3)
                    ui.text(
                        'With no binding, the method dispatches a DOM '
                            'event (``bz-open`` / ``bz-close`` / ``bz-'
                            'toggle``) the root listens for.',
                        color="muted", size="xs",
                    )
                    imperative = ui.sidebar(slots=FIT, collapsible="none")
                    with ui.hstack(gap="sm"):
                        ui.button("open()", size="xs", variant="outline",
                                  on_click=imperative.open())
                        ui.button("close()", size="xs", variant="outline",
                                  on_click=imperative.close())
                        ui.button("toggle()", size="xs",
                                  on_click=imperative.toggle())
                    with frame("h-[240px]"):
                        with imperative:
                            ui.sidebar_title('Imperative', icon="zap")
                            with ui.sidebar_section(label="MAIN"):
                                ui.sidebar_item("Home", icon="home")
                                ui.sidebar_item("Issues", icon="bug")
                        with ui.vstack(classes="flex-1 min-w-0 p-3"):
                            ui.text("page", color="muted", size="xs")

                    ui.heading("Mode 2 — ClientBinding seul", level=3)
                    ui.text(
                        '``open=`` receives a binding: the switch and the'
                            ' sidebar read the same client signal.',
                        color="muted", size="xs",
                    )
                    with ui.hstack(gap="sm", align="center"):
                        ui.switch(checked=client.expanded)
                        ui.text("client.expanded", color="muted", size="xs",
                                classes="font-mono")
                    with frame("h-[240px]"):
                        with ui.sidebar(slots=FIT, collapsible="none",
                                        open=client.expanded):
                            ui.sidebar_title("Binding", icon="zap")
                            with ui.sidebar_section(label="MAIN"):
                                ui.sidebar_item("Home", icon="home")
                        with ui.vstack(classes="flex-1 min-w-0 p-3"):
                            ui.text("page", color="muted", size="xs")

                    ui.heading('Mode 3 — both (write-through)', level=3)
                    ui.text(
                        'With a binding, ``.toggle()`` writes INTO the '
                            'binding: the switch above follows the button, '
                            'and the other way round.',
                        color="muted", size="xs",
                    )
                    both = ui.sidebar(slots=FIT, collapsible="none",
                                      open=client.expanded)
                    with ui.hstack(gap="sm", align="center"):
                        ui.button("toggle()", size="xs", on_click=both.toggle())
                        ui.switch(checked=client.expanded)
                        ui.text('the same signal', color="muted", size="xs")
                    with frame("h-[240px]"):
                        with both:
                            ui.sidebar_title('Both', icon="zap")
                            with ui.sidebar_section(label="MAIN"):
                                ui.sidebar_item("Home", icon="home")
                        with ui.vstack(classes="flex-1 min-w-0 p-3"):
                            ui.text("page", color="muted", size="xs")

            # ── Card 10 — Client events ─────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Client events", level=2)
                    ui.text(
                        "``SidebarItem.EVENTS = ('click',)`` as a pure "
                            'client expression — zero round trips, the log '
                            'lives in a ``ClientState``.',
                        color="muted", size="sm",
                    )

                    with frame("h-[260px]"):
                        with ui.sidebar(slots=FIT, collapsible="none"):
                            with ui.sidebar_section(label="CLIENT EVENTS"):
                                for name in ("Home", "Issues", "Settings"):
                                    ui.sidebar_item(
                                        name, icon="circle",
                                        on_click=client_events.log.push(name),
                                    )
                        with ui.vstack(classes="flex-1 min-w-0 p-3"):
                            ui.text('Click an entry →', color="muted",
                                    size="xs")

                    ui.divider()

                    with ui.hstack(justify="between", align="center"):
                        ui.text("Live log (client-reactive)",
                                color="muted", size="sm")
                        ui.button("Clear", variant="ghost", size="xs",
                                  on_click=client_events.log.clear())

                    ui.text(
                        ClientExpression(
                            "($bz.state.SidebarClientEvents.default.log"
                            ' || []).join("\\n") || "(no events yet)"'
                        ),
                        color="muted", size="sm",
                        classes="font-mono whitespace-pre",
                    )

                    ui.divider()

                    representative = ui.sidebar(slots=FIT)
                    with representative:
                        ui.sidebar_item(
                            "Home", icon="home",
                            on_click=client_events.log.push("Home"),
                        )
                    emitted_html_block(
                        'Emitted HTML (SidebarItem with a client expression)',
                        serialize_html(representative),
                    )
