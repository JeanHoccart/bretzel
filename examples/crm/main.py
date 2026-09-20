"""CRM — the real-use instrument. ``py -m examples.crm.main``.

It is not an 18th demo: it is the app used to MEASURE the framework at
length. The brief, the "no working around it" rule and the findings
journal live in ``.claude/work/chantier-crm-2026-08-19.md``.

``main`` is the only file that knows the instance: it ``include``s the
features, seeds the database at startup, and lets the contract validate.
"""

from pathlib import Path

from bretzel import Bretzel, auth
from bretzel.runtime import is_public_asset_path
from bretzel.server import action_path, redirect_response
from examples.crm.core import db
from examples.crm.core.db import init_db
from examples.crm.core.domain import LOGIN_PATH
from examples.crm.core.texts import TEXTS
from examples.crm.core.theme import THEME
from examples.crm.features import (
    access,
    account_detail,
    accounts,
    accounts_data,
    activities,
    activities_data,
    analyse_nav,
    app_map,
    auth_data,
    contact_detail,
    contacts,
    contacts_data,
    deals_data,
    errors,
    geo,
    import_data,
    import_screen,
    login,
    nightly_hygiene,
    pipeline,
    realtime,
    reports,
    reports_data,
    search,
    search_data,
    settings,
    shell,
)

#: The app's assets, mounted on ``/static`` by ``static_dir=``.
#: An ABSOLUTE path derived from this file: a relative path would depend
#: on the folder one launches from, and ``Bretzel(static_dir=…)`` RAISES
#: at startup when it does not point at an existing folder.
STATIC_DIR = Path(__file__).resolve().parent / "static"

#: THIS app's icon — a funnel, not Bretzel's knot.
#:
#: It is ``favicon=``'s demonstration: by default a Bretzel app carries
#: the framework's mark, and one string is enough to set its own. The
#: file is served by ``static_dir``, so it is the app that answers for it
#: — the framework only announces it in the ``<head>``.
FAVICON_PATH = "/static/favicon.svg"

app = Bretzel(
    title="Bretzel · CRM",
    secret_key="dev-crm-secret-change-me",
    theme=THEME,
    static_dir=str(STATIC_DIR),
    favicon=FAVICON_PATH,
    # ``prod`` and not ``dev``: it is the only mode that shows the real
    # speed. In dev the CSS is compiled IN the browser by
    # ``@tailwindcss/browser`` and the runtime is served in its readable
    # version (286 kB instead of 97) — two choices made for the
    # development loop, not for display. In production: a compiled sheet
    # served in one ``<link>``, ``runtime.min.js``, and the three
    # third-party scripts vendored if they are in ``.bretzel/vendor/``.
    # Measured on 2026-08-27 on a minimal page, cold cache:
    # DOMContentLoaded at 110 ms against 644.
    #
    # ⚠️ Two trade-offs, both real: the first startup recompiles
    # ``.bretzel/style.css`` (a few seconds, the Tailwind binary required
    # in ``.bretzel/bin/``), and that cache is SHARED with the other
    # examples — alternating CRM and playground recompiles every time,
    # because their themes do not have the same fingerprint. Go back to
    # ``mode="dev"`` to get hot reloading again.
    mode="prod",
    # ── The language, declared ONCE ───────────────────────────────────
    # It sets ``<html lang="en">`` — a screen reader picks its voice from
    # it — and it names the months and the days of the four date
    # components. It was ``"fr"`` until 2026-09-20, and the switch is
    # what let the 19 strings each of those components was being passed
    # go: English is what they render with no help at all.
    lang="en",
    texts=TEXTS,
)


