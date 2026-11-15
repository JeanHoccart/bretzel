"""REFERENCE — Config & run.

How the application is configured and how it is launched. The parameter
tables for ``Bretzel()`` and ``run()`` are read live from the code
through ``callable_signature`` — they cannot diverge from the real API.
"""

from bretzel import Bretzel, page, ui

from examples.docs.features.shell import shell
from examples.docs.lib.blocks import callable_signature

PATH = "/config"


@page(PATH, layout=shell, title="Config & run · Bretzel docs",
      description="Configure and run a Bretzel app: the Bretzel(...) options, dev and prod modes, hot reload and run(), read from the code.")
def config_page() -> None:
    with ui.container(width="xl"):
        with ui.vstack(gap="lg"):
            ui.heading("Config & run", level=1, size="3xl")
            ui.text(
                'The `Bretzel(...)` instance carries the configuration; '
                '`run(...)` starts the dev server. The tables below are '
                'read from the code at render time — they follow the API '
                'with no editing.',
                color="muted", size="lg",
            )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("The instance", level=2)
                    ui.code(
                        'from bretzel import Bretzel\n\napp = Bretzel(\n    title="My App",\n    secret_key="…",   # required, ≥ 16 chars\n)\n# The mode is chosen by the command, not written here:\n#   bretzel dev main:app   -> dev\n#   uvicorn main:app       -> prod (the default)\n',
                        lang="python",
                    )
                    callable_signature(Bretzel.__init__, title="Bretzel(...)")

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Running", level=2)
                    ui.text(
                        '`mode` (dev/prod) and `reload` (hot reload) are '
                        'independent: `mode` picks a profile, `reload` '
                        'restarts the server when a file changes.',
                        color="muted", size="sm",
                    )
                    callable_signature(Bretzel.run, title="app.run(...)")

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading('What `mode` decides — and does not decide',
                               level=2)
                    ui.text(
                        '`mode` is a PRESET: it sets the defaults of '
                        'independent settings, which you can override one '
                        'by one.',
                        color="muted", size="sm",
                    )
                    ui.table(
                        columns=[
                            ui.column("reglage", label='Setting'),
                            ui.column("question", label='The question asked'),
                            ui.column("dev", label="dev"),
                            ui.column("prod", label="prod"),
                        ],
                        rows=[
                            {"reglage": "expose_errors=",
                             "question": 'does the detail of exceptions go'
                                         ' into the response?',
                             "dev": "True", "prod": "False"},
                            {"reglage": "debug=",
                             "question": 'should the framework be '
                                         'talkative (warnings, readable '
                                         'IDs)?',
                             "dev": "True", "prod": "False"},
                            {"reglage": "css=",
                             "question": 'who compiles the CSS?',
                             "dev": "browser", "prod": "build"},
                        {"reglage": "—",
                             "question": 'cache headers',
                             "dev": "no-store", "prod": "immutable"},
                        ],
                        size="sm",
                    )
                    ui.text(
                        'The two set themselves independently: '
                        '`mode="prod", debug=True` gives a talkative '
                        'production that exposes nothing, and `mode="dev",'
                        ' expose_errors=False` lets you see your real '
                        'error pages locally.',
                        color="muted", size="sm",
                    )

                    ui.heading('The CSS pipeline', level=3)
                    ui.text(
                        '`css="build"` compiles a sheet at startup and '
                        'serves it as a `<link>`: the CSS is there at the '
                        'first paint. `css="browser"` lets the Tailwind '
                        'compiler work inside the page — no binary to '
                        'install, but the CSS arrives after the first '
                        'paint. `"auto"` (the default) picks `build` in '
                        'production and `browser` in dev.',
                        color="muted", size="sm",
                    )
                    ui.text(
                        "To develop in production's exact conditions, ask "
                        'for `css="build"` — it needs the compiler (`pip '
                        "install 'bretzel[css]'`) and it adds a few "
                        'seconds to every startup. With no binary, the '
                        'application says so and falls back to the browser'
                        ' compiler.',
                        color="muted", size="sm",
                    )
                    ui.code(
                        "app = Bretzel(secret_key=\"…\", mode=\"dev\", "
                        "css=\"build\")\n",
                        lang="python",
                    )

                    ui.heading("Cookies and HTTPS", level=3)
                    ui.text(
                        "The cookies' `Secure` attribute does NOT depend "
                        "on the mode: it follows the request's protocol. A"
                        ' `Secure` cookie is never sent back over an '
                        '`http://` origin, so tying it to the mode would '
                        'cut the session of every application deployed '
                        'without TLS.',
                        color="muted", size="sm",
                    )
                    ui.code(
                        '# Behind a proxy that terminates TLS: tell uvicorn,\n# and it rewrites the protocol the app sees.\napp.run(proxy_headers=True)\n\n# Or force it, if the proxy sends no header.\napp = Bretzel(secret_key="…", secure_cookies=True)\n',
                        lang="python",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading('The security headers', level=2)
                    ui.text(
                        'Three headers are set BY DEFAULT, because they '
                        'can break no app: `nosniff`, `Referrer-Policy`, '
                        '`X-Frame-Options`. `security_headers=False` '
                        'exists for the app that sets them itself '
                        'upstream, behind its proxy.',
                        color="muted", size="sm",
                    )
                    ui.divider()
                    ui.text(
                        'The CSP, for its part, is OPT-IN — and it is a '
                        'split, not an oversight: Bretzel cannot guess '
                        "your app's fonts, CDNs and iframes. It computes "
                        'what it owes itself (the hashes of its inline '
                        'scripts, the origins of its assets); you add your'
                        ' own. One widens, one never narrows.',
                        color="muted", size="sm",
                    )
                    ui.code(
                        '# 1. The first rung: the browser EVALUATES the policy\n#    and reports what would have been blocked, without\n#    blocking anything.\napp = Bretzel(secret_key="…", csp="report-only")\n\n# 2. One looks at what comes back, fills the gaps, then\n#    closes it.\napp = Bretzel(secret_key="…", csp=True, csp_sources={\n    "font-src": ["https://fonts.gstatic.com"],\n    "frame-src": ["https://www.youtube.com"],\n})\n',
                        lang="python",
                    )
                    ui.text(
                        'The mode and the sources are two separate axes on'
                        ' purpose: a dict meaning “enable AND extend” '
                        'would make two ways of writing the same thing. '
                        'And `report-only` exists precisely so one does '
                        'not discover in production that an origin was '
                        'missing.',
                        color="muted", size="sm",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading('State persistence', level=2)
                    ui.text(
                        'By default, server state lives in memory and a '
                        'restart forgets it. `state_url=` says where it '
                        'lives instead: `"sqlite:///state.db"` keeps it in '
                        'a file across restarts; a `redis://` URL also '
                        'shares it between workers.',
                        color="muted", size="sm",
                    )
                    ui.table(
                        columns=[
                            ui.column("param", label="Param"),
                            ui.column("effet", label="Effect"),
                        ],
                        rows=[
                            {"param": "secret_key=",
                             "effet": 'the HMAC key (action signatures) — '
                                      'required, ≥ 16 chars; in production'
                                      ' through an env var'},
                            {"param": "state_url=",
                             "effet": 'sqlite:///file.db or redis://…; '
                                      'memory otherwise'},
                            {"param": "session_max_age_days=",
                             "effet": 'session cookie lifetime (default 30)'},
                            {"param": "workers=",
                             "effet": "uvicorn processes (a redis:// state_url if > 1)"},
                        ],
                        size="sm",
                    )
