"""RÉFÉRENCE — Le navigateur.

Ce que Bretzel sait demander à la machine de l'utilisateur : copier,
imprimer, passer en plein écran, partager, vibrer — plus servir un
fichier et se faire installer comme une application.

Chapitre écrit le 2026-09-02, parce que ces trois familles sont arrivées
le même jour et qu'aucune n'avait de récit. Elles apparaissaient déjà
dans la cheat-sheet — la gate de classement l'impose — mais une liste
dit qu'une chose existe, pas ce qu'elle coûte ni où elle casse.

⚠️ Les signatures et les besoins sont INTROSPECTÉS
(``describe_ui_symbol`` / ``callable_signature``). Ce qui est écrit à la
main ici, ce sont les pièges — et chacun a été mesuré, pas supposé.

⚠️ **Chaque section vit dans une ``ui.card``, et il a fallu qu'on le
remarque à l'œil.** C'était la SEULE page du dépôt sans une seule carte —
mesuré : ``theme`` en a douze, ``structure`` sept, ``actions_client``
six, ``state_server`` cinq, et celle-ci zéro. Ses sections flottaient
donc à même le fond de page, et elle ne ressemblait à aucune autre.
"""

from __future__ import annotations

import bretzel
from bretzel import PWA, download, page, ui

from examples.docs.features.shell import shell
from examples.docs.lib.blocks import callable_signature, source_block

PATH = "/browser"


def piege(titre: str, texte: str) -> None:
    """Un piège MESURÉ — la forme visuelle de ce chapitre.

    Un composant maison plutôt qu'un ``ui.alert`` répété : la page en
    porte six, et les recopier ferait diverger le ton au troisième.
    """
    # `ui.alert` est une FEUILLE : le message passe en paramètre, pas
    # en enfant (`describe alert` le dit, et le socle refuse le `with`).
    ui.alert(texte, color="warning", title=titre)


