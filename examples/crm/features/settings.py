"""features/settings — screen 10: the preferences, and validation.

What this screen puts under constraint: ``ui.form`` + ``ui.form_field`` +
validation + ``ui.toggle_group`` + ``ui.select`` **at density** — ten
fields in a page, not one field in a demo card. It is here that one sees
whether the heights line up when a `switch`, a `select`, a
`toggle_group` and an `input` follow each other in the same grid.

Validation is the second subject. A validator that **raises** populates
``form.errors``, and a ``ui.form_field`` with no ``error=`` deduces its
field from the input it wraps and shows the message on its own. The only
wiring to do at the call site is not to write when ``form.errors`` is not
empty.
"""

from __future__ import annotations

from bretzel import Feature, page, refreshable, ui
from bretzel.state import UserState, field, validator
from bretzel.theme import ColorScheme
from examples.crm.features.shell import shell

DENSITIES: tuple[tuple[str, str], ...] = (
    ("sm", "Compacte"), ("md", "Normale"), ("lg", "Airy"),
)
#: The three modes the base layer understands. ``"system"`` follows the
#: operating system's preference; ``"auto"`` is an inherited alias for it,
#: not offered here — one way of doing each thing.
SCHEMES: tuple[tuple[str, str], ...] = (
    ("light", "Clair"), ("dark", "Sombre"), ("system", "System"),
)
LANDINGS: tuple[tuple[str, str], ...] = (
    ("/", "Pipeline"), ("/accounts", "Accounts"), ("/contacts", "Contacts"),
    ("/activities", "Activities"), ("/reports", "Reports"),
)
PER_PAGE: tuple[tuple[str, str], ...] = (
    ("10", "10 lignes"), ("25", "25 lignes"), ("50", "50 lignes"),
    ("100", "100 lignes"),
)
#: Multi-selection: these are channels, not modes. A `toggle_group`
#: `multiple=True` says that better than a row of `switch`, which would
#: suggest the three are independent the way a setting is.
CHANNELS: tuple[tuple[str, str], ...] = (
    ("app", "In the app"), ("mail", "By email"), ("digest", "Daily digest"),
)


class Preferences(UserState):
    """What the user has chosen.

    ``UserState`` since accounts were added — it was a ``SessionState``
    as long as the app had no sign-in. The change is not cosmetic: the
    settings now follow the PERSON, so they survive changing browser and
    do NOT follow the machine. Signing out rotates the session, which
    would have erased preferences carried by it.

    ⚠️ A ``UserState`` raises ``AuthRequiredError`` (401) outside a
    session. This class is read by the contacts list ("rows per page"):
    so everything that touches it is behind the guard, by construction.
    """

    densite: str = field(default='md')
    atterrissage: str = field(default='/')
    par_page: str = field(default='25')
    #: ``list``, because a multiple selection IS a list. The component's
    #: hidden field posts back JSON, and the base layer decodes it on the
    #: way (``_coerce_composite``) — the app has nothing left to undo. It
    #: did have to: it was the work's finding 19, fixed since.
    canaux: list = field(default_factory=lambda: ["app"])
    email_rapport: str = field(default='')
    signature: str = field(default='')
    archiver_perdus: bool = field(default=True)

    @validator("canaux")
    def _canaux(cls, value: list) -> list:
        """Keep only known channels. The JSON decoding, for its part, is
        done by the base layer before arriving here."""
        keys = {k for k, _label in CHANNELS}
        return [v for v in value if v in keys]

    @validator("email_rapport")
    def _email(cls, value: str) -> str:
        """Raises on an invalid address — ``form.errors`` collects it and
        the ``form_field`` wrapping the input shows it with no wiring."""
        clean = (value or "").strip().lower()[:120]
        if not clean:
            return ""
        if "@" not in clean or clean.startswith("@") or clean.endswith("@"):
            raise ValueError("Invalid address — an @ or a domain is missing.")
        if "." not in clean.rsplit("@", 1)[-1]:
            raise ValueError("The domain must contain a dot.")
        return clean

    @validator("signature")
    def _signature(cls, value: str) -> str:
        clean = (value or "").strip()
        if len(clean) > 240:
            raise ValueError("240 characters at most — it is a mail footer.")
        return clean

    @validator("densite")
    def _densite(cls, value: str) -> str:
        return value if value in {k for k, _l in DENSITIES} else "md"

    @validator("par_page")
    def _par_page(cls, value: str) -> str:
        return value if value in {k for k, _l in PER_PAGE} else "25"


def save_preferences(form: Preferences) -> None:
    """The guard fits in one line: nothing is confirmed if a field raised.

    The valid values ARE already written (each ``__set__`` succeeded) —
    what this guard prevents is saying "saved" when two fields out of ten
    were refused.
    """
    if form.errors:
        ui.notification("Fix the fields in red.", variant="error",
                        duration_ms=2500)
        return
    ui.notification("Preferences saved", variant="success",
                    duration_ms=2000)


