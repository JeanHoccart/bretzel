"""REFERENCE — Cheat sheet.

Everything on one page, Ctrl-F friendly: state, actions, reactivity, and
the traps that keep coming back. Every block is a condensed reminder —
the detail lives in the chapters. It is an INDEX, so it points and does
not teach — cf. the rule at the head of ``examples/docs/main.py``.
"""

from __future__ import annotations

from bretzel import page, ui

from examples.docs.features.shell import shell
from examples.docs.lib.blocks import toplevel_surface_mirror

PATH = "/cheatsheet"


def section(title: str, code: str) -> None:
    with ui.card():
        with ui.vstack(gap="sm"):
            ui.heading(title, level=2)
            ui.code(code, lang="python")


@page(PATH, layout=shell, title="Cheat sheet · Bretzel docs",
      description="The whole Bretzel API on one page: every public name of the Python web framework, grouped by the need it answers.")
def cheatsheet_page() -> None:
    with ui.container(width="xl"):
        with ui.vstack(gap="lg"):
            ui.heading("Cheat sheet", level=1, size="3xl")
            ui.text(
                'The whole of Bretzel condensed onto one page. Ctrl-F what'
                ' you need.',
                color="muted", size="lg",
            )

            # ── What exists, grouped by need — read live ─────────────
            # All the rest of this page is hand-written prose: useful,
            # dense, and it drifts. This block cannot: it enumerates
            # ``bretzel.__all__`` from the package, and an entry with no
            # category makes ``test_docs_coverage`` blush.
            with ui.card():
                with ui.vstack(gap="md"):
                    ui.heading("What one types — the package's surface", level=2)
                    ui.text(
                        'Grouped by the need each name answers, not by its'
                        ' Python nature. A helper callable from a handler '
                        'has exactly one access point: this one.',
                        color="muted", size="sm",
                    )
                    toplevel_surface_mirror()

            section(
                'State — server (4 scopes)',
                'from bretzel.state import PageState, SessionState, UserState, AppState\nfrom bretzel.state import field, validator, computed\n\nclass Cart(SessionState):          # page / session / user / app\n    items: list[dict] = field(default_factory=list)\n    coupon: str = ""\n\n    @validator("coupon")           # receives (self, value), RETURNS the value\n    def _norm(self, v: str) -> str:\n        return v.strip().upper()\n\n    @computed                       # derived, auto-tracked\n    def total(self) -> float:\n        return sum(i["price"] for i in self.items)\n',
            )

            section(
                'State — client (3 persistence modes)',
                'from bretzel.state import ClientState\n\nclass FilterUI(ClientState, persist="local"):\n    #  "memory"  → throwaway (lost on reload)\n    #  "session" → survives a reload, not a close\n    #  "local"   → survives everything\n    sort_by: str = "date"\n',
            )

            section(
                "Actions — server vs client",
                '# Server: on_click = callable → hx-post, HMAC signed\ndef save() -> None:\n    Cart().coupon = ""          # mutation → automatic re-render\nui.button("Save", on_click=save)\n\n# Client: on_click = an expression (string) → no round trip\nui.button("Top", on_click="window.scrollTo(0, 0)")\n\n# Imperative: the method RETURNS the client string\nwith ui.dialog() as d:\n    ui.text("Are you sure?")\nui.button("Open", on_click=d.open())\n\n# Binding: driving a ClientState\npanel = PanelUI()\nui.button("Toggle", on_click=panel.open.toggle())\n',
            )

            section(
                'Reactivity — mutate → re-render',
                'from bretzel import refreshable, ui\n\n@refreshable          # declarative: re-render when Cart changes\ndef cart_view() -> None:\n    for it in ui.each(Cart().items, key="id"):\n        ui.text(it["label"])\n\nfrom bretzel import refresh\nrefresh(cart_view)                 # imperative, from a handler\n',
            )

            with ui.card(color="surface"):
                with ui.vstack(gap="sm"):
                    ui.heading('⚠️ Trap no. 1', level=2)
                    ui.text(
                        'Every file declaring a State MUST start with '
                        '`from __future__ import annotations` (PEP 649) — '
                        'otherwise the fields do not register, silently.',
                        color="muted", size="sm",
                    )
                    ui.code(
                        "from __future__ import annotations   # ← FIRST, always\n",
                        lang="python",
                    )
                    with ui.hstack(align="baseline", gap="sm", wrap=True):
                        ui.text('The other traps:', color="muted", size="sm")
                        ui.link('Traps →', href="/traps")
