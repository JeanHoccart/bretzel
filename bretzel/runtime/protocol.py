"""Wire-format constants — the **only** place these strings are defined.

Every other module that needs a ``bz-*`` attribute name, an HTTP header
name, or a framework route imports it from here. The strict rule
(``.claude/bretzel/runtime.md`` §*Purpose*) : no other Bretzel module
hardcodes these strings.

Bumping any constant here is a wire-format change and must be paired
with a bump in :data:`PROTOCOL_VERSION`.

Client state travels as namespaced form-data in the request body. Actions
use native ``hx-post`` attributes; client-only events use ``BZ_ON_PREFIX``.
"""

from __future__ import annotations

from typing import Final

# ───────────────────────────────────────────────────────────────────────────
# Protocol version (semver — major bump = incompatible wire change)
# ───────────────────────────────────────────────────────────────────────────

PROTOCOL_VERSION: Final[str] = "v1.0"


# ───────────────────────────────────────────────────────────────────────────
# bz-* attributes consumed by the runtime
# ───────────────────────────────────────────────────────────────────────────

# Metadata stamps (read by the runtime, not directives). ``bz-id`` is
# load-bearing in V3 : it keys the ``bz-data`` scope store, so scope
# state survives idiomorph swaps.
BZ_ID_ATTR: Final[str] = "bz-id"
BZ_STATE_ATTR: Final[str] = "bz-state"

# Directive prefixes — the 13 directives the runtime evaluates.
# Grammar and edge cases : .claude/bretzel/runtime.md §"_src/02_directives.js".
BZ_ON_PREFIX: Final[str] = "bz-on:"          # event handler (client-only)
BZ_MODEL_PREFIX: Final[str] = "bz-model"     # two-way binding on form inputs
BZ_ATTR_PREFIX: Final[str] = "bz-attr:"      # generic one-way attribute bind
BZ_CLASS_PREFIX: Final[str] = "bz-class"     # class object/array bind
BZ_TEXT_PREFIX: Final[str] = "bz-text"       # textContent (display-only)
BZ_SHOW_PREFIX: Final[str] = "bz-show"       # display:none toggle (stays mounted)
BZ_IF_PREFIX: Final[str] = "bz-if"           # mount/unmount conditional
BZ_FOR_PREFIX: Final[str] = "bz-for"         # keyed client-side iteration
BZ_DATA_PREFIX: Final[str] = "bz-data"       # component-local scope declaration
BZ_INIT_PREFIX: Final[str] = "bz-init"       # one-shot on-mount hook
BZ_EFFECT_PREFIX: Final[str] = "bz-effect"   # continuous reactive effect
BZ_REF_PREFIX: Final[str] = "bz-ref"         # named DOM reference
BZ_TELEPORT_PREFIX: Final[str] = "bz-teleport"  # render at another DOM location

# HMAC action stamps (read by the bridge, forwarded as headers).
DATA_BZ_SIG: Final[str] = "data-bz-sig"
DATA_BZ_TS: Final[str] = "data-bz-ts"      # render timestamp, signed into the HMAC (v2)

# ``bz-data`` scope marker read by the runtime scope engine
# (``_src/03_scope.js``), not a directive. ``_serverSync`` lists the scope
# keys a ``@refreshable`` morph must re-adopt from the freshly-rendered
# ``bz-data`` (server wins), vs the client-owned keys ``absorb`` preserves.
# Emitted by value-holding controls via
# ``components/base/_wiring.server_sync_marker`` ; mirrored verbatim in the
# JS scope reader (guarded by ``tests/consistency/test_python_js_mirror.py``).
SERVERSYNC_KEY: Final[str] = "_serverSync"


# ───────────────────────────────────────────────────────────────────────────
# HTTP headers carrying runtime / transport state
# ───────────────────────────────────────────────────────────────────────────

HEADER_PROTOCOL: Final[str] = "X-Bretzel-Protocol"  # client → server
HEADER_BZ_SIG: Final[str] = "X-Bz-Sig"              # HMAC sig (V3 wire)
HEADER_BZ_TS: Final[str] = "X-Bz-Ts"                # render timestamp signed into the HMAC (v2)
HEADER_PAGE_ID: Final[str] = "X-Bretzel-Page-ID"    # page identity
HEADER_CSRF: Final[str] = "X-Bretzel-CSRF"          # CSRF token

