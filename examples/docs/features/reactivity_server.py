"""REACTIVITY — Server reactivity.

The server side of reactivity: what re-renders after an action. A zone
declares the states it reads; mutating one of them re-renders it
automatically. Plus the manual trigger (`refresh`) and real time
(`broadcast=[…]` / SSE). API checked in
``render/decorators/refreshable.py`` (only ``refreshable`` and
``refresh`` are exported).
"""

from bretzel import page, ui
from examples.docs.features.shell import shell
from examples.docs.lib.i18n import tr


@page("/reactivity-server", layout=shell, title=tr('Server reactivity',
                                                   'Réactivité serveur'))
def reactivity_server_page() -> None:
    with ui.container(width="xl"), ui.vstack(gap="lg"):
        ui.heading(tr('Server reactivity',
                      'Réactivité serveur'), level=1, size="3xl")
        with ui.hstack(align="baseline", gap="sm", wrap=True):
            ui.text(
                tr('Once a handler has changed the state (cf.',
                   "Une fois qu'un handler a modifié l'état (cf."),
                color="muted", size="lg",
            )
            ui.link("Actions serveur", href="/actions-server")
            ui.text(tr('), here is what re-renders on screen, and how to '
                       'control it.',
                       "), voici ce qui se re-rend à l'écran, et comment le "
                       'contrôler.'), color="muted", size="lg")

        # ── @refreshable(deps=) ──────────────────────────────────
        with ui.card(), ui.vstack(gap="sm"):
            ui.heading(tr('The automatic re-render',
                          'Le re-render automatique'), level=2)
            ui.text(
                tr('A `@refreshable(deps=[…])` zone declares the states it '
                   'reads. When a handler mutates one of them, the zone is '
                   're-rendered automatically — no refresh to call.',
                   'Une zone `@refreshable(deps=[…])` déclare les états '
                   "qu'elle lit. Quand un handler mute l'un d'eux, la zone "
                   'est re-rendue automatiquement — pas de refresh à appeler.'),
                color="muted", size="sm",
            )
            ui.code(
                tr('@refreshable(deps=[Cart])\ndef cart_summary() -> None:\n    ui.text(f"{len(Cart().items)} items")\n\n\ndef add_to_cart(product_id: str) -> None:\n    Cart().items.append(product_id)\n    # cart_summary re-renders: Cart is in its deps\n',
                   '@refreshable(deps=[Cart])\ndef cart_summary() -> None:\n    ui.text(f"{len(Cart().items)} articles")\n\n\ndef add_to_cart(product_id: str) -> None:\n    Cart().items.append(product_id)\n    # cart_summary se re-rend : Cart est dans ses deps\n'),
                lang="python",
            )

        # ── Mutation = re-render ─────────────────────────────────
        with ui.card(), ui.vstack(gap="sm"):
            ui.heading("Mutation = re-render", level=2)
            ui.text(
                tr('At the end of an action, the server compares the state '
                   'before and after — including in-place modifications '
                   '(`items.append(...)`, `d[k] = v`). Every zone whose '
                   '`deps=` changed is re-rendered and sent back to the '
                   'browser.',
                   "En fin d'action, le serveur compare l'état avant / après "
                   '— y compris les modifications en place '
                   '(`items.append(...)`, `d[k] = v`). Toute zone dont un '
                   '`deps=` a changé est re-rendue et renvoyée au navigateur.'),
                color="muted", size="sm",
            )
            ui.text(
                tr('Conversely, if a handler changes no state declared in a '
                   '`deps=`, no zone is re-rendered — the round trip brings '
                   'back nothing to refresh.',
                   "À l'inverse, si un handler ne change aucun état déclaré "
                   "dans un `deps=`, aucune zone n'est re-rendue — l'aller-"
                   'retour ne renvoie rien à rafraîchir.'),
                color="muted", size="sm",
            )

        # ── refresh() ────────────────────────────────────────────
        with ui.card(), ui.vstack(gap="sm"):
            ui.heading(tr('Triggering by hand — refresh()',
                          'Déclencher manuellement — refresh()'), level=2)
            ui.text(
                tr("`refresh(zone)` forces a zone's re-render. Useful when "
                   'the change does not come from a declared state, or from '
                   'somewhere that is not an action handler. It can also be '
                   'addressed by its `name`.',
                   "`refresh(zone)` force le re-render d'une zone. Utile "
                   "quand le changement ne vient pas d'un état déclaré, ou "
                   "depuis un endroit qui n'est pas un handler d'action. On "
                   "peut aussi l'adresser par son `name`."),
                color="muted", size="sm",
            )
            ui.code(
                tr('from bretzel import refresh\n\ndef reload_prices() -> None:\n    fetch_latest()\n    refresh(price_table)          # by the zone\n    # or: refresh("price_table")  # by its name=\n',
                   'from bretzel import refresh\n\ndef reload_prices() -> None:\n    fetch_latest()\n    refresh(price_table)          # par la zone\n    # ou : refresh("price_table")  # par son name=\n'),
                lang="python",
            )

        # ── broadcast ────────────────────────────────────────────
        with ui.card(), ui.vstack(gap="sm"):
            ui.heading(tr('Realtime between clients — broadcast',
                          'Temps réel entre clients — broadcast'), level=2)
            ui.text(
                tr('`deps` and `broadcast` are two ORTHOGONAL lists, and the '
                   'question they ask is the same: who changes this state?',
                   '`deps` et `broadcast` sont deux listes ORTHOGONALES, et '
                   "la question qu'elles posent est la même : qui change cet "
                   'état ?'),
                color="muted", size="sm",
            )
            with ui.vstack(gap="xs", classes="pl-4"):
                ui.text(
                    tr('• ME → `deps`. The zone is re-rendered in the '
                       "action's response: one round trip, one swap.",
                       '• MOI → `deps`. La zone est re-rendue dans la réponse'
                       " de l'action : un aller-retour, un swap."),
                    color="muted", size="sm",
                )
                ui.text(
                    tr('• THE OTHERS → `broadcast`. An SSE signal, then a '
                       'refetch: two round trips, but the tab that did '
                       'nothing follows.',
                       '• LES AUTRES → `broadcast`. Un signal SSE, puis un '
                       "refetch : deux allers-retours, mais l'onglet qui n'a "
                       'rien fait suit.'),
                    color="muted", size="sm",
                )
                ui.text(
                    tr('• BOTH → both lists. It is not a redundancy: it says '
                       '“instant for me, pushed to the others”.',
                       "• LES DEUX → les deux listes. Ce n'est pas une "
                       'redondance : ça dit « instantané pour moi, poussé aux'
                       ' autres ».'),
                    color="muted", size="sm",
                )
            ui.code(
                tr('@refreshable(deps=[Cart])                     # local\n@refreshable(broadcast=[Queue])               # I never\n                                              # change it\n@refreshable(deps=[Presence], broadcast=[Presence],\n             name="online_users")             # both\n',
                   '@refreshable(deps=[Cart])                     # local\n@refreshable(broadcast=[FileAttente])         # je ne le\n                                              # change jamais\n@refreshable(deps=[Presence], broadcast=[Presence],\n             name="online_users")             # les deux\n'),
                lang="python",
            )
            ui.text(
                tr('What crosses is only a SIGNAL: every client refetches in '
                   'its own context, no data passes from one client to '
                   'another. `name=` gives a stable address for '
                   '`refresh("…")`.',
                   "Ce qui traverse n'est qu'un SIGNAL : chaque client "
                   'refetch dans son propre contexte, aucune donnée ne passe '
                   "d'un client à l'autre. `name=` donne une adresse stable "
                   'pour `refresh("…")`.'),
                color="muted", size="xs",
            )

        # ── Boundary ─────────────────────────────────────────────
        with ui.card(color="surface"), ui.vstack(gap="xs"):
            ui.heading("Et ensuite", level=3)
            with ui.hstack(align="baseline", gap="sm", wrap=True):
                ui.text(
                    tr('The reactivity that lives in the browser, with no '
                       'round trip:',
                       'La réactivité qui vit dans le navigateur, sans aller-'
                       'retour :'),
                    color="muted", size="sm",
                )
                ui.link(tr('Client reactivity →',
                           'Réactivité client →'), href="/reactivity-client")
