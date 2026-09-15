"""``Avatar`` test bench.

Seven visual cards : Reference / Slots / Edge cases / Composability /
A11y / Server playground / Client playground. ``BINDABLE_PROPS =
("src", "initials", "status")`` — user data + presence are bindable ;
size / shape / color stay design-time. No events.

Seven props : ``src`` / ``alt`` / ``initials`` / ``size`` / ``shape``
/ ``color`` / ``status``.
"""

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import ClientState, PageState, field

from examples.playground.features.inspection import emitted_html_block


PATH = "/avatar"


SIZES    = ["xs", "sm", "md", "lg", "xl", "2xl"]
SHAPES   = ["circle", "square"]
COLORS   = ["primary", "secondary", "success", "warning",
            "error", "info", "muted"]
STATUSES = ["online", "offline", "busy", "away"]


class AvatarPlayground(PageState):
    src:         str = field(default="")
    alt:         str = field(default="")
    initials:    str = field(default="AD")
    size:        str = field(default="md")
    shape:       str = field(default="circle")
    color:       str = field(default="primary")
    status:      str = field(default="")
    # Escape hatches.
    classes:     str = field(default="")
    custom_id:   str = field(default="")
    aria_label:  str = field(default="")
    style:       str = field(default="")
    extra_attrs: str = field(default="")
    # Universal modifiers.
    visible:     str = field(default="on")
    tooltip:     str = field(default="")


class AvatarClient(ClientState, persist="memory"):
    """Mirror of Avatar's BINDABLE_PROPS = ('status',)."""

    status:   str = field(default="online")


def server_changed(state: AvatarPlayground) -> None:
    # Typed param → the dispatcher hydrates the changed
    # control's value into ``state`` (coerced + persisted).
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


def build_preview(state: AvatarPlayground):
    kwargs: dict = {
        "size": state.size,
        "shape": state.shape,
        "color": state.color,
    }
    if state.src:
        kwargs["src"] = state.src
    if state.alt:
        kwargs["alt"] = state.alt
    if state.initials:
        kwargs["initials"] = state.initials
    if state.status:
        kwargs["status"] = state.status
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
    return ui.avatar(**kwargs)


def control(label: str):
    block = ui.vstack(gap="xs")
    with block:
        ui.text(label, color="muted", size="xs")
    return block


@refreshable(deps=[AvatarPlayground])
def server_panel() -> None:
    state = AvatarPlayground()

    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control("src (image URL)"):
            ui.input(value=state.src,
                     placeholder="https://example.com/me.jpg",
                     on_change=server_changed)
        with control("alt (image alt text)"):
            ui.input(value=state.alt,
                     placeholder="Ada Lovelace",
                     on_change=server_changed)
        with control("initials (fallback)"):
            ui.input(value=state.initials, placeholder="AD",
                     on_change=server_changed)
        with control("size"):
            ui.select(value=state.size,
                      options=[(s, s) for s in SIZES],
                      on_change=server_changed)
        with control("shape"):
            ui.select(value=state.shape,
                      options=[(s, s) for s in SHAPES],
                      on_change=server_changed)
        with control("color"):
            ui.select(value=state.color,
                      options=[(c, c) for c in COLORS],
                      on_change=server_changed)
        with control("status (empty = no dot)"):
            ui.select(value=state.status,
                      options=[("", "(none)")]
                              + [(s, s) for s in STATUSES],
                      on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes,
                     placeholder="!ring-2",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id, placeholder="my-avatar",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label,
                     placeholder="User avatar",
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style,
                     placeholder="border: 2px solid white",
                     on_change=server_changed)
        with control("extra_attrs (one per line, key=value)"):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="data-test=avatar",
                        on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip,
                     placeholder="Ada Lovelace",
                     on_change=server_changed)
        with control("visible"):
            ui.select(value=state.visible,
                      options=[("on", "True (default)"),
                               ("off", "False (skip render)")],
                      on_change=server_changed)

    ui.divider()

    with ui.flex(justify="center", align="center"):
        build_preview(state)

    ui.divider()

    emitted_html_block(
        "Emitted HTML",
        serialize_html(build_preview(state)),
    )