#: The ``@refreshable`` zones the BROWSER actually has in front of it,
#: in clear text, comma-separated. Sent on action POSTs only.
#:
#: Without it, ``enqueue_deps`` queues EVERY zone declared on a changed
#: state class, including those living on other pages: the server
#: renders them, serialises them, compresses them, sends them — and the
#: browser throws them away for want of a target. Measured on 2026-09-05
#: on ``examples/mad``: an action from ``/patients`` rendered the
#: dashboard's zone for nothing, **8.4 ms** against 9.6 ms for the useful
#: zone, so nearly half the drain. On ``examples/crm``, ``ViewerPrefs``
#: drags 14 zones across 8 modules for 4 at most per page.
#:
#: ⚠️ An ABSENT header means "I do not know", not "no zone": the server
#: then filters nothing. That is what makes the setting safe — a cached
#: runtime, a third-party client or a test POSTing by hand falls back on
#: the old behaviour, never on a zone that silently stops refreshing.
#: The TAB identity, drawn once per page load.
#:
#: It serves one thing only, and it is a saving: excluding the tab that
#: has just acted from its OWN broadcast. It already received its zones
#: in its action's response; asking for them again through the real-time
#: stream is one round trip per zone, for an identical render.
#:
#: Measured on ``examples/kanban`` before the exclusion: ticking a
#: subtask cost **five requests and 354 KB** — the action (177 KB) plus
#: four re-reads returning exactly what the first had just delivered.
#:
#: ⚠️ Exclude the tab, not the SESSION. Two tabs of the same person must
#: keep seeing each other: that is the very use case of a shared board
#: opened twice to compare.
HEADER_TAB: Final[str] = "X-Bretzel-Tab"

#: The same identifier, carried by the stream's URL — an ``EventSource``
#: cannot set a header.
SSE_TAB_PARAM: Final[str] = "tab"

HEADER_ZONES: Final[str] = "X-Bretzel-Zones"

#: **Response → client**: the fingerprint of every zone this response
#: has just shipped, as comma-separated ``id:fingerprint``. The runtime
#: keeps it and sends it back in :data:`HEADER_ZONES` on the next
#: request; the server can then STAY SILENT about a zone whose fresh
#: render is identical to the one the browser already carries.
#:
#: Measured on ``examples/messagerie``: toggling a read flag shipped
#: 93 075 bytes for 115 actually changed — two zones out of three came
#: back byte for byte identical.
#:
#: The server STORES nothing: it is the client that carries the
#: fingerprint of what it displays. A stale or absent fingerprint can
#: therefore only cause a zone to be re-shipped — never wrongly
#: silenced.
HEADER_ZONE_HASHES: Final[str] = "X-Bretzel-Zone-Hashes"


# ───────────────────────────────────────────────────────────────────────────
# Framework-served routes (mounted under ``/_bretzel`` by the server layer)
# ───────────────────────────────────────────────────────────────────────────

ROUTE_PREFIX: Final[str] = "/_bretzel"
ROUTE_RUNTIME_JS: Final[str] = f"{ROUTE_PREFIX}/runtime.js"
ROUTE_THEME_CSS: Final[str] = f"{ROUTE_PREFIX}/theme.css"
ROUTE_STYLE_CSS: Final[str] = f"{ROUTE_PREFIX}/style.css"
# The third-party scripts brought in-house under ``./.bretzel/vendor/``
# — htmx, idiomorph, iconify. Served from here rather than from three
# CDNs: a page's ``DOMContentLoaded`` goes from 644 to 110 ms (measured
# on 2026-08-27). Cf. ``bretzel/render/vendor.py``.
ROUTE_VENDOR: Final[str] = f"{ROUTE_PREFIX}/vendor"
# The icon DATA, relayed and cached. The iconify web component fetches
# its glyphs from three third-party hosts (``api.iconify.design`` and two
# fallbacks): measured on 2026-09-13, with all three cut off it renders
# **0 glyphs out of 25**. Bringing the component in-house does not bring
# its glyphs in-house — that is a second dependency, in the same page,
# and it outlives the other one.
ROUTE_ICONS: Final[str] = f"{ROUTE_PREFIX}/icons"
# The framework's mark, served by default when an app sets no
# ``favicon=``. Two files and not one more: the SVG follows
# ``prefers-color-scheme``, the PNG exists because iOS does not read the
# SVG for its home screen. Cf. ``bretzel/static/``.
ROUTE_FAVICON: Final[str] = f"{ROUTE_PREFIX}/favicon.svg"
ROUTE_TOUCH_ICON: Final[str] = f"{ROUTE_PREFIX}/apple-touch-icon.png"
ROUTE_ACTION: Final[str] = f"{ROUTE_PREFIX}/action"
ROUTE_SSE: Final[str] = f"{ROUTE_PREFIX}/sse"
# The user assets (``Bretzel(static_dir=…)``) — OUTSIDE the
# ``/_bretzel`` prefix, which is reserved for the framework: that path
# appears in the URLs the app writes itself.
ROUTE_STATIC_DIR: Final[str] = "/static"
# NOT a live channel — a standard HTTP GET hit by the runtime AFTER an
# SSE state-dirty event, to fetch the updated HTML of a subscribing
# zone. The SSE stream is the only long-lived connection.
ROUTE_REFETCH: Final[str] = f"{ROUTE_PREFIX}/refetch"

