"""REFERENCE — The browser.

What Bretzel can ask of the user's machine: copy, print, go full screen,
share, vibrate — plus serving a file and getting itself installed as an
application.

Chapter written on 2026-09-02, because these three families arrived on
the same day and none had a narrative. They already appeared in the cheat
sheet — the classification gate requires it — but a list says a thing
exists, not what it costs nor where it breaks.

⚠️ The signatures and the needs are INTROSPECTED
(``describe_ui_symbol`` / ``callable_signature``). What is written by
hand here are the traps — and each one was measured, not assumed.

⚠️ **Every section lives in a ``ui.card``, and it took noticing by eye.**
It was the repository's ONLY page without a single card — measured:
``theme`` has twelve, ``structure`` seven, ``actions_client`` six,
``state_server`` five, and this one zero. So its sections floated
straight on the page background, and it looked like no other.
"""

from __future__ import annotations

import bretzel
from bretzel import PWA, download, page, ui

from examples.docs.features.shell import shell
from examples.docs.lib.blocks import callable_signature, source_block
from examples.docs.lib.i18n import tr

PATH = "/browser"


def piege(titre: str, texte: str) -> None:
    """A MEASURED trap — this chapter's visual form.

    A home-made component rather than a repeated ``ui.alert``: the page
    carries six, and copying them would make the tone drift by the third.
    """
    # `ui.alert` is a LEAF: the message goes in as a parameter, not as a
    # child (`describe alert` says so, and the base layer refuses the
    # `with`).
    ui.alert(texte, color="warning", title=titre)


@page(PATH, layout=shell, title=tr('The browser',
                                   'Le navigateur'))