def page() -> None:
    with ui.container():
        with ui.vstack():
            ui.heading("Avatar", level=1)
            ui.text(
                "User chip with image or initials fallback. Optional "
                "status dot overlay (online / offline / busy / "
                "away). Circle by default, ``shape=\"square\"`` "
                "available. The Server playground card stress-tests "
                "every prop ; the emitted HTML is shown live "
                "underneath.",
                color="muted",
            )

            # ── Card 1 — Reference ──────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Reference", level=2)
                    ui.text("Visual scan of every prop.",
                            color="muted", size="sm")

                    ui.heading("name= (derives initials AND alt)", level=3)
                    ui.text(
                        "The recommended way to call this component : "
                        "pass the person's name and it derives both the "
                        "letters and the image's alt text. Without it, "
                        "an avatar with a photo emits alt=\"\" — which "
                        "declares a DECORATIVE image, so a screen reader "
                        "skips the person entirely.",
                        color="muted", size="sm",
                    )
                    with ui.hstack(align="end", gap="lg"):
                        ui.avatar(name="Jean Hoccart")
                        ui.avatar(name="Ada Lovelace", color="success")
                        ui.avatar(
                            name="Jean Hoccart",
                            src="https://i.pravatar.cc/96?u=named",
                        )

                    ui.heading("Sizes (initials)", level=3)
                    with ui.hstack(align="end"):
                        for s in SIZES:
                            ui.avatar(initials="AB", size=s)

                    ui.heading("Sizes (image)", level=3)
                    with ui.hstack(align="end"):
                        for s in SIZES:
                            ui.avatar(
                                src="https://i.pravatar.cc/96?u=ref",
                                size=s,
                                alt="ref",
                            )

                    ui.heading("Shapes", level=3)
                    with ui.hstack(gap="lg"):
                        ui.avatar(initials="AB", shape="circle")
                        ui.avatar(initials="AB", shape="square")

                    ui.heading("Colors (initials fallback)", level=3)
                    with ui.hstack(wrap=True):
                        for c in COLORS:
                            ui.avatar(initials=c[0].upper(), color=c)

                    ui.heading("Status overlays", level=3)
                    with ui.hstack(wrap=True):
                        ui.avatar(initials="ON", status="online")
                        ui.avatar(initials="OF", status="offline")
                        ui.avatar(initials="BS", status="busy")
                        ui.avatar(initials="AW", status="away")

            # ── Card 2 — Slots ──────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Slots", level=2)
                    ui.text(
                        "Two content slots : ``src`` (image URL) and "
                        "``initials`` (text fallback). When ``src`` "
                        "is set it covers the chip ; when only "
                        "``initials`` is set the tinted square shows "
                        "the letters. Empty for both → plain "
                        "placeholder.",
                        color="muted", size="sm",
                    )

                    ui.heading("Image only (src)", level=3)
                    with ui.hstack(gap="lg"):
                        ui.avatar(src="https://i.pravatar.cc/96?u=1",
                                  alt="User 1")
                        ui.avatar(src="https://i.pravatar.cc/96?u=2",
                                  alt="User 2",
                                  shape="square")

                    ui.heading("Initials only (no src)", level=3)
                    with ui.hstack(gap="lg"):
                        ui.avatar(initials="AD", color="primary")
                        ui.avatar(initials="JD", color="success")
                        ui.avatar(initials="ML", color="warning")

                    ui.heading("Neither (plain placeholder)", level=3)
                    with ui.hstack(gap="lg"):
                        ui.avatar(color="muted")
                        ui.avatar(color="primary", shape="square")

                    ui.text(
                        "``src`` / ``initials`` / ``status`` accept "
                        "ClientBinding — see Card 8 (Client "
                        "playground) below for the live binding demo.",
                        color="muted", size="sm",
                    )

            # ── Card 3 — Edge cases ─────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Edge cases", level=2)
                    ui.text("Edge inputs that historically break.",
                            color="muted", size="sm")

                    ui.heading("Broken image URL (browser fallback)",
                               level=3)
                    ui.text(
                        "Browser shows the ``alt=`` text when load "
                        "fails. Pair with ``initials=`` for a "
                        "typed fallback chip instead.",
                        color="muted", size="xs",
                    )
                    ui.avatar(
                        src="https://invalid.example/no-such-image.jpg",
                        alt="Fallback alt",
                        initials="??",
                    )

                    ui.heading("Very long initials (overflow)", level=3)
                    ui.avatar(initials="ALOTOFINITIALS")

                    ui.heading("Emoji initials", level=3)
                    with ui.hstack(gap="lg"):
                        ui.avatar(initials="🚀")
                        ui.avatar(initials="♥")
                        ui.avatar(initials="中")

                    ui.heading("Status without initials or image",
                               level=3)
                    ui.avatar(status="online", color="muted")

                    ui.heading("Image + initials (image wins)", level=3)
                    ui.text(
                        "When both are passed the image takes "
                        "precedence ; initials only show on load "
                        "failure (via the browser alt fallback).",
                        color="muted", size="xs",
                    )
                    ui.avatar(src="https://i.pravatar.cc/96?u=both",
                              initials="??", alt="With initials")

            # ── Card 4 — Composability ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Composability", level=2)
                    ui.text("Avatar in common contexts.",
                            color="muted", size="sm")

                    ui.heading("User row (hstack)", level=3)
                    with ui.vstack(gap="sm"):
                        for (name, initials, color, status) in (
                            ("Ada Lovelace",     "AL", "primary", "online"),
                            ("Grace Hopper",     "GH", "success", "away"),
                            ("Margaret Hamilton","MH", "info",    "busy"),
                        ):
                            with ui.hstack(align="center", gap="md"):
                                ui.avatar(initials=initials,
                                          color=color, status=status)
                                with ui.vstack(gap="xs"):
                                    ui.text(name, weight="bold")
                                    ui.text(status,
                                            color="muted", size="sm")

                    ui.heading("Stacked avatars (contributors strip)",
                               level=3)
                    with ui.hstack(classes="-space-x-2"):
                        ui.avatar(initials="A", color="primary",
                                  classes="!ring-2 !ring-background")
                        ui.avatar(initials="B", color="success",
                                  classes="!ring-2 !ring-background")
                        ui.avatar(initials="C", color="warning",
                                  classes="!ring-2 !ring-background")
                        ui.avatar(initials="+3", color="muted",
                                  classes="!ring-2 !ring-background")

                    ui.heading("Inside ui.card (profile header)",
                               level=3)
                    with ui.card():
                        with ui.hstack(align="center", gap="md"):
                            ui.avatar(initials="AL", color="primary",
                                      size="lg", status="online")
                            with ui.vstack(gap="xs"):
                                ui.heading("Ada Lovelace", level=3)
                                ui.text("ada@example.com",
                                        color="muted", size="sm")

                    ui.heading("Inside ui.tooltip", level=3)
                    with ui.tooltip("Ada Lovelace — online"):
                        ui.avatar(initials="AL", color="primary",
                                  status="online")

            # ── Card 5 — A11y ───────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("A11y", level=2)
                    ui.text(
                        "When ``src=`` is set, pair with ``alt=`` so "
                        "screen readers describe the picture. When "
                        "only ``initials=`` are shown the chip is "
                        "treated as decorative — pair with a "
                        "neighbouring text label or pass "
                        "``aria_label=`` if it carries meaning. "
                        "Status dots emit "
                        "``role=\"status\"`` + ``aria-label`` "
                        "automatically.",
                        color="muted", size="sm",
                    )
                    with ui.hstack(gap="lg"):
                        ui.avatar(src="https://i.pravatar.cc/96?u=a11y",
                                  alt="Ada Lovelace's profile picture")
                        ui.avatar(initials="AL",
                                  aria_label="Ada Lovelace",
                                  status="online")

            # ── Card 6 — Server playground ──────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Server playground", level=2)
                    ui.text(
                        "Every prop AND every escape hatch is wired "
                        "to a control ; the preview AND the emitted "
                        "HTML both refresh on every change.",
                        color="muted", size="sm",
                    )
                    server_panel()

            # ── Card 7 — Client playground ──────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Client playground", level=2)
                    ui.text(
                        "Mirror of Avatar's ``BINDABLE_PROPS = "
                        "('status',)`` contract. The status overlay "
                        "flips through a ``bz-attr`` directive — no "
                        "round-trip. ``src`` / ``initials`` and the "
                        "visual props (size / shape / color) are "
                        "design-time.",
                        color="muted", size="sm",
                    )
                    client = AvatarClient()
                    with ui.grid(cols={"base": 1, "sm": 3}, gap="md"):
                        with control("status"):
                            ui.select(value=client.status,
                                      options=[("", "(none)")]
                                              + [(s, s) for s in STATUSES])

                    ui.divider()

                    with ui.flex(justify="center", align="center"):
                        ui.avatar(initials="JD",
                                  status=client.status,
                                  color="primary", size="xl")

                    ui.divider()

                    emitted_html_block(
                        "Emitted HTML — bz-attr on the status overlay "
                        "(src / initials are static).",
                        serialize_html(
                            ui.avatar(initials="JD",
                                      status=client.status,
                                      color="primary", size="xl")
                        ),
                    )
