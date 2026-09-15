"""RÉFÉRENCE — Config & run.

Comment on configure l'application et comment on la lance. Les tables de
paramètres de ``Bretzel()`` et ``run()`` sont lues en direct dans le code
via ``callable_signature`` — elles ne peuvent pas diverger de l'API réelle.
"""

from bretzel import Bretzel, page, ui

from examples.docs.features.shell import shell
from examples.docs.lib.blocks import callable_signature

PATH = "/config"


@page(PATH, layout=shell, title="Config & run")
def config_page() -> None:
    with ui.container(width="xl"):
        with ui.vstack(gap="lg"):
            ui.heading("Config & run", level=1, size="3xl")
            ui.text(
                "L'instance `Bretzel(...)` porte la configuration ; `run(...)` "
                "lance le serveur de dev. Les tables ci-dessous sont lues dans "
                "le code au render — elles suivent l'API sans édition.",
                color="muted", size="lg",
            )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("L'instance", level=2)
                    ui.code(
                        "from bretzel import Bretzel\n"
                        "\n"
                        "app = Bretzel(\n"
                        "    title=\"My App\",\n"
                        "    secret_key=\"…\",   # requis, ≥ 16 chars\n"
                        "    mode=\"dev\",       # \"dev\" | \"prod\" (défaut prod)\n"
                        ")\n",
                        lang="python",
                    )
                    callable_signature(Bretzel.__init__, title="Bretzel(...)")

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Lancer", level=2)
                    ui.text(
                        "`mode` (dev/prod) et `reload` (hot-reload) sont "
                        "indépendants : `mode` choisit un profil, `reload` "
                        "relance le serveur au changement de fichier.",
                        color="muted", size="sm",
                    )
                    callable_signature(Bretzel.run, title="app.run(...)")

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Ce que `mode` décide — et ne décide pas",
                               level=2)
                    ui.text(
                        "`mode` est un PRÉRÉGLAGE : il pose les valeurs "
                        "par défaut de réglages indépendants, que tu peux "
                        "surcharger un par un.",
                        color="muted", size="sm",
                    )
                    ui.table(
                        columns=[
                            ui.column("reglage", label="Réglage"),
                            ui.column("question", label="Question posée"),
                            ui.column("dev", label="dev"),
                            ui.column("prod", label="prod"),
                        ],
                        rows=[
                            {"reglage": "expose_errors=",
                             "question": "le détail des exceptions part-il "
                                         "dans la réponse ?",
                             "dev": "True", "prod": "False"},
                            {"reglage": "debug=",
                             "question": "le framework doit-il être bavard "
                                         "(warnings, IDs lisibles) ?",
                             "dev": "True", "prod": "False"},
                            {"reglage": "css=",
                             "question": "qui compile le CSS ?",
                             "dev": "browser", "prod": "build"},
                        {"reglage": "—",
                             "question": "en-têtes de cache",
                             "dev": "no-store", "prod": "immutable"},
                        ],
                        size="sm",
                    )
                    ui.text(
                        "Les deux se règlent seuls : `mode=\"prod\", "
                        "debug=True` donne une prod bavarde qui n'expose "
                        "rien, et `mode=\"dev\", expose_errors=False` permet "
                        "de voir tes vraies pages d'erreur en local.",
                        color="muted", size="sm",
                    )

                    ui.heading("Le pipeline CSS", level=3)
                    ui.text(
                        "`css=\"build\"` compile une feuille au démarrage et "
                        "la sert en `<link>` : le CSS est présent au premier "
                        "affichage. `css=\"browser\"` laisse le compilateur "
                        "Tailwind travailler dans la page — aucun binaire à "
                        "installer, mais le CSS arrive après le premier "
                        "affichage. `\"auto\"` (défaut) choisit `build` en "
                        "prod et `browser` en dev.",
                        color="muted", size="sm",
                    )
                    ui.text(
                        "Pour développer dans les conditions exactes de la "
                        "prod, demande `css=\"build\"` — il faut le "
                        "compilateur (`pip install 'bretzel[css]'`) et ça "
                        "ajoute quelques secondes à chaque démarrage. Sans "
                        "binaire, l'application le dit et repasse sur le "
                        "compilateur navigateur.",
                        color="muted", size="sm",
                    )
                    ui.code(
                        "app = Bretzel(secret_key=\"…\", mode=\"dev\", "
                        "css=\"build\")\n",
                        lang="python",
                    )

                    ui.heading("Cookies et HTTPS", level=3)
                    ui.text(
                        "L'attribut `Secure` des cookies ne dépend PAS du "
                        "mode : il suit le protocole de la requête. Un "
                        "cookie `Secure` n'est jamais renvoyé sur une origine "
                        "`http://`, donc le lier au mode couperait la session "
                        "de toute application déployée sans TLS.",
                        color="muted", size="sm",
                    )
                    ui.code(
                        "# Derrière un proxy qui termine le TLS : dis-le à\n"
                        "# uvicorn, il réécrit le protocole vu par l'app.\n"
                        "app.run(proxy_headers=True)\n"
                        "\n"
                        "# Ou force-le, si le proxy n'envoie pas d'en-tête.\n"
                        "app = Bretzel(secret_key=\"…\", secure_cookies=True)\n",
                        lang="python",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Les en-têtes de sécurité", level=2)
                    ui.text(
                        "Trois en-têtes sont posés PAR DÉFAUT, parce qu'ils "
                        "ne peuvent casser aucune app : `nosniff`, "
                        "`Referrer-Policy`, `X-Frame-Options`. "
                        "`security_headers=False` existe pour l'app qui les "
                        "pose elle-même en amont, derrière son proxy.",
                        color="muted", size="sm",
                    )
                    ui.divider()
                    ui.text(
                        "La CSP, elle, est OPT-IN — et c'est un partage, pas "
                        "un oubli : Bretzel ne peut pas deviner les polices, "
                        "les CDN et les iframes de ton app. Il calcule ce "
                        "qu'il se doit à lui-même (les empreintes de ses "
                        "scripts inline, les origines de ses assets) ; tu "
                        "ajoutes les tiennes. On élargit, jamais on ne "
                        "rétrécit.",
                        color="muted", size="sm",
                    )
                    ui.code(
                        "# 1. Le premier barreau : le navigateur ÉVALUE la\n"
                        "#    politique et signale ce qui aurait sauté, sans\n"
                        "#    rien bloquer.\n"
                        "app = Bretzel(secret_key=\"…\", csp=\"report-only\")\n"
                        "\n"
                        "# 2. On regarde ce qui remonte, on complète, puis on\n"
                        "#    ferme.\n"
                        "app = Bretzel(secret_key=\"…\", csp=True, csp_sources={\n"
                        "    \"font-src\": [\"https://fonts.gstatic.com\"],\n"
                        "    \"frame-src\": [\"https://www.youtube.com\"],\n"
                        "})\n",
                        lang="python",
                    )
                    ui.text(
                        "Le mode et les sources sont deux axes séparés à "
                        "dessein : un dict qui voudrait dire « active ET "
                        "étends » ferait deux façons d'écrire la même chose. "
                        "Et `report-only` existe exactement pour ne pas "
                        "découvrir en production qu'il manquait une origine.",
                        color="muted", size="sm",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Persistance de l'état", level=2)
                    ui.text(
                        "Par défaut, l'état serveur vit en mémoire. Pour du "
                        "multi-worker ou de la durabilité, passe `redis_url=` "
                        "— il n'y a pas de param `state_backend=`, le backend "
                        "est câblé au démarrage selon `redis_url`.",
                        color="muted", size="sm",
                    )
                    ui.table(
                        columns=[
                            ui.column("param", label="Param"),
                            ui.column("effet", label="Effet"),
                        ],
                        rows=[
                            {"param": "secret_key=",
                             "effet": "clé HMAC (signatures d'action) — requis, "
                                      "≥ 16 chars ; en prod via variable d'env"},
                            {"param": "redis_url=",
                             "effet": "backend Redis si fourni ; mémoire sinon"},
                            {"param": "session_max_age_days=",
                             "effet": "durée du cookie de session (défaut 30)"},
                            {"param": "workers=",
                             "effet": "process uvicorn (Redis requis si > 1)"},
                        ],
                        size="sm",
                    )
