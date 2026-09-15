"""SUJET — Parler la langue de qui visite.

Le partage est net, et c'est lui qu'il faut comprendre avant d'écrire
une ligne :

- **le framework traduit SES phrases** — « Aller à la diapositive 3 »,
  « Taille maximale 8 Mo », les libellés d'accessibilité que personne
  n'écrit à la main. C'est ``bretzel.render.text``, et une app n'a rien
  à faire pour en profiter ;
- **l'app traduit LES SIENNES.** Bretzel ne les connaît pas et ne les
  connaîtra pas. Il fournit la couture : ``Language().code``.

⚠️ Ce n'est PAS une bibliothèque d'i18n. Pas de fichiers `.po`, pas de
pluriels, pas de dates localisées au-delà de ce que le navigateur fait.
La feuille de route l'annonce en 2.1 — ce chapitre décrit ce qui EXISTE.
"""

from __future__ import annotations

from bretzel import page, ui
from examples.docs.features.shell import shell

PATH = "/languages"


@page(PATH, layout=shell, title="Les langues")
def languages_page() -> None:
    with ui.container(width="lg"):
        with ui.vstack(gap="lg"):
            ui.heading("Parler la langue de qui visite", level=1,
                       size="3xl")
            ui.text(
                "Deux moitiés, et une seule vous appartient : le "
                "framework traduit ses propres phrases, votre app "
                "traduit les siennes.",
                color="muted", size="lg",
            )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Ce que le framework fait tout seul",
                               level=2)
                    ui.text(
                        "Les phrases que Bretzel produit — libellés "
                        "d'accessibilité d'un carrousel, message de "
                        "taille maximale d'un `file_upload`, texte d'un "
                        "tableau vide — passent par sa propre table. "
                        "Déclarez les langues de l'app, et elles "
                        "suivent.",
                        color="muted", size="sm",
                    )
                    ui.code(
                        "app = Bretzel(\n"
                        "    secret_key=\"…\",\n"
                        "    lang=\"fr\",                  # la langue par défaut\n"
                        "    languages=(\"fr\", \"en\"),     # celles qu'on accepte\n"
                        ")\n",
                        lang="python",
                    )
                    ui.text(
                        "La langue est résolue PAR REQUÊTE : un choix "
                        "explicite l'emporte sur l'en-tête du "
                        "navigateur, et une langue qu'on n'a pas "
                        "déclarée retombe sur le défaut plutôt que de "
                        "rendre une clé brute.",
                        color="muted", size="sm",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Ce que votre app doit faire", level=2)
                    ui.text(
                        "`Language()` se lit comme ses trois sœurs "
                        "d'ambiance — `Screen()`, `ColorScheme()`, "
                        "`LiveConnection()` : un objet, un champ. À vous "
                        "la table.",
                        color="muted", size="sm",
                    )
                    ui.code(
                        "from bretzel import Language\n"
                        "\n"
                        "PHRASES = {\n"
                        "    \"fr\": {\"save\": \"Enregistrer\",\n"
                        "            \"cancel\": \"Annuler\"},\n"
                        "    \"en\": {\"save\": \"Save\", \"cancel\": \"Cancel\"},\n"
                        "}\n"
                        "\n"
                        "def dire(cle: str) -> str:\n"
                        "    \"\"\"Une fonction, pas un composant : c'est du\n"
                        "    TEXTE, et il doit pouvoir aller dans un\n"
                        "    `placeholder=` comme dans un `ui.text`.\"\"\"\n"
                        "    code = Language().code.split(\"-\")[0]\n"
                        "    return PHRASES.get(code, PHRASES[\"en\"])[cle]\n"
                        "\n"
                        "ui.button(dire(\"save\"), color=\"primary\")\n",
                        lang="python",
                    )
                    ui.text(
                        "`Language().code` peut porter une région "
                        "(`fr-CA`, `en-GB`). Couper au tiret est la "
                        "forme la plus simple qui marche ; garder la "
                        "région n'a de sens que si la table la "
                        "distingue vraiment.",
                        color="muted", size="sm",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Laisser choisir", level=2)
                    ui.text(
                        "`Language.set` est un handler SERVEUR : il "
                        "choisit la langue et recharge la page dedans. "
                        "On le passe donc en `partial`, pas en appel — "
                        "`Language.set(\"fr\")` s'exécuterait au RENDU, "
                        "pas au clic.",
                        color="muted", size="sm",
                    )
                    ui.code(
                        "from functools import partial\n"
                        "\n"
                        "ui.button(\"Français\", on_click=partial(Language.set, \"fr\"))\n"
                        "ui.button(\"English\", on_click=partial(Language.set, \"en\"))\n",
                        lang="python",
                    )
                    ui.text(
                        "Pourquoi ça existe alors que la langue est "
                        "déjà automatique : `Accept-Language` décrit la "
                        "configuration du système d'exploitation, pas un "
                        "choix de lecture. Sans un moyen de dire le "
                        "contraire, quelqu'un dont la machine est en "
                        "anglais ne peut pas lire en français.",
                        color="muted", size="sm",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Ce que ça ne fait pas", level=2)
                    ui.alert(
                        "Ce n'est pas une bibliothèque d'i18n. Pas de "
                        "fichiers `.po`, pas de règles de pluriel, pas "
                        "d'extraction de chaînes, pas de formatage de "
                        "dates ou de devises au-delà de ce que le "
                        "navigateur sait faire. C'est une COUTURE : la "
                        "langue de la requête, et la table du framework "
                        "pour ses propres mots. La feuille de route "
                        "annonce l'i18n complète en 2.1.",
                        color="warning", title="Une couture, pas une lib",
                    )
                    ui.text(
                        "Ce partage est un choix, pas un manque de "
                        "temps : les phrases d'une app lui appartiennent, "
                        "et un framework qui imposerait son format de "
                        "catalogue imposerait aussi son outillage.",
                        color="muted", size="sm",
                    )
