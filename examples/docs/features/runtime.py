"""RÉFÉRENCE — Le runtime client.

Ce que le navigateur exécute une fois la page arrivée : un moteur de
signaux, les directives `bz-*`, et un pont qui possède la frontière
transport. Chapitre de référence : on n'écrit pas ces directives à la
main dans une app Bretzel — les composants les émettent. On vient les
lire quand on sort du cadre, ou pour savoir ce qui tourne.

Toutes les tables sont introspectées depuis `bretzel/runtime/` : le
vocabulaire déclaré côté Python, confronté à ce que le JS branche
réellement. Aucun compte n'est écrit dans cette page.
"""

from __future__ import annotations

from bretzel import page, ui

from examples.docs.features.shell import shell
from examples.docs.lib.runtime_blocks import (
    directives_mirror,
    magics_mirror,
    runtime_api_mirror,
    runtime_modules_mirror,
    section,
)
from examples.docs.lib.runtime_surface import describe_magics

PATH = "/runtime"


@page(PATH, layout=shell, title="Le runtime client")
def runtime_page() -> None:
    with ui.container(width="xl"):
        with ui.vstack(gap="lg"):
            ui.heading("Le runtime client", level=1, size="3xl")
            ui.text(
                "Le serveur reste la source de vérité, mais quelque chose "
                "tourne dans le navigateur : un moteur maison, sans npm et "
                "sans framework réactif tiers. Cette page dit ce qu'il "
                "garantit, puis "
                "énumère son vocabulaire.",
                color="muted", size="lg",
            )

            with section(
                "Tu n'écris pas ça",
                "Dans une app Bretzel, les directives `bz-*` sont émises "
                "par les composants : passer `visible=binding` produit un "
                "`bz-show`, `value=binding` produit un `bz-model`. Cette "
                "page est la sortie de secours — ce qu'on lit pour "
                "comprendre ce qui a été émis, ou pour écrire à la main le "
                "cas que les composants ne couvrent pas.",
            ):
                pass

            with section(
                "Les trois garanties",
                "Un runtime client se juge sur ce qu'il promet quand le "
                "serveur réécrit la page sous ses pieds.",
            ):
                ui.table(
                    columns=[
                        ui.column("g", label="Garantie"),
                        ui.column("m", label="Le mécanisme"),
                    ],
                    rows=[
                        {
                            "g": "Un état client survit à un refresh serveur",
                            "m": "Chaque scope est keyé par bz-id. Après un "
                                 "morph, le sous-arbre est re-scanné : les "
                                 "bindings sont jetés puis recâblés, et les "
                                 "effets restaurent ce que le morph a écrasé "
                                 "(texte, display, valeur, classes).",
                        },
                        {
                            "g": "Aucun aller-retour pour de l'affichage",
                            "m": "Un binding client compile en expression JS "
                                 "évaluée dans le navigateur. Afficher, "
                                 "masquer, calculer une classe : rien ne part "
                                 "sur le réseau.",
                        },
                        {
                            "g": "La frontière transport est au runtime",
                            "m": "Un composant ne POSTe jamais. Il déclare un "
                                 "handler ; le pont ajoute la signature HMAC, "
                                 "le jeton CSRF, les en-têtes de protocole et "
                                 "l'instantané d'état client.",
                        },
                    ],
                    size="sm",
                )

            with section(
                "Ce que pèse le runtime",
                "Le bundle est concaténé depuis `_src/*.js`, sans bundler "
                "ni minifieur — le fichier servi est celui qu'on débogue. "
                "Le préfixe numérique EST l'ordre de chargement.",
            ):
                runtime_modules_mirror()

            with section(
                "Les directives",
                "Groupées par ce qu'elles garantissent. Le vocabulaire a "
                "deux moitiés — une constante Python le déclare, un module "
                "JS le branche — et le runtime ne peut pas importer Python. "
                "Une gate le vérifie déjà au commit "
                "(test_python_js_mirror.py) ; cette table le montre, un cran "
                "plus strict : commentaires ôtés, et par module source.",
            ):
                directives_mirror()

            with section(
                "Dans une expression",
                "Une expression de directive est compilée une fois puis "
                "mise en cache. Le scope courant est sur la chaîne de "
                "portée — un nom nu lit le scope — et quelques variables "
                "sont injectées.",
            ):
                magics_mirror()
                ui.code(
                    "{ open: false, pick(v) { this.open = false; } }",
                    lang="js",
                )
                ui.text(
                    "Le piège : le rebind des noms nus vaut pour les "
                    "expressions inline, pas pour les méthodes d'un scope. "
                    "Dans une méthode, c'est `this.champ` — sans le `this`, "
                    "on crée une globale.",
                    color="muted", size="sm",
                )

            with section(
                "La surface $bz",
                "L'objet global, lu module par module. Les fabriques de "
                "scope sont ce qu'un composant spread dans son `bz-data` ; "
                "le reste est le moteur. La colonne « expose » est lue dans "
                "le littéral JS, jamais recopiée.",
            ):
                runtime_api_mirror()
