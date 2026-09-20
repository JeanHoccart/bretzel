"""REFERENCE — The client runtime.

What the browser runs once the page has arrived: a signal engine, the
`bz-*` directives, and a bridge that owns the transport boundary. A
reference chapter: one does not write these directives by hand in a
Bretzel app — the components emit them. One comes to read it when
stepping outside the frame, or to know what is running.

Every table is introspected from `bretzel/runtime/`: the vocabulary
declared on the Python side, checked against what the JS really wires. No
count is written into this page.
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
from examples.docs.lib.i18n import tr

PATH = "/runtime"


@page(PATH, layout=shell, title=tr('The client runtime',
                                   'Le runtime client'))
def runtime_page() -> None:
    with ui.container(width="xl"):
        with ui.vstack(gap="lg"):
            ui.heading(tr('The client runtime',
                          'Le runtime client'), level=1, size="3xl")
            ui.text(
                tr('The server stays the source of truth, but something runs '
                   'in the browser: a home-made engine, with no npm and no '
                   'third-party reactive framework. This page says what it '
                   'guarantees, then enumerates its vocabulary.',
                   'Le serveur reste la source de vérité, mais quelque chose '
                   'tourne dans le navigateur : un moteur maison, sans npm et'
                   " sans framework réactif tiers. Cette page dit ce qu'il "
                   'garantit, puis énumère son vocabulaire.'),
                color="muted", size="lg",
            )

            with section(
                tr('You do not write this',
                   "Tu n'écris pas ça"),
                tr('In a Bretzel app, the `bz-*` directives are emitted by '
                   'the components: passing `visible=binding` produces a `bz-'
                   'show`, `value=binding` produces a `bz-model`. This page '
                   'is the emergency exit — what one reads to understand what'
                   ' was emitted, or to write by hand the case the components'
                   ' do not cover.',
                   'Dans une app Bretzel, les directives `bz-*` sont émises '
                   'par les composants : passer `visible=binding` produit un '
                   '`bz-show`, `value=binding` produit un `bz-model`. Cette '
                   "page est la sortie de secours — ce qu'on lit pour "
                   'comprendre ce qui a été émis, ou pour écrire à la main le'
                   ' cas que les composants ne couvrent pas.'),
            ):
                pass

            with section(
                tr('The three guarantees',
                   'Les trois garanties'),
                tr('A client runtime is judged on what it promises when the '
                   'server rewrites the page under its feet.',
                   "Un runtime client se juge sur ce qu'il promet quand le "
                   'serveur réécrit la page sous ses pieds.'),
            ):
                ui.table(
                    columns=[
                        ui.column("g", label="Garantie"),
                        ui.column("m", label=tr('The mechanism',
                                                'Le mécanisme')),
                    ],
                    rows=[
                        {
                            "g": tr('A client state survives a server refresh',
                                    'Un état client survit à un refresh '
                                    'serveur'),
                            "m": tr('Every scope is keyed by bz-id. After a '
                                    'morph, the subtree is re-scanned: the '
                                    'bindings are thrown away then rewired, '
                                    'and the effects restore what the morph '
                                    'overwrote (text, display, value, '
                                    'classes).',
                                    'Chaque scope est keyé par bz-id. Après '
                                    'un morph, le sous-arbre est re-scanné : '
                                    'les bindings sont jetés puis recâblés, '
                                    'et les effets restaurent ce que le morph'
                                    ' a écrasé (texte, display, valeur, '
                                    'classes).'),
                        },
                        {
                            "g": tr('No round trip just to display something',
                                    "Aucun aller-retour pour de l'affichage"),
                            "m": tr('A client binding compiles into a JS '
                                    'expression evaluated in the browser. '
                                    'Showing, hiding, computing a class: '
                                    'nothing goes over the network.',
                                    'Un binding client compile en expression '
                                    'JS évaluée dans le navigateur. Afficher,'
                                    ' masquer, calculer une classe : rien ne '
                                    'part sur le réseau.'),
                        },
                        {
                            "g": tr("The transport boundary is the runtime's",
                                    'La frontière transport est au runtime'),
                            "m": tr('A component never POSTs. It declares a '
                                    'handler; the bridge adds the HMAC '
                                    'signature, the CSRF token, the protocol '
                                    'headers and the client-state snapshot.',
                                    'Un composant ne POSTe jamais. Il déclare'
                                    ' un handler ; le pont ajoute la '
                                    'signature HMAC, le jeton CSRF, les en-'
                                    "têtes de protocole et l'instantané "
                                    "d'état client."),
                        },
                    ],
                    size="sm",
                )

            with section(
                tr('What the runtime weighs',
                   'Ce que pèse le runtime'),
                tr('The bundle is concatenated from `_src/*.js`, with no '
                   'bundler and no minifier — the file served is the one you '
                   'debug. The numeric prefix IS the load order.',
                   'Le bundle est concaténé depuis `_src/*.js`, sans bundler '
                   "ni minifieur — le fichier servi est celui qu'on débogue. "
                   "Le préfixe numérique EST l'ordre de chargement."),
            ):
                runtime_modules_mirror()

            with section(
                tr('The directives',
                   'Les directives'),
                tr('Grouped by what they guarantee. The vocabulary has two '
                   'halves — a Python constant declares it, a JS module wires'
                   ' it — and the runtime cannot import Python. A gate '
                   'already checks that at commit time '
                   '(test_python_js_mirror.py); this table shows it, one '
                   'notch stricter: comments stripped, and per source module.',
                   "Groupées par ce qu'elles garantissent. Le vocabulaire a "
                   'deux moitiés — une constante Python le déclare, un module'
                   ' JS le branche — et le runtime ne peut pas importer '
                   'Python. Une gate le vérifie déjà au commit '
                   '(test_python_js_mirror.py) ; cette table le montre, un '
                   'cran plus strict : commentaires ôtés, et par module '
                   'source.'),
            ):
                directives_mirror()

            with section(
                tr('Inside an expression',
                   'Dans une expression'),
                tr('A directive expression is compiled once then cached. The '
                   'current scope is on the scope chain — a bare name reads '
                   'the scope — and a few variables are injected.',
                   'Une expression de directive est compilée une fois puis '
                   'mise en cache. Le scope courant est sur la chaîne de '
                   'portée — un nom nu lit le scope — et quelques variables '
                   'sont injectées.'),
            ):
                magics_mirror()
                ui.code(
                    "{ open: false, pick(v) { this.open = false; } }",
                    lang="js",
                )
                ui.text(
                    tr('The trap: the rebinding of bare names holds for '
                       "inline expressions, not for a scope's methods. Inside"
                       ' a method it is `this.field` — without the `this`, '
                       'you create a global.',
                       'Le piège : le rebind des noms nus vaut pour les '
                       "expressions inline, pas pour les méthodes d'un scope."
                       " Dans une méthode, c'est `this.champ` — sans le "
                       '`this`, on crée une globale.'),
                    color="muted", size="sm",
                )

            with section(
                tr('The $bz surface',
                   'La surface $bz'),
                tr('The global object, read module by module. The scope '
                   'factories are what a component spreads into its `bz-'
                   'data`; the rest is the engine. The “exposes” column is '
                   'read from the JS literal, never copied by hand.',
                   "L'objet global, lu module par module. Les fabriques de "
                   "scope sont ce qu'un composant spread dans son `bz-data` ;"
                   ' le reste est le moteur. La colonne « expose » est lue '
                   'dans le littéral JS, jamais recopiée.'),
            ):
                runtime_api_mirror()