def browser_page() -> None:
    with ui.container(width="xl"):
        with ui.vstack(gap="lg"):
            ui.heading(tr('The browser',
                          'Le navigateur'), level=1, size="3xl")
            ui.text(
                tr('The server stays the source of truth, but some things '
                   "exist only on the user's machine: their clipboard, their "
                   'printer, their screen, their share sheet. Bretzel reaches'
                   ' them in three ways, and each answers a different '
                   'constraint.',
                   'Le serveur reste la source de vérité, mais certaines '
                   "choses n'existent que sur la machine de l'utilisateur : "
                   'son presse-papiers, son imprimante, son écran, sa feuille'
                   ' de partage. Bretzel les atteint de trois façons, et '
                   'chacune répond à une contrainte différente.'),
                color="muted",
            )

            # ── 1. Les verbes ────────────────────────────────────────
            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(tr('1. The verbs — an action, a string',
                                  '1. Les verbes — une action, une chaîne'),
                               level=2)
                    ui.text(
                        tr('A verb produces JavaScript and plugs into an '
                           '`on_*=`. It costs almost nothing because the slot'
                           ' already existed: `on_<event>=` is polymorphic — '
                           'a callable leaves as a signed POST to the server,'
                           ' a STRING is evaluated in place, with no round '
                           "trip. It is `dialog.open()`'s contract; the verbs"
                           ' plug into it without adding a directive, a scope'
                           ' or a request.',
                           'Un verbe produit du JavaScript et se branche dans'
                           ' un `on_*=`. Il ne coûte presque rien parce que '
                           'le slot existait déjà : `on_<event>=` est '
                           'polymorphe — un callable part en POST signé vers '
                           'le serveur, une CHAÎNE est évaluée sur place, '
                           "sans aller-retour. C'est le contrat de "
                           "`dialog.open()` ; les verbes s'y branchent sans "
                           'ajouter ni directive, ni scope, ni requête.'),
                        color="muted", size="sm",
                    )
                    for verbe in (bretzel.copy, bretzel.print_page,
                                  bretzel.fullscreen, bretzel.share,
                                  bretzel.vibrate):
                        callable_signature(verbe)

                    ui.heading(tr('What they do, one line each',
                                  "Ce qu'ils font, en une ligne chacun"),
                               level=3)
                    source_block(exemple_verbes)

                    piege(
                        tr('The clipboard demands a SECURE context',
                           'Le presse-papiers exige un contexte SÉCURISÉ'),
                        tr('`navigator.clipboard` only exists over https:// '
                           'or localhost. Over http:// with a local-network '
                           'IP — the way an internal tool gets used — it is '
                           '`undefined`, and a bare call would do NOTHING, '
                           'without a word. Bretzel falls back to '
                           '`document.execCommand`, deprecated and the only '
                           'route that exists there.',
                           "`navigator.clipboard` n'existe que sur https:// "
                           'ou localhost. Sur http:// avec une IP de réseau '
                           'local — la façon dont un outil interne se sert — '
                           'il vaut `undefined`, et un appel nu ne ferait '
                           'RIEN, sans un mot. Bretzel replie sur '
                           '`document.execCommand`, déprécié et seul chemin '
                           'qui existe là-bas.'),
                    )
                    piege(
                        tr('`share` falls back to copying, and that is the '
                           'contract',
                           "`share` retombe sur la copie, et c'est le contrat"),
                        tr('`navigator.share` is absent from desktop Chromium'
                           ' (measured). Its absence is therefore not an edge'
                           ' case, it is the NORMAL case where one develops. '
                           'Rather than an inert “Share” button, the verb '
                           'copies the URL. A share CANCELLED by the user, on'
                           ' the other hand, does not fall back on it: '
                           'closing the sheet would copy behind their back.',
                           '`navigator.share` est absente du Chromium de '
                           "bureau (mesuré). L'absence n'est donc pas un cas "
                           "limite, c'est le cas NORMAL là où l'on développe."
                           " Plutôt qu'un bouton « Partager » inerte, le "
                           "verbe copie l'URL. En revanche un partage ANNULÉ "
                           "par l'utilisateur ne retombe pas dessus : fermer "
                           'la feuille copierait dans son dos.'),
                    )
                    piege(
                        "Aucun retour visuel sur `copy`",
                        tr('That is the contract, not an oversight: the verb '
                           'copies, the app wires whatever feedback it wants.'
                           ' Nothing tells the user the click took.',
                           "C'est le contrat, pas un oubli : le verbe copie, "
                           "l'app câble le retour qu'elle veut. Rien "
                           "n'indique à l'utilisateur que le clic a pris."),
                    )

            # ── 2. @download ─────────────────────────────────────────
            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(
                        tr('2. @download — a routable that returns a file',
                           '2. @download — un routable qui rend un fichier'),
                        level=2,
                    )
                    ui.text(
                        tr('This is NOT an action, and the constraint is '
                           "structural: an action's response is swallowed by "
                           'the bridge and applied as a `<bz-patch>`, whereas'
                           ' a download must BE the file. So it is an '
                           'ordinary `ui.link(href=…)`, not an `on_click=`.',
                           "Ce n'est PAS une action, et la contrainte est "
                           "structurelle : la réponse d'une action est avalée"
                           ' par le bridge et appliquée en `<bz-patch>`, '
                           "alors qu'un téléchargement doit ÊTRE le fichier. "
                           "C'est donc un `ui.link(href=…)` ordinaire, pas un"
                           ' `on_click=`.'),
                        color="muted", size="sm",
                    )
                    callable_signature(download)
                    source_block(exemple_download)

                    ui.heading("Quatre formes rendues", level=3)
                    ui.table(
                        rows=[
                            {"forme": "list[dict]",
                             "sortie": tr('a CSV — headers derived from the '
                                          "first record's keys, UTF-8 BOM, "
                                          'RFC 4180 quoting',
                                          'un CSV — en-têtes déduits des clés'
                                          ' du premier enregistrement, BOM '
                                          'UTF-8, citation RFC 4180')},
                            {"forme": "str", "sortie": tr('the text as is',
                                                          'le texte tel quel')},
                            {"forme": "bytes",
                             "sortie": tr('the bytes as they are — a PDF, an '
                                          'image, a zip',
                                          'les octets tels quels — un PDF, '
                                          'une image, un zip')},
                            {"forme": "Response",
                             "sortie": tr('the escape hatch, tested FIRST: '
                                          'everything the rest does not cover',
                                          "l'échappatoire, testée en PREMIER "
                                          ': tout ce que le reste ne couvre '
                                          'pas')},
                        ],
                        columns=[
                            ui.column("forme",
                                      label=tr('what the function returns',
                                               'ce que la fonction rend')),
                            ui.column("sortie",
                                      label=tr('what the browser receives',
                                               'ce que le navigateur reçoit')),
                        ],
                    )

                    piege(
                        tr("It is NOT signed, unlike the datatable's export",
                           "Il n'est PAS signé, contrairement à l'export du "
                           'datatable'),
                        tr('And that is the difference that justifies the '
                           "routable. The datatable's link carries in its URL"
                           ' the NAME of the function to invoke, so it MUST '
                           'be signed — and it inherits being a bearer '
                           'capability, with no expiry. A `@download` fixes '
                           'its function at DECORATION time, like `@page`: '
                           'the URL decides nothing, and the route goes '
                           'through the same middleware. An app that protects'
                           ' its pages protects its downloads.',
                           "Et c'est la différence qui justifie le routable. "
                           'Le lien du datatable porte dans son URL le NOM de'
                           ' la fonction à invoquer, donc il DOIT être signé '
                           "— et il hérite d'être une capacité au porteur, "
                           'sans expiration. Un `@download` fixe sa fonction '
                           "à la DÉCORATION, comme `@page` : l'URL ne décide "
                           'de rien, et la route passe par le même '
                           'middleware. Une app qui protège ses pages protège'
                           ' ses téléchargements.'),
                    )
                    piege(
                        tr('`ui.datatable(exportable=True)` is NOT wired to it',
                           "`ui.datatable(exportable=True)` n'est PAS branché"
                           ' dessus'),
                        tr('The two mechanisms coexist today, which principle'
                           ' 4 refuses — and that is written down rather than'
                           " hidden. The datatable's export needs the "
                           "READER's query (sort, filters at click time), "
                           'which does not exist in a static route. Rewiring '
                           'them means deciding how a VIEW travels as far as '
                           'a `@download`.',
                           "Les deux mécanismes coexistent aujourd'hui, ce "
                           "que le principe 4 refuse — et c'est écrit plutôt "
                           "que caché. L'export du datatable a besoin de la "
                           'requête du LECTEUR (tri, filtres au moment du '
                           "clic), qui n'existe pas dans une route statique. "
                           'Les rebrancher demande de décider comment une VUE'
                           " voyage jusqu'à un `@download`."),
                    )

            # ── 3. PWA ───────────────────────────────────────────────
            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("3. PWA — l'app devient installable",
                               level=2)
                    ui.text(
                        tr('The manifest describes the app to the system: its'
                           ' name, its icon, its colour, and the fact that it'
                           ' opens in its OWN window rather than in a tab. It'
                           ' is what gives an internal tool an icon in the '
                           'Start menu.',
                           "Le manifeste décrit l'app au système : son nom, "
                           "son icône, sa couleur, et le fait qu'elle s'ouvre"
                           ' en fenêtre PROPRE plutôt que dans un onglet. '
                           "C'est ce qui donne à un outil interne une icône "
                           'dans le menu Démarrer.'),
                        color="muted", size="sm",
                    )
                    callable_signature(PWA)
                    source_block(exemple_pwa)

                    piege(
                        tr('It makes NOTHING available offline',
                           'Ça ne rend RIEN disponible hors ligne'),
                        tr('Offline needs a service worker — a script '
                           'intercepting every request. It is not shipped, '
                           'deliberately: it is a whole lifecycle (versions, '
                           'invalidation, updating an app already installed '
                           "on somebody's machine), and a place where one "
                           'breaks an app in production while believing one '
                           'is improving it.',
                           'Le hors ligne demande un service worker — un '
                           "script qui intercepte chaque requête. Ce n'est "
                           "pas livré, délibérément : c'est un cycle de vie "
                           "entier (versions, invalidation, mise à jour d'une"
                           " app déjà installée chez quelqu'un), et un "
                           "endroit où l'on casse une app en production en "
                           "croyant l'améliorer."),
                    )
                    piege(
                        tr('If the “Install” prompt does not appear, it is '
                           'not the manifest',
                           "Si l'invite « Installer » n'apparaît pas, ce "
                           "n'est pas le manifeste"),
                        tr('Chrome long ALSO demanded a service worker before'
                           ' offering it. What Bretzel guarantees and what is'
                           ' measured: the manifest is served, valid, '
                           'correctly typed and linked — and it is Chromium '
                           'itself that says so (`Page.getAppManifest`, zero '
                           'errors).',
                           'Chrome a longtemps exigé EN PLUS un service '
                           'worker pour la proposer. Ce que Bretzel garantit '
                           'et qui est mesuré : le manifeste est servi, '
                           "valide, correctement typé et lié — c'est Chromium"
                           ' lui-même qui le dit (`Page.getAppManifest`, zéro'
                           ' erreur).'),
                    )

            with ui.card(color="surface"):
                with ui.vstack(gap="sm"):
                    ui.heading(tr('What Bretzel can NOT do yet',
                                  'Ce que Bretzel ne sait PAS encore faire'),
                               level=2)
                    ui.text(
                        tr('Written here so the list above does not read as '
                           'complete. None of these capabilities has the '
                           'slightest start in the code: geolocation, camera,'
                           ' network state, system notification, screen lock,'
                           ' IndexedDB. They all need a new pattern — a '
                           'PERMISSION and a WAIT — that a synchronous verb '
                           'cannot carry.',
                           'Écrit ici pour que la liste du dessus ne se lise '
                           "pas comme complète. Aucune de ces capacités n'a "
                           'la moindre amorce dans le code : géolocalisation,'
                           ' caméra, état réseau, notification système, '
                           "verrou d'écran, base IndexedDB. Elles demandent "
                           'toutes un patron neuf — une PERMISSION et une '
                           "ATTENTE — qu'un verbe synchrone ne peut pas "
                           'porter.'),
                        color="muted", size="sm",
                    )


# ── The examples, as real functions so `source_block` can read them ────
def exemple_verbes() -> None:
    ui.button(tr('Copy the key',
                 'Copier la clé'), on_click=bretzel.copy(state.api_key))
    ui.button("Imprimer", on_click=bretzel.print_page())
    ui.button(tr('Full screen',
                 'Plein écran'), on_click=bretzel.fullscreen(carte))
    ui.button(tr('Share this view',
                 'Partager cette vue'), on_click=bretzel.share())
    ui.button("Vibrer", on_click=bretzel.vibrate([50, 30, 50]))


def exemple_download() -> None:
    @download("/clients.csv")
    async def clients_csv() -> list[dict]:
        return await db.clients()

    # ⚠️ `download=True` is MANDATORY: without it, `hx-boost` swallows
    # the link and the CSV arrives as HTML in the outlet, with no sign at
    # all on the server side. The example omitted it although the
    # /capabilities page said so — two pages contradicting each other.
    ui.link(tr('Export the customers',
               'Exporter les clients'), href="/clients.csv", download=True)


def exemple_pwa() -> None:
    app = Bretzel(
        title="Tracker",
        secret_key=...,
        pwa=PWA(name="Tracker", icon="/static/logo.png",
                theme_color="#0f172a"),
    )
