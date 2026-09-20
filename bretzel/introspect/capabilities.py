"""What Bretzel can DO — the list no tree can give.

Why it exists, and why it is written by hand
--------------------------------------------
``describe_package`` walks the folder tree and returns 117 lines saying
**where the files are**. That is exact, and it does not answer the
question one really asks: *what can this framework do?*

No tree can answer it, and that is not a drafting flaw: **a capability
does not fit in a folder.** Serving a file is
``render/decorators/download.py`` + ``server/routing/downloads.py`` +
``server/routing/_csv.py`` + the ``download=`` of ``components/actions/
link`` + the export of ``components/data/datatable``. Five folders, five
docstrings, and not one saying "Bretzel can serve a file".

Hence a cross-cutting list, written by a human. It is exactly the form
that got the ``bretzel-api`` skill deleted on 2026-08-01 — a hand-copied
catalogue naming two non-existent components.

What makes this one different
-----------------------------
**It is ANCHORED.** Every capability names the symbols one enters
through, as dotted paths, and ``test_a_capability_is_anchored``:

1. resolves them for real (import + ``getattr``) — a removed or renamed
   symbol makes the line citing it turn red;
2. checks that the snippet parses AND that it uses those symbols — so a
   capability cannot describe anything other than what it names;
3. refuses the same entry symbol being claimed by two capabilities —
   that is the duplicate detector.

⚠️ **What the gate does NOT hold: that the sentence is true.** A
``does:`` promising more than the code does passes green. No mechanism
can judge that — that is review. It is why every line carries a
``caveat:``: the limit is as useful as the promise, and it is what says
the PWA has no service worker yet.

The rule: an index LISTS, a chapter TEACHES
-------------------------------------------
This list is an INDEX. It serves to know that a thing exists and where
one enters it — not to learn it. What explains *why* and *how* lives in a
chapter of ``examples/docs``, written by hand, and **in one place only**.

The rule was set on 2026-09-03 because there were four surfaces
answering "what can Bretzel do" — this list, the package tree, the
``ui.*`` catalogue, the cheat sheet — and no rule saying which one was
authoritative. Measured: the chapters do NOT duplicate each other (only
three pairs share four symbols, and those are ``Bretzel``, ``page``,
``ui.button``, which every snippet needs). The disorder was therefore not
repetition, it was the absence of a rule about *where one writes* when
one adds something.

Hence:

- an **index** is generated from a single source, carries no prose of its
  own, and POINTS AT the chapter;
- a **chapter** is written, teaches a mechanism, and is the only place
  where one explains;
- every capability declares its chapter in :attr:`Capability.chapter`,
  and a capability without a chapter is a VISIBLE debt — displayed on the
  page, held by a ratchet that does not go back up.

What it does NOT claim to be
----------------------------
Documentation. A capability fits in one sentence and a minimal snippet;
the detail lives in the symbol's docstring, which ``describe`` already
returns. The list serves to KNOW THAT IT EXISTS — that is the only hole
neither the tree, nor the ``ui.*`` catalogue, nor the per-need table
fills.
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Capability:
    """One thing Bretzel makes possible, and where one enters it."""

    #: The title, as an action: one names an ACTION, not a component.
    #: "Serve a file", not "The download decorator".
    name: str
    #: What it makes possible, in one sentence, from the point of view of
    #: whoever writes it. Not what it is — what it saves one from doing.
    does: str
    #: The symbols one enters through, as dotted paths. Resolved by the
    #: gate: that is what keeps this list from drifting.
    entry: tuple[str, ...]
    #: The smallest code that puts it to work. Must parse, and must use
    #: the names in ``entry`` — the gate checks it.
    snippet: str
    #: What to know before using it: the limit, the trap, or the
    #: fallback. Empty when there is none.
    caveat: str = field(default="")

    #: The route of the chapter that TEACHES it, in ``examples/docs``.
    #:
    #: **It is the "an index lists, a chapter teaches" rule.** A
    #: capability fits in one sentence and a snippet; what explains why
    #: and how lives in a hand-written chapter, in one place only.
    #: Without this field, there were four surfaces answering "what can
    #: it do" and no rule saying which one was authoritative.
    #:
    #: Empty = **no chapter yet**, and that is a VISIBLE debt: the page
    #: displays it in clear, and ``test_a_capability_is_anchored`` holds
    #: a ratchet that does not go back up. Measured when it was set: 8
    #: out of 19.
    chapter: str = field(default="")


def _code(text: str) -> str:
    """A dedented snippet — written readably in the source."""
    return textwrap.dedent(text).strip("\n")


#: ⚠️ **The list is not exhaustive.** Nineteen capabilities on
#: 2026-09-03; what is still missing is tracked in
#: ``.claude/work/todo.md``. Do not read the absence of a line as
#: "Bretzel cannot do it".
CAPABILITIES: tuple[Capability, ...] = (
    # ── Leaving the app: files, device, installation, identity ───────
    Capability(
        name="Serve a file",
        chapter="/browser",
        does=(
            "Return a route that DOWNLOADS instead of navigating. A list "
            "of dicts becomes a CSV with its header, its escaping and "
            "its BOM for Excel; one touches neither the HTTP headers nor "
            "the `Content-Disposition`."
        ),
        entry=("bretzel.download", "bretzel.ui.link"),
        snippet=_code(
            """
            @download("/customers.csv")
            async def customers_csv() -> list[dict]:
                return [{"name": "Ada Lovelace", "city": "London"}]

            # The link must say it carries a FILE, otherwise the shell
            # swallows it: `hx-boost` intercepts every <a> and swaps the
            # CSV into the page.
            ui.link("Export", href="/customers.csv", download=True)
            """
        ),
        caveat=(
            "Without `download=True`, the link is intercepted by "
            "`hx-boost` and the file arrives as HTML in the outlet — "
            "with no sign at all on the server side."
        ),
    ),
    Capability(
        name="Act in the browser without writing JS",
        chapter="/browser",
        does=(
            "Copy to the clipboard, open the share sheet, vibrate the "
            "device, print, go full screen — each in one `on_click=`, "
            "with no server round trip and not a line of JavaScript."
        ),
        entry=(
            "bretzel.copy",
            "bretzel.share",
            "bretzel.vibrate",
            "bretzel.print_page",
            "bretzel.fullscreen",
        ),
        snippet=_code(
            """
            ui.button("Copy the key", on_click=copy(state.api_key))
            ui.button("Share", on_click=share())
            ui.button("Vibrate", on_click=vibrate([50, 30, 50]))
            ui.button("Print", on_click=print_page())
            ui.button("Full screen", on_click=fullscreen())
            """
        ),
        caveat=(
            "`share` does not exist on a desktop browser: it falls back "
            "on copying the URL. `vibrate` does nothing on a device with "
            "no motor. Both are silent by design — a missing verb must "
            "not break the page."
        ),
    ),
    Capability(
        name="Install as an application",
        chapter="/browser",
        does=(
            "Serve a web manifest so the app can be added to the home "
            "screen and open with no address bar. One line in "
            "`Bretzel(...)`; the manifest, its route and its tags are "
            "generated."
        ),
        entry=("bretzel.PWA", "bretzel.PWAIcon"),
        snippet=_code(
            """
            app = Bretzel(
                title="Tracker",
                pwa=PWA(name="Tracker", icon="/static/logo.png",
                        theme_color="#0f172a"),
            )
            """
        ),
        caveat=(
            "The manifest is not enough for offline mode: there is no "
            "service worker yet, so the installed app still requires the "
            "network."
        ),
    ),
    Capability(
        name="Sign in with a Google, Microsoft or GitHub account",
        chapter="/auth",
        does=(
            "Mount an OAuth2/OIDC door — its route, its token exchange, "
            "its signed cookie and its anti-fixation rotation. What is "
            "left to write is the only decision that is yours: accept "
            "this profile, or not."
        ),
        entry=("bretzel.server.oauth.OIDC", "bretzel.auth"),
        snippet=_code(
            """
            @auth.door(OIDC(
                name="google", issuer="https://accounts.google.com",
                client_id=CLIENT_ID, client_secret=CLIENT_SECRET,
            ))
            def on_oauth_user(profile) -> str | None:
                \"\"\"Returning None REFUSES entry.\"\"\"
                if not profile.email.endswith("@mycompany.com"):
                    return None
                return profile.email
            """
        ),
        caveat=(
            "Bretzel owns the identity and its transport; the app owns "
            "the proof. There is no sign-in page supplied, no passwords, "
            "no roles — and Apple is not handled (its `client_secret` is "
            "an ES256 JWT, hence a dependency)."
        ),
    ),
    # ── The core: typed state, reactivity, client computation ────────
    Capability(
        name="Keep the app's state in typed classes",
        chapter="/state-server",
        does=(
            "Declare where a piece of data lives — the page, the "
            "session, the user, the whole app, or the browser — by "
            "choosing the class one inherits from. No strings to address "
            "state, so autocompletion and the type checker work."
        ),
        entry=(
            "bretzel.state.PageState",
            "bretzel.state.SessionState",
            "bretzel.state.UserState",
            "bretzel.state.AppState",
            "bretzel.state.ClientState",
        ),
        snippet=_code(
            """
            class Filter(PageState):        # dies with the page
                search: str = field(default="")

            class Cart(SessionState):       # follows the tab
                lines: list[str] = field(default_factory=list)

            class Profile(UserState):       # follows the signed-in person
                first_name: str = field(default="")

            class Settings(AppState):       # shared by everybody
                maintenance: bool = field(default=False)

            class Open(ClientState):        # NEVER leaves the browser
                panel: bool = field(default=False)
            """
        ),
        caveat=(
            "`UserState` only exists when an identity is resolved: with "
            "no auth, an app reading it gets a 401. `ClientState` does "
            "not travel as JSON — htmx sends it field by field, which "
            "surprises on lists."
        ),
    ),
    Capability(
        name="Refresh part of a page on a state mutation",
        chapter="/reactivity-server",
        does=(
            "Mark a region as depending on a typed state: any mutation "
            "of that state re-renders it, alone, without the rest of the "
            "page moving and without writing a single network call. With "
            "`broadcast=`, the same region re-renders on ALL open pages, "
            "over SSE."
        ),
        entry=("bretzel.refreshable",),
        snippet=_code(
            """
            class Cart(SessionState):
                lines: list[str] = field(default_factory=list)

            @refreshable(deps=[Cart])
            def summary() -> None:
                ui.text(f"{len(Cart().lines)} item(s)")

            # Elsewhere, in a handler: the region re-renders by itself.
            Cart().lines.append("coffee")
            """
        ),
        caveat=(
            "The region is TRANSPARENT to layout but is not an instance "
            "of what it carries — a container inspecting its children "
            "must unwrap it. And `broadcast=` is not a separate "
            "capability: it is a mode of that same decorator."
        ),
    ),
    Capability(
        name="Compute on the client without writing JS",
        chapter="/reactivity-client",
        does=(
            "Write a Python expression over client state — comparison, "
            "arithmetic, negation, concatenation — and let it evaluate "
            "IN the browser. No round trip, and the JS emitted is never "
            "typed by hand."
        ),
        entry=("bretzel.state.ClientBinding",),
        snippet=_code(
            """
            class Form(ClientState):
                name: str = field(default="")
                age: int = field(default=0)

            f = Form()
            # ⚠️ One never WRITES the type's name: it is the operator on
            # a client-state field that builds it.
            empty: ClientBinding = f.name == ""

            # Each of these three lines produces JS, not a POST:
            ui.button("Submit", disabled=empty)
            ui.text("Adult", visible=f.age >= 18)
            ui.text(f.name + " — " + f.name)
            """
        ),
        caveat=(
            "One never writes `ClientBinding`: it is the TYPE an "
            "operator on a client-state field produces. The anchoring "
            "gate in fact refused this snippet's first version, which "
            "named it nowhere.\n"
            "  The algebra is finite: `bretzel describe ClientBinding` "
            "lists the operations with the JS each one emits. An "
            "expression outside the algebra (a Python function call) "
            "evaluates at RENDER time and freezes."
        ),
    ),
    Capability(
        name="Make a page live without anybody clicking",
        chapter="/cadence",
        does=(
            "A counter, a clock, a periodic poll: a client-side cadence "
            "that fires a handler, stoppable by a plain state boolean — "
            "with no server task and no lifecycle to manage."
        ),
        entry=("bretzel.ui.interval",),
        snippet=_code(
            """
            class Live(ClientState):
                active: bool = field(default=True)

            live = Live()
            ui.interval(on_tick=reload_rows, seconds=5, active=live.active)
            ui.switch("Follow live", value=live.active)
            """
        ),
        caveat=(
            "This is PULL: the page asks. For PUSH — the server telling "
            "it — use `@refreshable(broadcast=[…])`, which goes over SSE "
            "and wakes only the pages concerned."
        ),
    ),
    # ── Lists: iterate, tabulate, move ───────────────────────────────
    Capability(
        name="Render a moving list without re-rendering all of it",
        chapter="/lists",
        does=(
            "Iterate with a stable key per item, filter client-side on "
            "an expression, paginate — all of it while keeping each "
            "row's client state (a ticked box stays ticked when the list "
            "reorders)."
        ),
        entry=(
            "bretzel.ui.each",
            "bretzel.ui.filter_each",
            "bretzel.ui.paginate_each",
        ),
        snippet=_code(
            """
            for task in each(Tasks().items, key=lambda t: t.id):
                ui.checkbox(task.title)

            # Filter without going back to the server:
            with filter_each(Tasks().items, where=lambda t: t.open):
                ui.text("…")

            with paginate_each(Tasks().items, per_page=20):
                ui.text("…")
            """
        ),
        caveat=(
            "A bare `for` works as long as the body produces no client "
            "state: without a stable key, idiomorph re-pairs the nodes "
            "by position and the state jumps from one row to another."
        ),
    ),
    Capability(
        name="Show a table that sorts, filters, paginates and exports",
        chapter="/lists",
        does=(
            "A component that takes a typed query state and some "
            "columns, and renders the search box, the clickable headers, "
            "the pagination and the CSV export button. Sorting and "
            "pagination are done on the SERVER: the table works on a "
            "million rows."
        ),
        entry=("bretzel.ui.datatable", "bretzel.ui.column"),
        snippet=_code(
            """
            class Query(DatatableState):
                pass

            COLUMNS = [
                column("title", "Title", sortable=True),
                column("status", "Status", align="center"),
            ]

            def load(q):
                \"\"\"Returns (rows_of_this_page, total).\"\"\"
                return page_of(q), total_of(q)

            datatable(state=Query, columns=COLUMNS, rows=load,
                      exportable=True, export_filename="issues.csv")
            """
        ),
        caveat=(
            "`rows=` accepts a list (everything in memory) or a callable "
            "receiving the query — only the second form avoids loading "
            "the whole table."
        ),
    ),
    Capability(
        name="Move items with the mouse or a finger",
        chapter="/drag",
        does=(
            "Reorder a list, drag a card from one column to another: one "
            "declares the zone that accepts and the item that is "
            "grabbed, and the handler receives what came from where and "
            "where it goes."
        ),
        entry=("bretzel.ui.draggable", "bretzel.ui.dropzone"),
        snippet=_code(
            """
            with dropzone(name="todo", accepts=["task"], on_move=move_task):
                for t in Tasks().todo:
                    with draggable(key=t.id, group="task"):
                        ui.card(t.title)
            """
        ),
        caveat=(
            "`accepts=` and `group=` are what keep a card from falling "
            "into a zone that does not understand it — without them, "
            "every zone accepts everything."
        ),
    ),
    # ── Surfaces and layout ──────────────────────────────────────────
    Capability(
        name="Open and close a surface from the code",
        chapter="/actions-client",
        does=(
            "Dialogs, drawers, popovers and menus open through a call — "
            "`.open()` / `.close()` — instead of a state boolean to "
            "wire. It is the default for everything purely visual: "
            "nothing to declare, nothing to synchronise."
        ),
        entry=(
            "bretzel.ui.dialog",
            "bretzel.ui.drawer",
            "bretzel.ui.popover",
            "bretzel.ui.dropdown",
        ),
        snippet=_code(
            """
            with dialog(title="Confirm") as confirmation:
                ui.text("Delete permanently?")

            ui.button("Delete", on_click=confirmation.open())

            with drawer(side="right") as panel:
                ui.text("Filters")
            with popover() as details:
                ui.text("Detail")
            with dropdown() as menu:
                ui.menu_item("Rename")
            """
        ),
        caveat=(
            "The imperative form is the default for VISUAL surfaces. A "
            "component carrying a VALUE (a field, a choice) stays bound "
            "through `ClientBinding` — the state is then the truth, not "
            "the call."
        ),
    ),
    Capability(
        name="Freeze the document and scroll the regions",
        chapter="/scrolling",
        does=(
            "The tool model: the frame does not move, only the columns "
            "scroll — a fixed sidebar, a fixed header, content that "
            "scrolls on its own. The alternative stays the default: a "
            "document that scrolls as a whole."
        ),
        entry=("bretzel.ui.viewport", "bretzel.ui.pane"),
        snippet=_code(
            """
            with viewport(direction="row"):
                with pane(padding="md"):
                    ui.text("The left column scrolls on its own.")
                with pane(padding="md"):
                    ui.text("So does the right one, independently.")
            """
        ),
        caveat=(
            "Both models coexist in the repository (8 apps against 10) "
            "and that is intended. Mixing the two on one page gives two "
            "nested scrollbars."
        ),
    ),
    Capability(
        name="Draw charts without a JS library",
        chapter="/charts",
        does=(
            "Lines, bars, pies, scatter plots and sparklines, rendered as "
            "SVG on the server — so visible before a single script runs, "
            "and printable."
        ),
        entry=(
            "bretzel.ui.line_chart",
            "bretzel.ui.bar_chart",
            "bretzel.ui.pie_chart",
            "bretzel.ui.scatter_chart",
            "bretzel.ui.sparkline",
        ),
        snippet=_code(
            """
            line_chart(series=[sales], x_labels=MONTHS, height=240)
            bar_chart(series=[by_region])
            pie_chart(values=[40, 35, 25], labels=["A", "B", "C"])
            scatter_chart(series=[cloud])
            sparkline(values=[3, 5, 4, 8, 6])
            """
        ),
        caveat=(
            "This is static SVG enriched on the client: no zoom, no "
            "panning, no millions of points. For interactive "
            "exploration, a dedicated library remains the right tool."
        ),
    ),
    # ── Visual identity and structure ────────────────────────────────
    Capability(
        name="Change the whole visual identity from a palette",
        chapter="/theme",
        does=(
            "One semantic colour is enough: light, dark, hover states "
            "and contrasts are derived from it, and every component "
            "follows. Tailwind v4 is compiled by a Rust binary — no "
            "Node.js in production."
        ),
        entry=("bretzel.theme.Theme", "bretzel.theme.Palette"),
        snippet=_code(
            """
            THEME = Theme(semantic={"primary": "#0f766e"})

            # Override ONE component, without touching the others:
            THEME = Theme(
                semantic={"primary": "#0f766e"},
                components={"card": {"slots": {"root": "rounded-none"}}},
            )
            palette = Palette  # what the theme resolves, light AND dark
            """
        ),
        caveat=(
            "A Tailwind class ASSEMBLED in an f-string is invisible to "
            "the production compiler: the HTML is identical on both "
            "sides, so the breakage only shows IN production. Whole "
            "class in the theme, or safelist."
        ),
    ),
    Capability(
        name="Split an app into declared features",
        chapter="/structure",
        does=(
            "Each feature declares its name, its nature and what it "
            "provides; the graph is checked at startup — an unknown "
            "dependency, a cycle, a name collision are errors, not "
            "runtime surprises."
        ),
        entry=("bretzel.Feature",),
        snippet=_code(
            """
            feature = Feature(
                name="access",
                kind="logic",
                provides=[current_user, sign_out],
            )
            """
        ),
        caveat=(
            "The discovery mechanics (manifest, `include` versus "
            "sweeping) are deliberately DEFERRED: `app.include(module)` "
            "remains the way to mount a feature."
        ),
    ),
    Capability(
        name="Speak the visitor's language",
        chapter="/languages",
        does=(
            "The words the framework renders itself — \"Search…\", "
            "\"Dismiss alert\", the pagination labels — are translated "
            "per request, negotiated from the browser's header and "
            "overridable by a cookie."
        ),
        entry=("bretzel.render.Language", "bretzel.render.text"),
        snippet=_code(
            """
            app = Bretzel(
                lang="fr", languages=["fr", "en"],
                texts={"fr": {"alert.dismiss": "Fermer"}},
            )

            # In a page, read the language resolved for THIS request:
            ui.text(f"language = {Language().code}")
            # And reuse the framework's vocabulary:
            ui.text(text("alert.dismiss"))
            """
        ),
        caveat=(
            "This covers THE FRAMEWORK's vocabulary. The app's own "
            "sentences stay its responsibility — there is no application "
            "internationalisation system (planned for 2.1)."
        ),
    ),
    # ── The framework looking at itself ──────────────────────────────
    Capability(
        name="Ask the framework what it exposes",
        chapter="/tree",
        does=(
            "Query the INSTALLED code: a component's card with its "
            "parameters, its slots and its events; the package tree; a "
            "module's surface classified by need. Nothing is copied, so "
            "nothing can drift."
        ),
        entry=("bretzel.introspect.describe", "bretzel.introspect.index"),
        snippet=_code(
            """
            # On the command line:
            #   py -m bretzel.cli.main describe hstack
            #   py -m bretzel.cli.main describe capabilities
            print(describe("hstack"))
            print(index())          # the whole ui.* surface, one line per symbol
            """
        ),
        caveat=(
            "The output is UTF-8, arrows and quotation marks included: "
            "on a Windows console in cp1252, a bare `print` raises. The "
            "CLI takes care of it, a home-made script must too."
        ),
    ),
    Capability(
        name="Have the framework judge your own code",
        chapter="/structure",
        does=(
            "Ten rules that catch what no test sees: the dead kwarg (it "
            "does not raise, does not show, is not visible in review), "
            "sibling fields at different sizes, a cast that erases a "
            "value's provenance and breaks resynchronisation."
        ),
        entry=("bretzel.lint.run", "bretzel.lint.available_rules"),
        snippet=_code(
            """
            # On the command line:
            #   py -m bretzel.cli.main check examples
            report = run(["examples"])
            print(report.exit_code, len(report.findings))

            # What the tool can verify, enumerable by design:
            for rule in available_rules():
                print(rule)
            """
        ),
        caveat=(
            "These are RULES, not a reflection of the code — it is the "
            "detachable half of the framework, and the "
            "`lint-stays-extractable` contract in `.importlinter` keeps "
            "it detachable."
        ),
    ),
    Capability(
        name="Validate a piece of data where it lives",
        chapter="/forms",
        does=(
            "Attach a rule to a typed state FIELD rather than to a form. "
            "It runs on every assignment — so from the form as well as "
            "from an import or a handler called elsewhere."
        ),
        entry=("bretzel.state.validator", "bretzel.ui.form",
               "bretzel.ui.form_field"),
        snippet=(
            "class SignUp(SessionState):\n"
            '    email: str = field(default="")\n'
            "\n"
            '    @validator("email")\n'
            "    def _check(self, value: str) -> str:\n"
            "        value = value.strip().lower()\n"
            '        if "@" not in value:\n'
            '            raise ValueError("Invalid address.")\n'
            "        return value           # it also NORMALISES\n"
            "\n"
            "with ui.form(on_submit=save):\n"
            '    with ui.form_field(label="Email", error=error):\n'
            '        ui.input(name="email")\n'
        ),
        caveat=(
            "A rule set on the VIEW only covers the path that goes "
            "through the view. An app has several write paths and one "
            "form — that is why the validator lives on the field, not on "
            "the `ui.form`."
        ),
    ),
    Capability(
        name="Keep state across a restart",
        chapter="/config",
        does=(
            "Plug in a shared store — Redis — so that the session and "
            "user scopes survive the process restarting and are shared "
            "between several instances. One URL, and nothing else to "
            "change in the code."
        ),
        entry=("bretzel.BretzelConfig",),
        snippet=(
            "# Without Redis, state lives in memory and dies with the\n"
            "# process. Perfect in dev, wrong as soon as there are two\n"
            "# instances behind a load balancer.\n"
            "app = Bretzel(\n"
            '    secret_key="…",\n'
            '    redis_url="redis://localhost:6379/0",\n'
            "    session_max_age_days=30,\n"
            ")\n"
            "\n"
            "# `BretzelConfig` carries the settings' complete contract.\n"
            "print(BretzelConfig.__doc__)\n"
        ),
        caveat=(
            "It is not a database: screen state is not your business "
            "data. A cart one must find again in six months goes in a "
            "database, not in a `SessionState`."
        ),
    ),
    Capability(
        name="Refuse a double click and a replay",
        chapter="/actions-server",
        does=(
            "Mark an action so that a second submission of the same "
            "render does not run it twice. The signature already carries "
            "a signed timestamp — a late replay is refused by the base "
            "layer, with nothing to write."
        ),
        entry=("bretzel.idempotent",),
        snippet=(
            "from bretzel import idempotent\n"
            "\n"
            "@idempotent\n"
            "def pay() -> None:\n"
            '    """A double click does not charge twice."""\n'
            "    charge(Cart().total)\n"
        ),
        caveat=(
            "The anti-replay shipped is a SIGNED timestamp plus this "
            "decorator, not a table of single-use tokens: the signature "
            "is computed at RENDER time, so it cannot cover the "
            "request's body. Replaying escalates no privilege — the "
            "double click is the real subject."
        ),
    ),
    Capability(
        name="Develop with no build and no manual reload",
        chapter="/config",
        does=(
            "One word switches the whole toolchain: server reload on the "
            "slightest file touched, CSS compiled in the browser, full "
            "tracebacks. In production the CSS is compiled ahead of time "
            "by a binary, and there is no Node.js at all."
        ),
        entry=("bretzel.Bretzel",),
        snippet=(
            "app = Bretzel(\n"
            '    secret_key="…",\n'
            '    mode="dev",            # or "prod"\n'
            ")\n"
            "\n"
            'if __name__ == "__main__":\n'
            "    app.run(port=8000, reload=True)\n"
        ),
        caveat=(
            "Reloading launches uvicorn in a CHILD process. A parent "
            "killed without propagating leaves that child holding the "
            "port, and the next launch can no longer bind to it — "
            "measured, and the error does not always reach the screen."
        ),
    ),
)


def capability_names() -> tuple[str, ...]:
    """The titles, in list order."""
    return tuple(c.name for c in CAPABILITIES)


def render_capabilities() -> str:
    """The list as text — what ``bretzel describe capabilities`` returns."""
    lines = [f"## What Bretzel can do ({len(CAPABILITIES)})", ""]
    for cap in CAPABILITIES:
        lines.append(f"  {cap.name}")
        lines.append(f"    {cap.does}")
        lines.append(f"    Entry points: {', '.join(cap.entry)}")
        lines.append(
            f"    Chapter: {cap.chapter}" if cap.chapter
            else "    Chapter: (not written yet)"
        )
        for line in cap.snippet.splitlines():
            lines.append(f"      {line}")
        if cap.caveat:
            lines.append(f"    ⚠️ {cap.caveat}")
        lines.append("")
    return "\n".join(lines)


__all__ = ["CAPABILITIES", "Capability", "capability_names", "render_capabilities"]
