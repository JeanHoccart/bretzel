"""RÉFÉRENCE — Structure d'app.

L'app plate : des fonctionnalités à plat qui se décorent elles-mêmes, un
``main`` qui les ``include``, un ``core`` pour le global-only. Pas de
dossier ``app/``. Cette doc EST une app plate — elle se prend elle-même
comme exemple.

⚠️ **Ce que cette page annonçait de moins que le framework.** Elle listait
trois décorateurs — ``@page`` / ``@layout`` / ``@error_page`` — sous le
titre « les trois rôles de feature ». Il y en a onze, et surtout elle ne
mentionnait nulle part ``Feature``, le contrat qui déclare ce qu'une
fonctionnalité fournit et ce dont elle dépend, vérifié en graphe au
démarrage.

D'où la correction structurelle : **la table des décorateurs RÉSOUT
chaque symbole qu'elle nomme** (:data:`MARQUEURS`), et les genres de
``Feature`` sont lus sur ``FEATURE_KINDS``, importé par la porte
publique de sa couche — ``bretzel.server``, et pas
``bretzel.server.feature``, que la gate
``test_no_example_dives_below_a_public_door`` refuse (elle a mordu ici
au premier essai). Une page qui nomme un
décorateur disparu le dit à l'écran au lieu de le laisser croire, et
``test_the_structure_chapter_names_real_decorators`` la fait rougir
avant.
"""

from __future__ import annotations

import importlib

from bretzel import page, ui
from bretzel.server import FEATURE_KINDS

from examples.docs.features.shell import shell

PATH = "/structure"

#: Ce qu'une fonctionnalité peut déclarer : le chemin pointé du
#: décorateur, la forme qu'on écrit, et ce que ça pose.
#:
#: L'ordre est celui où on les rencontre en construisant une app — les
#: vues d'abord, la mécanique ensuite.
MARQUEURS: tuple[tuple[str, str, str], ...] = (
    ("bretzel.page", '@page("/tarifs")',
     "une route qui rend une vue"),
    ("bretzel.layout", "@layout",
     "une coquille réutilisable (nav, chrome) — référencée par `layout=`"),
    ("bretzel.error_page", "@error_page(404)",
     "le rendu d'un statut HTTP"),
    ("bretzel.download", '@download("/export.csv")',
     "une route qui rend un FICHIER, pas une page"),
    ("bretzel.refreshable", "@refreshable(deps=[Panier])",
     "une zone qui se re-rend quand un état mute"),
    ("bretzel.background", "@background",
     "un travail lancé après la réponse, hors du chemin critique"),
    ("bretzel.idempotent", "@idempotent",
     "une action qu'un double clic ne doit pas exécuter deux fois"),
    ("bretzel.auth.source", "@auth.source",
     "d'où une identité peut venir (jeton d'API, proxy de confiance…)"),
    ("bretzel.auth.door", "@auth.door(OIDC(...))",
     "une porte OAuth/OIDC, et la décision d'accepter le profil"),
    ("bretzel.server.decorators.middleware", "@middleware",
     "un passage sur chaque requête"),
    ("bretzel.server.decorators.lifecycle.startup", "@startup / @shutdown",
     "l'ouverture et la fermeture des ressources de l'app"),
)


def resolve(chemin: str) -> bool:
    """Le symbole existe-t-il vraiment ?

    ⚠️ On importe le plus long préfixe importable puis on descend en
    ``getattr`` : ``bretzel.auth`` est un module, ``bretzel.page`` un
    attribut du paquet, et couper le chemin en deux échouerait sur l'un
    ou sur l'autre.
    """
    parts = chemin.split(".")
    objet = None
    reste = list(parts)
    for coupe in range(len(parts), 0, -1):
        try:
            objet = importlib.import_module(".".join(parts[:coupe]))
        except ImportError:
            continue
        reste = parts[coupe:]
        break
    if objet is None:
        return False
    for attribut in reste:
        if not hasattr(objet, attribut):
            return False
        objet = getattr(objet, attribut)
    return True