@page(PATH, layout=shell, title="Le navigateur")
def browser_page() -> None:
    with ui.container(width="lg"):
        with ui.vstack(gap="lg"):
            ui.heading("Le navigateur", level=1, size="3xl")
            ui.text(
                "Le serveur reste la source de vérité, mais certaines "
                "choses n'existent que sur la machine de l'utilisateur : "
                "son presse-papiers, son imprimante, son écran, sa "
                "feuille de partage. Bretzel les atteint de trois "
                "façons, et chacune répond à une contrainte différente.",
                color="muted",
            )

            # ── 1. Les verbes ────────────────────────────────────────
            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("1. Les verbes — une action, une chaîne",
                               level=2)
                    ui.text(
                        "Un verbe produit du JavaScript et se branche "
                        "dans un `on_*=`. Il ne coûte presque rien parce "
                        "que le slot existait déjà : `on_<event>=` est "
                        "polymorphe — un callable part en POST signé "
                        "vers le serveur, une CHAÎNE est évaluée sur "
                        "place, sans aller-retour. C'est le contrat de "
                        "`dialog.open()` ; les verbes s'y branchent sans "
                        "ajouter ni directive, ni scope, ni requête.",
                        color="muted", size="sm",
                    )
                    for verbe in (bretzel.copy, bretzel.print_page,
                                  bretzel.fullscreen, bretzel.share,
                                  bretzel.vibrate):
                        callable_signature(verbe)

                    ui.heading("Ce qu'ils font, en une ligne chacun",
                               level=3)
                    source_block(exemple_verbes)

                    piege(
                        "Le presse-papiers exige un contexte SÉCURISÉ",
                        "`navigator.clipboard` n'existe que sur https:// "
                        "ou localhost. Sur http:// avec une IP de réseau "
                        "local — la façon dont un outil interne se sert "
                        "— il vaut `undefined`, et un appel nu ne ferait "
                        "RIEN, sans un mot. Bretzel replie sur "
                        "`document.execCommand`, déprécié et seul chemin "
                        "qui existe là-bas.",
                    )
                    piege(
                        "`share` retombe sur la copie, et c'est le contrat",
                        "`navigator.share` est absente du Chromium de "
                        "bureau (mesuré). L'absence n'est donc pas un "
                        "cas limite, c'est le cas NORMAL là où l'on "
                        "développe. Plutôt qu'un bouton « Partager » "
                        "inerte, le verbe copie l'URL. En revanche un "
                        "partage ANNULÉ par l'utilisateur ne retombe pas "
                        "dessus : fermer la feuille copierait dans son "
                        "dos.",
                    )
                    piege(
                        "Aucun retour visuel sur `copy`",
                        "C'est le contrat, pas un oubli : le verbe "
                        "copie, l'app câble le retour qu'elle veut. Rien "
                        "n'indique à l'utilisateur que le clic a pris.",
                    )

            # ── 2. @download ─────────────────────────────────────────
            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(
                        "2. @download — un routable qui rend un fichier",
                        level=2,
                    )
                    ui.text(
                        "Ce n'est PAS une action, et la contrainte est "
                        "structurelle : la réponse d'une action est "
                        "avalée par le bridge et appliquée en "
                        "`<bz-patch>`, alors qu'un téléchargement doit "
                        "ÊTRE le fichier. C'est donc un "
                        "`ui.link(href=…)` ordinaire, pas un `on_click=`.",
                        color="muted", size="sm",
                    )
                    callable_signature(download)
                    source_block(exemple_download)

                    ui.heading("Quatre formes rendues", level=3)
                    ui.table(
                        rows=[
                            {"forme": "list[dict]",
                             "sortie": "un CSV — en-têtes déduits des clés "
                             "du premier enregistrement, BOM UTF-8, "
                             "citation RFC 4180"},
                            {"forme": "str", "sortie": "le texte tel quel"},
                            {"forme": "bytes",
                             "sortie": "les octets tels quels — un PDF, "
                             "une image, un zip"},
                            {"forme": "Response",
                             "sortie": "l'échappatoire, testée en "
                             "PREMIER : tout ce que le reste ne couvre pas"},
                        ],
                        columns=[
                            ui.column("forme",
                                      label="ce que la fonction rend"),
                            ui.column("sortie",
                                      label="ce que le navigateur reçoit"),
                        ],
                    )

                    piege(
                        "Il n'est PAS signé, contrairement à l'export du "
                        "datatable",
                        "Et c'est la différence qui justifie le "
                        "routable. Le lien du datatable porte dans son "
                        "URL le NOM de la fonction à invoquer, donc il "
                        "DOIT être signé — et il hérite d'être une "
                        "capacité au porteur, sans expiration. Un "
                        "`@download` fixe sa fonction à la DÉCORATION, "
                        "comme `@page` : l'URL ne décide de rien, et la "
                        "route passe par le même middleware. Une app qui "
                        "protège ses pages protège ses téléchargements.",
                    )
                    piege(
                        "`ui.datatable(exportable=True)` n'est PAS "
                        "branché dessus",
                        "Les deux mécanismes coexistent aujourd'hui, ce "
                        "que le principe 4 refuse — et c'est écrit "
                        "plutôt que caché. L'export du datatable a "
                        "besoin de la requête du LECTEUR (tri, filtres "
                        "au moment du clic), qui n'existe pas dans une "
                        "route statique. Les rebrancher demande de "
                        "décider comment une VUE voyage jusqu'à un "
                        "`@download`.",
                    )

            # ── 3. PWA ───────────────────────────────────────────────
            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("3. PWA — l'app devient installable",
                               level=2)
                    ui.text(
                        "Le manifeste décrit l'app au système : son nom, "
                        "son icône, sa couleur, et le fait qu'elle "
                        "s'ouvre en fenêtre PROPRE plutôt que dans un "
                        "onglet. C'est ce qui donne à un outil interne "
                        "une icône dans le menu Démarrer.",
                        color="muted", size="sm",
                    )
                    callable_signature(PWA)
                    source_block(exemple_pwa)

                    piege(
                        "Ça ne rend RIEN disponible hors ligne",
                        "Le hors ligne demande un service worker — un "
                        "script qui intercepte chaque requête. Ce n'est "
                        "pas livré, délibérément : c'est un cycle de vie "
                        "entier (versions, invalidation, mise à jour "
                        "d'une app déjà installée chez quelqu'un), et un "
                        "endroit où l'on casse une app en production en "
                        "croyant l'améliorer.",
                    )
                    piege(
                        "Si l'invite « Installer » n'apparaît pas, ce "
                        "n'est pas le manifeste",
                        "Chrome a longtemps exigé EN PLUS un service "
                        "worker pour la proposer. Ce que Bretzel "
                        "garantit et qui est mesuré : le manifeste est "
                        "servi, valide, correctement typé et lié — c'est "
                        "Chromium lui-même qui le dit "
                        "(`Page.getAppManifest`, zéro erreur).",
                    )

            with ui.card(color="surface"):
                with ui.vstack(gap="sm"):
                    ui.heading("Ce que Bretzel ne sait PAS encore faire",
                               level=2)
                    ui.text(
                        "Écrit ici pour que la liste du dessus ne se "
                        "lise pas comme complète. Aucune de ces "
                        "capacités n'a la moindre amorce dans le code : "
                        "géolocalisation, caméra, état réseau, "
                        "notification système, verrou d'écran, base "
                        "IndexedDB. Elles demandent toutes un patron "
                        "neuf — une PERMISSION et une ATTENTE — qu'un "
                        "verbe synchrone ne peut pas porter.",
                        color="muted", size="sm",
                    )


# ── Les exemples, en vraies fonctions pour que `source_block` les lise ──
def exemple_verbes() -> None:
    ui.button("Copier la clé", on_click=bretzel.copy(state.api_key))
    ui.button("Imprimer", on_click=bretzel.print_page())
    ui.button("Plein écran", on_click=bretzel.fullscreen(carte))
    ui.button("Partager cette vue", on_click=bretzel.share())
    ui.button("Vibrer", on_click=bretzel.vibrate([50, 30, 50]))


def exemple_download() -> None:
    @download("/clients.csv")
    async def clients_csv() -> list[dict]:
        return await db.clients()

    # ⚠️ `download=True` est OBLIGATOIRE : sans lui, `hx-boost` avale le
    # lien et le CSV arrive comme du HTML dans l'outlet, sans aucun signe
    # côté serveur. L'exemple l'omettait alors que la page /capabilities
    # le disait — deux pages qui se contredisaient.
    ui.link("Exporter les clients", href="/clients.csv", download=True)


def exemple_pwa() -> None:
    app = Bretzel(
        title="Tracker",
        secret_key=...,
        pwa=PWA(name="Tracker", icon="/static/logo.png",
                theme_color="#0f172a"),
    )
