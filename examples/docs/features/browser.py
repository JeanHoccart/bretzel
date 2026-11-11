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


@page(PATH, layout=shell, title="The browser · Bretzel docs",
      description="Reach the user's machine from Python: clipboard, printing, fullscreen, share sheet and vibration through Bretzel's browser verbs.")
def browser_page() -> None:
    with ui.container(width="xl"):
        with ui.vstack(gap="lg"):
            ui.heading('The browser', level=1, size="3xl")
            ui.text(
                'The server stays the source of truth, but some things '
                "exist only on the user's machine: their clipboard, their "
                'printer, their screen, their share sheet. Bretzel reaches'
                ' them in three ways, and each answers a different '
                'constraint.',
                color="muted",
            )

            # ── 1. Les verbes ────────────────────────────────────────
            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading('1. The verbs — an action, a string',
                               level=2)
                    ui.text(
                        'A verb produces JavaScript and plugs into an '
                        '`on_*=`. It costs almost nothing because the slot'
                        ' already existed: `on_<event>=` is polymorphic — '
                        'a callable leaves as a signed POST to the server,'
                        ' a STRING is evaluated in place, with no round '
                        "trip. It is `dialog.open()`'s contract; the verbs"
                        ' plug into it without adding a directive, a scope'
                        ' or a request.',
                        color="muted", size="sm",
                    )
                    for verbe in (bretzel.copy, bretzel.print_page,
                                  bretzel.fullscreen, bretzel.share,
                                  bretzel.vibrate):
                        callable_signature(verbe)

                    ui.heading('What they do, one line each',
                               level=3)
                    source_block(exemple_verbes)

                    piege(
                        'The clipboard demands a SECURE context',
                        '`navigator.clipboard` only exists over https:// '
                        'or localhost. Over http:// with a local-network '
                        'IP — the way an internal tool gets used — it is '
                        '`undefined`, and a bare call would do NOTHING, '
                        'without a word. Bretzel falls back to '
                        '`document.execCommand`, deprecated and the only '
                        'route that exists there.',
                    )
                    piege(
                        '`share` falls back to copying, and that is the '
                        'contract',
                        '`navigator.share` is absent from desktop Chromium'
                        ' (measured). Its absence is therefore not an edge'
                        ' case, it is the NORMAL case where one develops. '
                        'Rather than an inert “Share” button, the verb '
                        'copies the URL. A share CANCELLED by the user, on'
                        ' the other hand, does not fall back on it: '
                        'closing the sheet would copy behind their back.',
                    )
                    piege(
                        "No visual feedback on `copy`",
                        'That is the contract, not an oversight: the verb '
                        'copies, the app wires whatever feedback it wants.'
                        ' Nothing tells the user the click took.',
                    )

            # ── 2. @download ─────────────────────────────────────────
            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(
                        '2. @download — a routable that returns a file',
                        level=2,
                    )
                    ui.text(
                        'This is NOT an action, and the constraint is '
                        "structural: an action's response is swallowed by "
                        'the bridge and applied as a `<bz-patch>`, whereas'
                        ' a download must BE the file. So it is an '
                        'ordinary `ui.link(href=…)`, not an `on_click=`.',
                        color="muted", size="sm",
                    )
                    callable_signature(download)
                    source_block(exemple_download)

                    ui.heading("Four rendered forms", level=3)
                    ui.table(
                        rows=[
                            {"forme": "list[dict]",
                             "sortie": 'a CSV — headers derived from the '
                                       "first record's keys, UTF-8 BOM, "
                                       'RFC 4180 quoting'},
                            {"forme": "str", "sortie": 'the text as is'},
                            {"forme": "bytes",
                             "sortie": 'the bytes as they are — a PDF, an '
                                       'image, a zip'},
                            {"forme": "Response",
                             "sortie": 'the escape hatch, tested FIRST: '
                                       'everything the rest does not cover'},
                        ],
                        columns=[
                            ui.column("forme",
                                      label='what the function returns'),
                            ui.column("sortie",
                                      label='what the browser receives'),
                        ],
                    )

                    piege(
                        "It is NOT signed, unlike the datatable's export",
                        'And that is the difference that justifies the '
                        "routable. The datatable's link carries in its URL"
                        ' the NAME of the function to invoke, so it MUST '
                        'be signed — and it inherits being a bearer '
                        'capability, with no expiry. A `@download` fixes '
                        'its function at DECORATION time, like `@page`: '
                        'the URL decides nothing, and the route goes '
                        'through the same middleware. An app that protects'
                        ' its pages protects its downloads.',
                    )
                    piege(
                        '`ui.datatable(exportable=True)` is NOT wired to it',
                        'The two mechanisms coexist today, which principle'
                        ' 4 refuses — and that is written down rather than'
                        " hidden. The datatable's export needs the "
                        "READER's query (sort, filters at click time), "
                        'which does not exist in a static route. Rewiring '
                        'them means deciding how a VIEW travels as far as '
                        'a `@download`.',
                    )

            # ── 3. PWA ───────────────────────────────────────────────
            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("3. PWA — the app becomes installable",
                               level=2)
                    ui.text(
                        'The manifest describes the app to the system: its'
                        ' name, its icon, its colour, and the fact that it'
                        ' opens in its OWN window rather than in a tab. It'
                        ' is what gives an internal tool an icon in the '
                        'Start menu.',
                        color="muted", size="sm",
                    )
                    callable_signature(PWA)
                    source_block(exemple_pwa)

                    piege(
                        'It makes NOTHING available offline',
                        'Offline needs a service worker — a script '
                        'intercepting every request. It is not shipped, '
                        'deliberately: it is a whole lifecycle (versions, '
                        'invalidation, updating an app already installed '
                        "on somebody's machine), and a place where one "
                        'breaks an app in production while believing one '
                        'is improving it.',
                    )
                    piege(
                        'If the “Install” prompt does not appear, it is '
                        'not the manifest',
                        'Chrome long ALSO demanded a service worker before'
                        ' offering it. What Bretzel guarantees and what is'
                        ' measured: the manifest is served, valid, '
                        'correctly typed and linked — and it is Chromium '
                        'itself that says so (`Page.getAppManifest`, zero '
                        'errors).',
                    )

            with ui.card(color="surface"):
                with ui.vstack(gap="sm"):
                    ui.heading('What Bretzel can NOT do yet',
                               level=2)
                    ui.text(
                        'Written here so the list above does not read as '
                        'complete. None of these capabilities has the '
                        'slightest start in the code: geolocation, camera,'
                        ' network state, system notification, screen lock,'
                        ' IndexedDB. They all need a new pattern — a '
                        'PERMISSION and a WAIT — that a synchronous verb '
                        'cannot carry.',
                        color="muted", size="sm",
                    )


# ── The examples, as real functions so `source_block` can read them ────
def exemple_verbes() -> None:
    ui.button('Copy the key', on_click=bretzel.copy(state.api_key))
    ui.button("Print", on_click=bretzel.print_page())
    ui.button('Full screen', on_click=bretzel.fullscreen(carte))
    ui.button('Share this view', on_click=bretzel.share())
    ui.button("Vibrate", on_click=bretzel.vibrate([50, 30, 50]))


def exemple_download() -> None:
    @download("/clients.csv")
    async def clients_csv() -> list[dict]:
        return await db.clients()

    # Any component with an href: a @download route never navigates.
    ui.link('Export the customers', href="/clients.csv")


def exemple_pwa() -> None:
    app = Bretzel(
        title="Tracker",
        secret_key=...,
        pwa=PWA(name="Tracker", icon="/static/logo.png",
                theme_color="#0f172a"),
    )
