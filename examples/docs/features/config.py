"""REFERENCE — Config & run.

How the application is configured and how it is launched. The parameter
tables for ``Bretzel()`` and ``run()`` are read live from the code
through ``callable_signature`` — they cannot diverge from the real API.
"""

from bretzel import Bretzel, page, ui

from examples.docs.features.shell import shell
from examples.docs.lib.blocks import callable_signature
from examples.docs.lib.i18n import tr

PATH = "/config"


@page(PATH, layout=shell, title="Config & run")
def config_page() -> None:
    with ui.container(width="xl"):
        with ui.vstack(gap="lg"):
            ui.heading("Config & run", level=1, size="3xl")
            ui.text(
                tr('The `Bretzel(...)` instance carries the configuration; '
                   '`run(...)` starts the dev server. The tables below are '
                   'read from the code at render time — they follow the API '
                   'with no editing.',
                   "L'instance `Bretzel(...)` porte la configuration ; "
                   '`run(...)` lance le serveur de dev. Les tables ci-dessous'
                   " sont lues dans le code au render — elles suivent l'API "
                   'sans édition.'),
                color="muted", size="lg",
            )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("L'instance", level=2)
                    ui.code(
                        tr('from bretzel import Bretzel\n\napp = Bretzel(\n    title="My App",\n    secret_key="…",   # required, ≥ 16 chars\n    mode="dev",       # "dev" | "prod" (prod by default)\n)\n',
                           'from bretzel import Bretzel\n\napp = Bretzel(\n    title="My App",\n    secret_key="…",   # requis, ≥ 16 chars\n    mode="dev",       # "dev" | "prod" (défaut prod)\n)\n'),
                        lang="python",
                    )
                    callable_signature(Bretzel.__init__, title="Bretzel(...)")

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Lancer", level=2)
                    ui.text(
                        tr('`mode` (dev/prod) and `reload` (hot reload) are '
                           'independent: `mode` picks a profile, `reload` '
                           'restarts the server when a file changes.',
                           '`mode` (dev/prod) et `reload` (hot-reload) sont '
                           'indépendants : `mode` choisit un profil, `reload`'
                           ' relance le serveur au changement de fichier.'),
                        color="muted", size="sm",
                    )
                    callable_signature(Bretzel.run, title="app.run(...)")

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(tr('What `mode` decides — and does not decide',
                                  'Ce que `mode` décide — et ne décide pas'),
                               level=2)
                    ui.text(
                        tr('`mode` is a PRESET: it sets the defaults of '
                           'independent settings, which you can override one '
                           'by one.',
                           '`mode` est un PRÉRÉGLAGE : il pose les valeurs '
                           'par défaut de réglages indépendants, que tu peux '
                           'surcharger un par un.'),
                        color="muted", size="sm",
                    )
                    ui.table(
                        columns=[
                            ui.column("reglage", label=tr('Setting',
                                                          'Réglage')),
                            ui.column("question", label=tr('The question asked',
                                                           'Question posée')),
                            ui.column("dev", label="dev"),
                            ui.column("prod", label="prod"),
                        ],
                        rows=[
                            {"reglage": "expose_errors=",
                             "question": tr('does the detail of exceptions go'
                                            ' into the response?',
                                            'le détail des exceptions part-il'
                                            ' dans la réponse ?'),
                             "dev": "True", "prod": "False"},
                            {"reglage": "debug=",
                             "question": tr('should the framework be '
                                            'talkative (warnings, readable '
                                            'IDs)?',
                                            'le framework doit-il être bavard'
                                            ' (warnings, IDs lisibles) ?'),
                             "dev": "True", "prod": "False"},
                            {"reglage": "css=",
                             "question": tr('who compiles the CSS?',
                                            'qui compile le CSS ?'),
                             "dev": "browser", "prod": "build"},
                        {"reglage": "—",
                             "question": tr('cache headers',
                                            'en-têtes de cache'),
                             "dev": "no-store", "prod": "immutable"},
                        ],
                        size="sm",
                    )
                    ui.text(
                        tr('The two set themselves independently: '
                           '`mode="prod", debug=True` gives a talkative '
                           'production that exposes nothing, and `mode="dev",'
                           ' expose_errors=False` lets you see your real '
                           'error pages locally.',
                           'Les deux se règlent seuls : `mode="prod", '
                           "debug=True` donne une prod bavarde qui n'expose "
                           'rien, et `mode="dev", expose_errors=False` permet'
                           " de voir tes vraies pages d'erreur en local."),
                        color="muted", size="sm",
                    )

                    ui.heading(tr('The CSS pipeline',
                                  'Le pipeline CSS'), level=3)
                    ui.text(
                        tr('`css="build"` compiles a sheet at startup and '
                           'serves it as a `<link>`: the CSS is there at the '
                           'first paint. `css="browser"` lets the Tailwind '
                           'compiler work inside the page — no binary to '
                           'install, but the CSS arrives after the first '
                           'paint. `"auto"` (the default) picks `build` in '
                           'production and `browser` in dev.',
                           '`css="build"` compile une feuille au démarrage et'
                           ' la sert en `<link>` : le CSS est présent au '
                           'premier affichage. `css="browser"` laisse le '
                           'compilateur Tailwind travailler dans la page — '
                           'aucun binaire à installer, mais le CSS arrive '
                           'après le premier affichage. `"auto"` (défaut) '
                           'choisit `build` en prod et `browser` en dev.'),
                        color="muted", size="sm",
                    )
                    ui.text(
                        tr("To develop in production's exact conditions, ask "
                           'for `css="build"` — it needs the compiler (`pip '
                           "install 'bretzel[css]'`) and it adds a few "
                           'seconds to every startup. With no binary, the '
                           'application says so and falls back to the browser'
                           ' compiler.',
                           'Pour développer dans les conditions exactes de la'
                           ' prod, demande `css="build"` — il faut le '
                           "compilateur (`pip install 'bretzel[css]'`) et ça "
                           'ajoute quelques secondes à chaque démarrage. Sans'
                           " binaire, l'application le dit et repasse sur le "
                           'compilateur navigateur.'),
                        color="muted", size="sm",
                    )
                    ui.code(
                        "app = Bretzel(secret_key=\"…\", mode=\"dev\", "
                        "css=\"build\")\n",
                        lang="python",
                    )

                    ui.heading("Cookies et HTTPS", level=3)
                    ui.text(
                        tr("The cookies' `Secure` attribute does NOT depend "
                           "on the mode: it follows the request's protocol. A"
                           ' `Secure` cookie is never sent back over an '
                           '`http://` origin, so tying it to the mode would '
                           'cut the session of every application deployed '
                           'without TLS.',
                           "L'attribut `Secure` des cookies ne dépend PAS du "
                           'mode : il suit le protocole de la requête. Un '
                           "cookie `Secure` n'est jamais renvoyé sur une "
                           'origine `http://`, donc le lier au mode couperait'
                           ' la session de toute application déployée sans '
                           'TLS.'),
                        color="muted", size="sm",
                    )
                    ui.code(
                        tr('# Behind a proxy that terminates TLS: tell uvicorn,\n# and it rewrites the protocol the app sees.\napp.run(proxy_headers=True)\n\n# Or force it, if the proxy sends no header.\napp = Bretzel(secret_key="…", secure_cookies=True)\n',
                           '# Derrière un proxy qui termine le TLS : dis-le à\n# uvicorn, il réécrit le protocole vu par l\'app.\napp.run(proxy_headers=True)\n\n# Ou force-le, si le proxy n\'envoie pas d\'en-tête.\napp = Bretzel(secret_key="…", secure_cookies=True)\n'),
                        lang="python",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(tr('The security headers',
                                  'Les en-têtes de sécurité'), level=2)
                    ui.text(
                        tr('Three headers are set BY DEFAULT, because they '
                           'can break no app: `nosniff`, `Referrer-Policy`, '
                           '`X-Frame-Options`. `security_headers=False` '
                           'exists for the app that sets them itself '
                           'upstream, behind its proxy.',
                           'Trois en-têtes sont posés PAR DÉFAUT, parce '
                           "qu'ils ne peuvent casser aucune app : `nosniff`, "
                           '`Referrer-Policy`, `X-Frame-Options`. '
                           "`security_headers=False` existe pour l'app qui "
                           'les pose elle-même en amont, derrière son proxy.'),
                        color="muted", size="sm",
                    )
                    ui.divider()
                    ui.text(
                        tr('The CSP, for its part, is OPT-IN — and it is a '
                           'split, not an oversight: Bretzel cannot guess '
                           "your app's fonts, CDNs and iframes. It computes "
                           'what it owes itself (the hashes of its inline '
                           'scripts, the origins of its assets); you add your'
                           ' own. One widens, one never narrows.',
                           "La CSP, elle, est OPT-IN — et c'est un partage, "
                           'pas un oubli : Bretzel ne peut pas deviner les '
                           'polices, les CDN et les iframes de ton app. Il '
                           "calcule ce qu'il se doit à lui-même (les "
                           'empreintes de ses scripts inline, les origines de'
                           ' ses assets) ; tu ajoutes les tiennes. On '
                           'élargit, jamais on ne rétrécit.'),
                        color="muted", size="sm",
                    )
                    ui.code(
                        tr('# 1. The first rung: the browser EVALUATES the policy\n#    and reports what would have been blocked, without\n#    blocking anything.\napp = Bretzel(secret_key="…", csp="report-only")\n\n# 2. One looks at what comes back, fills the gaps, then\n#    closes it.\napp = Bretzel(secret_key="…", csp=True, csp_sources={\n    "font-src": ["https://fonts.gstatic.com"],\n    "frame-src": ["https://www.youtube.com"],\n})\n',
                           '# 1. Le premier barreau : le navigateur ÉVALUE la\n#    politique et signale ce qui aurait sauté, sans\n#    rien bloquer.\napp = Bretzel(secret_key="…", csp="report-only")\n\n# 2. On regarde ce qui remonte, on complète, puis on\n#    ferme.\napp = Bretzel(secret_key="…", csp=True, csp_sources={\n    "font-src": ["https://fonts.gstatic.com"],\n    "frame-src": ["https://www.youtube.com"],\n})\n'),
                        lang="python",
                    )
                    ui.text(
                        tr('The mode and the sources are two separate axes on'
                           ' purpose: a dict meaning “enable AND extend” '
                           'would make two ways of writing the same thing. '
                           'And `report-only` exists precisely so one does '
                           'not discover in production that an origin was '
                           'missing.',
                           'Le mode et les sources sont deux axes séparés à '
                           'dessein : un dict qui voudrait dire « active ET '
                           "étends » ferait deux façons d'écrire la même "
                           'chose. Et `report-only` existe exactement pour ne'
                           " pas découvrir en production qu'il manquait une "
                           'origine.'),
                        color="muted", size="sm",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(tr('State persistence',
                                  "Persistance de l'état"), level=2)
                    ui.text(
                        tr('By default, server state lives in memory. For '
                           'multi-worker or durability, pass `redis_url=` — '
                           'there is no `state_backend=` param, the backend '
                           'is wired at startup according to `redis_url`.',
                           "Par défaut, l'état serveur vit en mémoire. Pour "
                           'du multi-worker ou de la durabilité, passe '
                           "`redis_url=` — il n'y a pas de param "
                           '`state_backend=`, le backend est câblé au '
                           'démarrage selon `redis_url`.'),
                        color="muted", size="sm",
                    )
                    ui.table(
                        columns=[
                            ui.column("param", label="Param"),
                            ui.column("effet", label="Effet"),
                        ],
                        rows=[
                            {"param": "secret_key=",
                             "effet": tr('the HMAC key (action signatures) — '
                                         'required, ≥ 16 chars; in production'
                                         ' through an env var',
                                         "clé HMAC (signatures d'action) — "
                                         'requis, ≥ 16 chars ; en prod via '
                                         "variable d'env")},
                            {"param": "redis_url=",
                             "effet": tr('a Redis backend if supplied; memory'
                                         ' otherwise',
                                         'backend Redis si fourni ; mémoire '
                                         'sinon')},
                            {"param": "session_max_age_days=",
                             "effet": tr('session cookie lifetime (default 30)',
                                         'durée du cookie de session (défaut '
                                         '30)')},
                            {"param": "workers=",
                             "effet": "process uvicorn (Redis requis si > 1)"},
                        ],
                        size="sm",
                    )
