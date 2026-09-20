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
from examples.docs.lib.i18n import tr

PATH = "/cheatsheet"


def section(title: str, code: str) -> None:
    with ui.card():
        with ui.vstack(gap="sm"):
            ui.heading(title, level=2)
            ui.code(code, lang="python")


@page(PATH, layout=shell, title="Cheat-sheet")
def cheatsheet_page() -> None:
    with ui.container(width="xl"):
        with ui.vstack(gap="lg"):
            ui.heading("Cheat-sheet", level=1, size="3xl")
            ui.text(
                tr('The whole of Bretzel condensed onto one page. Ctrl-F what'
                   ' you need.',
                   'Le condensé de tout Bretzel sur une page. Ctrl-F ton '
                   'besoin.'),
                color="muted", size="lg",
            )

            # ── What exists, grouped by need — read live ─────────────
            # All the rest of this page is hand-written prose: useful,
            # dense, and it drifts. This block cannot: it enumerates
            # ``bretzel.__all__`` from the package, and an entry with no
            # category makes ``test_docs_coverage`` blush.
            with ui.card():
                with ui.vstack(gap="md"):
                    ui.heading(tr("What one types — the package's surface",
                                  "Ce qu'on tape — la surface du paquet"), level=2)
                    ui.text(
                        tr('Grouped by the need each name answers, not by its'
                           ' Python nature. A helper callable from a handler '
                           'has exactly one access point: this one.',
                           'Groupé par le besoin auquel chaque nom répond, '
                           'pas par sa nature Python. Un helper appelable '
                           "depuis un handler a exactement un point d'accès :"
                           ' celui-ci.'),
                        color="muted", size="sm",
                    )
                    toplevel_surface_mirror()

            section(
                tr('State — server (4 scopes)',
                   'État — serveur (4 scopes)'),
                tr('from bretzel.state import PageState, SessionState, UserState, AppState\nfrom bretzel.state import field, validator, computed\n\nclass Cart(SessionState):          # page / session / user / app\n    items: list[dict] = field(default_factory=list)\n    coupon: str = ""\n\n    @validator("coupon")           # receives (self, value), RETURNS the value\n    def _norm(self, v: str) -> str:\n        return v.strip().upper()\n\n    @computed                       # derived, auto-tracked\n    def total(self) -> float:\n        return sum(i["price"] for i in self.items)\n',
                   'from bretzel.state import PageState, SessionState, UserState, AppState\nfrom bretzel.state import field, validator, computed\n\nclass Cart(SessionState):          # page / session / user / app\n    items: list[dict] = field(default_factory=list)\n    coupon: str = ""\n\n    @validator("coupon")           # reçoit (self, value), RETOURNE la valeur\n    def _norm(self, v: str) -> str:\n        return v.strip().upper()\n\n    @computed                       # dérivé, auto-tracké\n    def total(self) -> float:\n        return sum(i["price"] for i in self.items)\n'),
            )

            section(
                tr('State — client (3 persistence modes)',
                   'État — client (3 modes de persistance)'),
                tr('from bretzel.state import ClientState\n\nclass FilterUI(ClientState, persist="local"):\n    #  "memory"  → throwaway (lost on reload)\n    #  "session" → survives a reload, not a close\n    #  "local"   → survives everything\n    sort_by: str = "date"\n',
                   'from bretzel.state import ClientState\n\nclass FilterUI(ClientState, persist="local"):\n    #  "memory"  → jetable (perdu au reload)\n    #  "session" → survit au reload, pas à la fermeture\n    #  "local"   → survit à tout\n    sort_by: str = "date"\n'),
            )

            section(
                "Actions — serveur vs client",
                tr('# Server: on_click = callable → hx-post, HMAC signed\ndef save() -> None:\n    Cart().coupon = ""          # mutation → automatic re-render\nui.button("Save", on_click=save)\n\n# Client: on_click = an expression (string) → no round trip\nui.button("Top", on_click="window.scrollTo(0, 0)")\n\n# Imperative: the method RETURNS the client string\nwith ui.dialog() as d:\n    ui.text("Are you sure?")\nui.button("Open", on_click=d.open())\n\n# Binding: driving a ClientState\npanel = PanelUI()\nui.button("Toggle", on_click=panel.open.toggle())\n',
                   '# Serveur : on_click = callable → hx-post, HMAC signé\ndef save() -> None:\n    Cart().coupon = ""          # mutation → re-render auto\nui.button("Save", on_click=save)\n\n# Client : on_click = expression (string) → aucun aller-retour\nui.button("Haut", on_click="window.scrollTo(0, 0)")\n\n# Impératif : la méthode RETOURNE la string cliente\nwith ui.dialog() as d:\n    ui.text("Sûr ?")\nui.button("Ouvrir", on_click=d.open())\n\n# Binding : piloter un ClientState\npanel = PanelUI()\nui.button("Toggle", on_click=panel.open.toggle())\n'),
            )

            section(
                tr('Reactivity — mutate → re-render',
                   'Réactivité — muter → re-render'),
                tr('from bretzel import refreshable, ui\n\n@refreshable(deps=[Cart])          # declarative: re-render when Cart changes\ndef cart_view() -> None:\n    for it in ui.each(Cart().items, key="id"):\n        ui.text(it["label"])\n\nfrom bretzel import refresh\nrefresh(cart_view)                 # imperative, from a handler\n# refresh on a broadcast=[…] zone → SSE fan-out to the other tabs\n',
                   'from bretzel import refreshable, ui\n\n@refreshable(deps=[Cart])          # déclaratif : re-render quand Cart change\ndef cart_view() -> None:\n    for it in ui.each(Cart().items, key="id"):\n        ui.text(it["label"])\n\nfrom bretzel import refresh\nrefresh(cart_view)                 # impératif, depuis un handler\n# refresh sur une zone broadcast=[…] → fan-out SSE aux autres onglets\n'),
            )

            with ui.card(color="surface"):
                with ui.vstack(gap="sm"):
                    ui.heading(tr('⚠️ Trap no. 1',
                                  '⚠️ Le piège n°1'), level=2)
                    ui.text(
                        tr('Every file declaring a State MUST start with '
                           '`from __future__ import annotations` (PEP 649) — '
                           'otherwise the fields do not register, silently.',
                           'Tout fichier qui déclare un State DOIT commencer '
                           'par `from __future__ import annotations` (PEP '
                           "649) — sinon les champs ne s'enregistrent pas, "
                           'silencieusement.'),
                        color="muted", size="sm",
                    )
                    ui.code(
                        "from __future__ import annotations   # ← EN PREMIER, toujours\n",
                        lang="python",
                    )
                    with ui.hstack(align="baseline", gap="sm", wrap=True):
                        ui.text(tr('The other traps:',
                                   'Les autres pièges :'), color="muted", size="sm")
                        ui.link(tr('Traps →',
                                   'Pièges →'), href="/traps")