#: The paths reachable WITHOUT being signed in. Everything else is
#: closed — it is the meaning of a middleware guard, and the reason this
#: is not a ``@page(auth=…)``: a page added tomorrow is protected without
#: anybody thinking about it.
#: ⚠️ ``PUBLIC_ASSET_ROUTES`` comes from the FRAMEWORK, and that is the
#: point. These three paths were enumerated here by hand — plus a fourth
#: (``theme.js``) that nobody mounted, and which was removed from the
#: framework in consequence. Above all, one had to KNOW that
#: ``/_bretzel/refetch`` and ``/_bretzel/sse`` return page HTML and must
#: stay closed. That is base-layer knowledge inside app code: an internal
#: route added tomorrow broke this guard, or opened it, without anything
#: saying so. The classification belongs to whoever mounts the routes,
#: and it is gated (``test_framework_routes_are_classified``).
#: ⚠️ And it is ``is_public_asset_path`` that decides, NOT an equality on
#: ``PUBLIC_ASSET_ROUTES``: that set contains route PATTERNS.
#: ``/_bretzel/vendor/{filename}`` equals no real path, so equality
#: refused the three third-party scripts — and the browser received this
#: sign-in page instead of a ``<script>``. The exact symptom, measured on
#: 2026-08-27: three ``Unexpected token '<'`` in the console, the page
#: rendered at 100 nodes instead of 1 700, no server error.
#: ⚠️ **The app's icon is part of it, and that is not intuitive.**
#: ``is_public_asset_path`` only knows the FRAMEWORK's assets — that is
#: its definition. An icon set by ``favicon=`` lives at the app, on
#: ``/static``, so the guard refuses it like any page: the sign-in asks
#: for its icon before anybody is signed in, and gets a 302 to itself.
#: Symptom: no icon on the sign-in screen, only one, and nothing in the
#: logs. It is the price of setting one's own mark, and it is paid here,
#: on one line.
PUBLIC_PATHS: frozenset[str] = frozenset({LOGIN_PATH, FAVICON_PATH})

#: The sign-in action, and it alone — named by the FUNCTION.
#:
#: ⚠️ It used to be a module prefix (``…/examples.crm.features.login::``).
#: The base layer's resolver works by ``getattr`` on the module, so that
#: prefix nominally opened everything ``login.py`` imports —
#: ``auth.login``, ``redirect``, the component factory. The HMAC
#: signature stayed the real barrier, but the guard's scope grew with a
#: file's import list, in silence.
#:
#: ⚠️ Opening ``/_bretzel/action/`` entirely would be shorter and WRONG:
#: the ``@refreshable`` zones re-render through ``/_bretzel/refetch/…``
#: and real time through ``/_bretzel/sse`` — two routes that return page
#: HTML. Leaving them out is letting twelve screens render for an
#: anonymous visitor.
#:
#: ``sign_out`` is NOT there: one only signs out when signed in.
#: ⚠️ The path could be ASKED of the framework since 2026-08-24
#: (``action_path``): it was recomposed here by hand, with the wire-id
#: separator, and ``examples/auth`` was about to copy it.
PUBLIC_ACTIONS: frozenset[str] = frozenset(
    action_path(fn) for fn in (login.sign_in,)
)


@app.middleware
async def require_login(request, call_next):
    """The guard. Written FIRST, so the outermost.

    ``auth.user_id`` and not ``auth.is_authenticated``: at this level
    neither the render context nor ``request.state.user`` exists yet.
    Until 2026-08-23 this example read the cookie itself and had to
    receive ``app.config._auth_key`` — the private attribute — from here.

    ``redirect_response`` and not ``redirect``: the first decides between
    a real 302 (navigation) and an ``HX-Redirect`` (bridge action), the
    second raises outside a render context.
    """
    path = request.url.path
    if (path in PUBLIC_PATHS
            or is_public_asset_path(path)
            or path in PUBLIC_ACTIONS
            or auth.user_id(request)):
        return await call_next(request)
    return redirect_response(request, LOGIN_PATH)


@app.startup
async def seed_db() -> None:
    # Idempotent: only re-seeds if ``SEED_VERSION`` has moved. ~4 s the
    # first time for 262 000 rows, zero afterwards.
    init_db()


app.include(
    db,                          # infra
    shell,                       # shell
    analyse_nav,                 # layout (shell ▸ analyse_nav ▸ pages)
    access,                      # logic (the access policy)
    geo,                         # facade (the geocoder, an external service)
    nightly_hygiene,             # job (aucune route, aucun rendu)
    auth_data,                                  # data
    accounts_data, contacts_data, deals_data,
    activities_data, reports_data, search_data, import_data,
    login,                                      # pages
    pipeline, accounts, account_detail,
    contacts, contact_detail, activities, reports, search,
    import_screen, settings, realtime,
    errors,                                     # error
    app_map,                                    # meta (carte)
)


if __name__ == "__main__":
    app.run(port=8016, reload=True)