def marqueurs_table() -> None:
    """Les onze marqueurs — chacun résolu avant d'être affiché."""
    ui.table(
        columns=[
            ui.column("forme", label="Ce qu'on écrit"),
            ui.column("pose", label="Ce que ça déclare"),
        ],
        rows=[
            {
                "forme": forme if resolve(chemin)
                else f"{forme}  ⚠️ introuvable — cette page est périmée",
                "pose": pose,
            }
            for chemin, forme, pose in MARQUEURS
        ],
        size="sm",
    )


@page(PATH, layout=shell, title="Structure d'app")
def structure_page() -> None:
    with ui.container(width="xl"):
        with ui.vstack(gap="lg"):
            ui.heading("Structure d'app", level=1, size="3xl")
            ui.text(
                "Tout est une fonctionnalité, à plat. Chacune se décore "
                "elle-même ; `main` les rassemble. Pas de dossier `app/`, "
                "pas de câblage central.",
                color="muted", size="lg",
            )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Le squelette", level=2)
                    ui.code(
                        "examples/docs/\n"
                        "├── main.py            # crée Bretzel(...) + app.include(...)\n"
                        "├── features/          # tout à plat\n"
                        "│   ├── shell.py       # @layout — la coquille (nav, chrome)\n"
                        "│   ├── home.py        # @page(\"/\")\n"
                        "│   ├── components.py  # @page(\"/components\")\n"
                        "│   ├── errors.py      # @error_page(404) / @error_page(500)\n"
                        "│   └── …\n"
                        "└── lib/               # helpers partagés (introspect, blocks)\n",
                        lang="text",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Une fonctionnalité se décore elle-même",
                               level=2)
                    ui.text(
                        "Le décorateur ne fait que MARQUER la fonction. "
                        "L'enregistrement effectif arrive dans "
                        "`app.include(…)` — l'ordre des imports n'a aucun "
                        "effet.",
                        color="muted", size="sm",
                    )
                    ui.code(
                        "# features/home.py\n"
                        "from bretzel import page, ui\n"
                        "from examples.docs.features.shell import shell\n"
                        "\n"
                        "@page(\"/\", layout=shell, title=\"Accueil\")\n"
                        "def home_page() -> None:\n"
                        "    ui.heading(\"Bienvenue\")\n",
                        lang="python",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("main rassemble", level=2)
                    ui.text(
                        "`app.include(module, …)` scanne les modules pour "
                        "leurs marques. Le `shell` (`@layout`) n'a pas "
                        "besoin d'être inclus — il se résout par référence "
                        "via `layout=shell`.",
                        color="muted", size="sm",
                    )
                    ui.code(
                        "# main.py\n"
                        "from bretzel import Bretzel\n"
                        "\n"
                        "app = Bretzel(secret_key=\"…\", mode=\"dev\")\n"
                        "\n"
                        "from examples.docs.features import home, components, errors\n"
                        "app.include(home, components, errors)\n",
                        lang="python",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("À plat, oui — mais pas obligatoirement",
                               level=2)
                    ui.text(
                        "« À plat » est le défaut, pas une contrainte. "
                        "Un dossier par domaine marche, et le framework "
                        "n'a rien à savoir : `include` scanne les "
                        "callables de premier niveau du module qu'on lui "
                        "donne. Il suffit donc que le `__init__.py` du "
                        "sous-dossier RÉEXPORTE ses pages.",
                        color="muted", size="sm",
                    )
                    ui.code(
                        "monapp/\n"
                        "├── main.py\n"
                        "└── facturation/          # un domaine, un dossier\n"
                        "    ├── __init__.py       # réexporte les pages\n"
                        "    ├── devis.py          # @page(\"/devis\")\n"
                        "    └── factures.py       # @page(\"/factures\")\n",
                        lang="text",
                    )
                    ui.code(
                        "# facturation/__init__.py\n"
                        "from monapp.facturation.devis import devis_page\n"
                        "from monapp.facturation.factures import factures_page\n"
                        "\n"
                        "# main.py\n"
                        "from monapp import facturation\n"
                        "app.include(facturation)      # les deux routes montent\n",
                        lang="python",
                    )
                    ui.alert(
                        "Le piège est là, et il est silencieux : si le "
                        "`__init__.py` réexporte les MODULES "
                        "(`from . import devis, factures`) au lieu des "
                        "fonctions, `include` ne trouve aucune marque et "
                        "les routes rendent 404 — sans erreur au "
                        "démarrage. Mesuré. Dans ce cas, incluez les "
                        "modules eux-mêmes : "
                        "`app.include(facturation.devis, facturation.factures)`.",
                        color="warning",
                        title="Réexporter les FONCTIONS, pas les modules",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(f"Les {len(MARQUEURS)} marqueurs", level=2)
                    ui.text(
                        "Une fonctionnalité ne déclare pas que des vues. "
                        "Tout ce qui suit se pose de la même façon — on "
                        "décore une fonction au niveau du module, et "
                        "`include` la ramasse.",
                        color="muted", size="sm",
                    )
                    marqueurs_table()
                    ui.text(
                        "Chaque ligne est vérifiée à l'affichage : le "
                        "symbole est résolu pour de vrai. Un décorateur "
                        "renommé se signalerait ici au lieu de laisser "
                        "croire qu'il existe.",
                        color="muted", size="xs",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Quand l'app grandit : déclarer un contrat",
                               level=2)
                    ui.text(
                        "À plat et sans contrat, rien n'empêche une "
                        "fonctionnalité d'en importer une autre en douce. "
                        "`Feature` rend la dépendance explicite : ce que je "
                        "fournis, ce dont je me sers, ce que je lis. Le "
                        "graphe est vérifié au démarrage — dépendance "
                        "inconnue, cycle et collision de noms sont des "
                        "erreurs, pas des surprises à l'exécution.",
                        color="muted", size="sm",
                    )
                    ui.code(
                        "# features/cart/feature.py\n"
                        "from bretzel import Feature\n"
                        "from .state import CartState\n"
                        "from .ui import cart_page\n"
                        "\n"
                        "feature = Feature(\n"
                        "    name=\"cart\",\n"
                        "    kind=\"page\",\n"
                        "    provides=[CartState, cart_page],   # ma surface publique\n"
                        "    uses=[\"catalog_data\", \"money\"], # les seules que je peux importer\n"
                        ")\n",
                        lang="python",
                    )
                    ui.text(
                        f"`kind=` prend l'une des {len(FEATURE_KINDS)} "
                        f"valeurs suivantes : "
                        f"{', '.join('`' + k + '`' for k in sorted(FEATURE_KINDS))}.",
                        color="muted", size="sm",
                    )
                    with ui.hstack(gap="sm", wrap=True, align="baseline"):
                        ui.text("Le graphe rendu en direct sur une app de "
                                "démo :", color="muted", size="sm")
                        ui.link("Carte de l'app →", href="/app-map")

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Faire juger la structure", level=2)
                    ui.text(
                        "`check` lit le code écrit contre le framework. "
                        "Avec `--deep`, il monte l'app désignée et arbitre "
                        "aussi sa carte — ce qu'une lecture de fichiers "
                        "seule ne peut pas voir.",
                        color="muted", size="sm",
                    )
                    ui.code(
                        "py -m bretzel.cli.main check examples\n"
                        "py -m bretzel.cli.main check --deep examples.docs.main:app\n",
                        lang="bash",
                    )

            with ui.card(color="surface"):
                ui.text(
                    "Cette doc tourne exactement comme ça : "
                    "`examples/docs/features/` à plat, `shell.py` en "
                    "`@layout`, `main.py` qui `include`. Ce que tu lis EST "
                    "le pattern. `core/` (quand il existe) porte le "
                    "global-only : états partagés, config transverse — pas "
                    "de vue.",
                    color="muted", size="sm",
                )