#: The framework routes an auth guard may leave OPEN.
#:
#: They carry no app data: the runtime, the sheet generated from the
#: theme, the compiled sheet, and the three third-party scripts brought
#: in-house. A login page needs them **before** anyone is signed in —
#: without them it renders unstyled, its form does not POST, and without
#: htmx it no longer even has a bridge.
#:
#: ⚠️ **All the rest of ``/_bretzel`` stays CLOSED**, and that is not
#: intuitive: ``/_bretzel/refetch/…`` re-renders a zone,
#: ``/_bretzel/sse`` pushes renders, ``/_bretzel/action/…`` runs app code
#: and ``/_bretzel/datatable.csv`` exports rows. Opening them means
#: letting a whole app render for an anonymous visitor.
#:
#: **Why this constant exists.** The first example to write a guard
#: (``examples/crm``, 2026-08-20) had to enumerate those three paths by
#: hand AND reason about the four others. That is framework knowledge
#: inside app code: the day an internal route is added, every guard
#: breaks or opens **silently**. The classification therefore belongs to
#: whoever mounts the routes.
#:
#: Gated by ``tests/consistency/test_framework_routes_are_classified.py``,
#: which reads the routes ACTUALLY mounted and requires each to be on one
#: side or the other.
PUBLIC_ASSET_ROUTES: Final[frozenset[str]] = frozenset({
    ROUTE_RUNTIME_JS,
    ROUTE_THEME_CSS,
    ROUTE_STYLE_CSS,
    # A path pattern, not a URL: the route is mounted with a parameter.
    # ⚠️ A guard therefore CANNOT compare a received path to this set —
    # it needs :func:`is_public_asset_path`.
    f"{ROUTE_VENDOR}/{{filename}}",
    # Same reason, same shape: a login page's glyphs are requested
    # before anyone is signed in.
    f"{ROUTE_ICONS}/{{icon_path:path}}",
    # The icon, for the same reason as the sheets: a login page
    # requests it BEFORE anyone is signed in. Closed, it would return
    # the login page (200, HTML) where the browser expects an image —
    # so no icon, and nothing in the logs.
    ROUTE_FAVICON,
    ROUTE_TOUCH_ICON,
})


def is_public_asset_path(path: str) -> bool:
    """Return whether ``path`` names a public framework asset."""
    for route in PUBLIC_ASSET_ROUTES:
        if "{" not in route:
            if path == route:
                return True
            continue
        prefix = route[: route.index("{")]
        if path.startswith(prefix):
            rest = path[len(prefix):]
            if rest and "/" not in rest:
                return True
    return False


# ───────────────────────────────────────────────────────────────────────────
# Wire-id separator
# ───────────────────────────────────────────────────────────────────────────

# Joins ``<module>`` + ``<qualname>`` into the addressable id that rides on
# ``ROUTE_ACTION`` (action handlers) and the refetch/realtime routes
# (refreshable zones + State ``deps``). Built by
# ``server.handlers.encode_action_id``,
# ``components.base.events.encode_handler_id`` and
# ``render.decorators.refreshable`` (zones + ``state_qualname``), split back
# by ``server.handlers.resolve_handler`` — the DAG forbids those sites
# sharing one function (``components`` < ``server``), so at least the
# separator has one source. Equivalence of the two encoders is guarded by
# ``tests/consistency/test_wire_id.py``.
WIRE_ID_SEP: Final[str] = "::"