def reset_preferences() -> None:
    prefs = Preferences()
    prefs.densite, prefs.atterrissage, prefs.par_page = "md", "/", "25"
    prefs.canaux = ["app"]
    prefs.email_rapport, prefs.signature = "", ""
    prefs.archiver_perdus = True
    ui.notification("Preferences reset", variant="info",
                    duration_ms=2000)


@refreshable(deps=[Preferences])
def preferences_form() -> None:
    prefs = Preferences()
    with ui.form(on_submit=save_preferences):
        with ui.vstack(gap="lg"):
            with ui.card(padding="md"):
                with ui.vstack(gap="md"):
                    ui.heading("Display", level=2, size="md")
                    # ``min_col`` and not window breakpoints: an ``xl:``
                    # prefix reads the VIEWPORT's width, not the one the
                    # grid really has. Under this shell, the sidebar
                    # takes 256 px — so on a 1440 window the grid only
                    # has ~1024 px, stayed at four columns, and every
                    # cell fell to 244 px for a ``ui.toggle_group`` that
                    # asks for 256. Measured: 11.9 px over its
                    # neighbour.
                    with ui.grid(min_col="16rem", gap="md"):
                        # ⚠️ The ONLY setting on this page that does not
                        # go through the server. ``ColorScheme`` is a
                        # framework ``ClientState``, persisted in
                        # ``localStorage``: the ``toggle_group`` binds
                        # straight to it
                        # (``$bz.state.ColorScheme.default.mode``), so the
                        # theme flips with no round trip and no "Save".
                        # It is not in ``Preferences`` for that reason —
                        # putting it there would make it wait for a form
                        # submission to change a colour.
                        with ui.form_field(
                            label="Theme",
                            hint="Follows the system by default.",
                        ):
                            ui.toggle_group(value=ColorScheme().mode,
                                            options=list(SCHEMES),
                                            size=prefs.densite)
                        with ui.form_field(
                            label="Density",
                            hint="Applies to tables and lists.",
                        ):
                            ui.toggle_group(value=prefs.densite,
                                            options=list(DENSITIES),
                                            size=prefs.densite)
                        with ui.form_field(label="Landing page"):
                            ui.select(value=prefs.atterrissage,
                                      options=list(LANDINGS),
                                      size=prefs.densite)
                        with ui.form_field(label="Rows per page"):
                            ui.select(value=prefs.par_page,
                                      options=list(PER_PAGE),
                                      size=prefs.densite)

            with ui.card(padding="md"):
                with ui.vstack(gap="md"):
                    ui.heading("Notifications", level=2, size="md")
                    with ui.grid(min_col="16rem", gap="md"):
                        with ui.form_field(
                            label="Channels",
                            hint="Several choices allowed.",
                        ):
                            ui.toggle_group(value=prefs.canaux,
                                            options=list(CHANNELS),
                                            multiple=True, size=prefs.densite)
                        with ui.form_field(
                            label="Report email",
                            hint="Empty = nothing sent.",
                        ):
                            ui.input(value=prefs.email_rapport, type="email",
                                     icon_left="mail", size=prefs.densite,
                                     placeholder="me@example.com")
                        with ui.form_field(label="Lost deals"):
                            # No ``on_change=``: an unticked box posts
                            # nothing in HTML, but the base layer now
                            # emits a hidden companion carrying the
                            # ``false``. It was the work's finding 20 —
                            # a handler was needed for a switch to be
                            # able to switch off.
                            ui.switch(checked=prefs.archiver_perdus,
                                      label="Archive automatically",
                                      size=prefs.densite)

            with ui.card(padding="md"):
                with ui.vstack(gap="md"):
                    ui.heading("Signature", level=2, size="md")
                    # ⚠️ "Default owner" was REMOVED when the
                    # accounts arrived: for a salesperson the only legal
                    # choice is themselves, and for the directorate it is
                    # the sidebar's selector. A setting that can take only
                    # one value is not a setting.
                    with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
                        with ui.form_field(
                            label="Message footer",
                            hint="240 characters at most.",
                        ):
                            ui.textarea(value=prefs.signature, rows=3,
                                        size=prefs.densite,
                                        placeholder="Kind regards,…")

            with ui.hstack(justify="end", gap="sm"):
                ui.button("Reset", variant="ghost",
                          icon_left="rotate-ccw", on_click=reset_preferences)
                ui.button("Save", type="submit", color="primary",
                          icon_left="save")


@page("/settings", layout=shell, title="Settings")
def settings_page() -> None:
    with ui.vstack(gap="lg"):
        ui.heading("Settings", level=1, size="2xl")
        preferences_form()


feature = Feature(
    name="settings",
    kind="page",
    provides=[settings_page, Preferences],
    uses=[],
)