# ───────────────────────────────────────────────────────────────────────────
# Realtime wire format (SSE notification + zone refetch)
# ───────────────────────────────────────────────────────────────────────────

SSE_EVENT_STATE_DIRTY: Final[str] = "state-dirty"
DATA_SUBSCRIBE_STATE: Final[str] = "data-bz-subscribe-state"
DATA_SUBSCRIBE_URL: Final[str] = "data-bz-subscribe-url"

#: The marker a ``@refreshable`` zone sets on its element, carrying its
#: own identifier. It exists so the runtime can enumerate the document's
#: zones without guessing: the identifier comes from ``_stable_id`` and
#: starts with ``refresh_``, but that prefix is a Python convention —
#: reading it in JS would make a mirror that drifts at the first rename.
#: Feeds :data:`HEADER_ZONES`.
DATA_ZONE: Final[str] = "data-bz-zone"

# Viewport cookie — a client→server wire string, so it lives here (single
# source, per this module's rule). Written pre-paint by the boot script
# (``render/shell.py`` interpolates this name into the JS) and read at render
# by ``render/screen.py``. Value format ``"{mobile},{touch}"`` (``1``/``0``).
# Cf. ``.claude/bretzel/screen-responsive-nav.md``.
SCREEN_COOKIE: Final[str] = "bz_screen"

# The LANGUAGE cookie. It wins over ``Accept-Language`` — the header
# describes the OS configuration, not a reading choice, so without this
# cookie a visitor on an English system who wants to read in French would
# have no way to say so. Set by ``Language.set()``, read by the render
# context middleware. Same role as ``bz_screen`` just above: the browser
# knows, the cookie carries, the server renders from a real value.
LANG_COOKIE: Final[str] = "bz_lang"

# Global the pre-paint sync script defines (``render/shell.py``) and the runtime
# calls by name (``_src/05_bridge.js``, before a boosted nav). Not a wire string
# in the HTTP sense, but the same problem this module exists for : one name, two
# languages, no compiler to catch a rename. Substituted into the bundle as
# ``__SCREEN_SYNC_FN__`` by ``_build.py`` and mirrored by
# ``tests/consistency/test_python_js_mirror.py``.
# ⚠️ The *reader* is what earns a constant its place here. The sibling
# ``sessionStorage`` key of the reload flag stays local to ``shell.py`` — no JS
# reads it, so promoting it would be cargo-cult.
SCREEN_SYNC_FN: Final[str] = "$bzScreenSync"


# ───────────────────────────────────────────────────────────────────────────
# Envelope tag names (V3 — replaces V2's <script id="bz-envelope"/"bz-delta">)
# ───────────────────────────────────────────────────────────────────────────

ENVELOPE_TAG_NAME: Final[str] = "bz-envelope"  # bootstrap (initial page load)
PATCH_TAG_NAME: Final[str] = "bz-patch"        # delta patches (per response)

# Permanent sink element id — actions target it (``hx-target``) so the
# non-OOB response body (where <bz-patch> rides) lands in the DOM
# instead of being discarded by ``hx-swap="none"``. Phase 0 learning ;
# V2 precedent : ``#bz-script-outbox``.
SINK_ELEMENT_ID: Final[str] = "bz-sink"

# RESERVED key of the ``$bz.pending`` registry: "a NAVIGATION is in
# flight". The bridge arms it in addition to the triggering element when
# the request is boosted or carries ``hx-push-url``, and the shell bar
# (``render/shell.nav_progress_html``) is nothing but a ``bz-show`` on
# it.
#
# The leading ``@`` puts the key out of reach of an ``action_id``, which
# is always ``module::qualname``. It is here and not in the shell because
# both sides of the wire name it — Python writes it into the attribute,
# JS arms it (``__NAV_PENDING_KEY__``, substituted at build time like the
# envelope and patch tags).
NAV_PENDING_KEY: Final[str] = "@nav"


# ───────────────────────────────────────────────────────────────────────────
# Outlet convention helper
# ───────────────────────────────────────────────────────────────────────────


def outlet_id_for(layout_name: str) -> str:
    """Return the ``<main>`` id for ``layout_name``'s outlet.

    Single source of truth for the ``<main id="outlet_<layout>">``
    naming Bretzel emits from layouts and references in partial-nav
    targets. Placed here (wire-format module) so components / render /
    server all consume the same helper without crossing the import DAG.
    """
    return f"outlet_{layout_name}"
