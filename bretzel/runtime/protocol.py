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

#: Les zones ``@refreshable`` que le NAVIGATEUR a réellement sous les
#: yeux, en clair, séparées par des virgules. Envoyé sur les POST
#: d'action uniquement.
#:
#: Sans lui, ``enqueue_deps`` enfile TOUTES les zones déclarées sur une
#: classe d'état changée, y compris celles qui vivent sur d'autres
#: pages : le serveur les rend, les sérialise, les compresse, les
#: envoie — et le navigateur les jette faute de cible. Mesuré le
#: 2026-09-05 sur ``examples/mad`` : une action depuis ``/patients``
#: rendait la zone du tableau de bord pour rien, **8,4 ms** contre
#: 9,6 ms pour la zone utile, soit près de la moitié du drain. Sur
#: ``examples/crm``, ``ViewerPrefs`` traîne 14 zones sur 8 modules
#: pour 4 au plus par page.
#:
#: ⚠️ Un en-tête ABSENT veut dire « je ne sais pas », pas « aucune
#: zone » : le serveur ne filtre alors rien. C'est ce qui rend le
#: réglage sûr — un runtime en cache, un client tiers ou un test qui
#: POSTe à la main retombent sur l'ancien comportement, jamais sur une
#: zone qui cesse silencieusement de se rafraîchir.
#: L'identité de l'ONGLET, tirée une fois par chargement de page.
#:
#: Elle sert à une seule chose, et c'est une économie : exclure l'onglet
#: qui vient d'agir de sa PROPRE diffusion. Il a déjà reçu ses zones dans
#: la réponse de son action ; les re-demander par le flux temps réel est
#: un aller-retour par zone, pour un rendu identique.
#:
#: Mesuré sur ``examples/kanban`` avant l'exclusion : cocher une
#: sous-tâche coûtait **cinq requêtes et 354 Ko** — l'action (177 Ko) plus
#: quatre re-lectures qui renvoyaient exactement ce que la première venait
#: de livrer.
#:
#: ⚠️ Exclure l'onglet, pas la SESSION. Deux onglets de la même personne
#: doivent continuer à se voir : c'est le cas d'usage même d'un tableau
#: partagé qu'on ouvre deux fois pour comparer.
HEADER_TAB: Final[str] = "X-Bretzel-Tab"

#: Le même identifiant, porté par l'URL du flux — un ``EventSource`` ne
#: sait pas poser d'en-tête.
SSE_TAB_PARAM: Final[str] = "tab"

HEADER_ZONES: Final[str] = "X-Bretzel-Zones"

#: **Réponse → client** : l'empreinte de chaque zone que cette réponse
#: vient d'expédier, en ``id:empreinte`` séparés par des virgules. Le
#: runtime la garde et la renvoie dans :data:`HEADER_ZONES` à la requête
#: suivante ; le serveur peut alors TAIRE une zone dont le rendu neuf est
#: identique à celui que le navigateur porte déjà.
#:
#: Mesuré sur ``examples/messagerie`` : basculer un drapeau de lecture
#: expédiait 93 075 octets pour 115 réellement changés — deux zones sur
#: trois revenaient octet pour octet identiques.
#:
#: Le serveur ne STOCKE rien : c'est le client qui porte l'empreinte de
#: ce qu'il affiche. Une empreinte périmée ou absente ne peut donc que
#: faire ré-expédier la zone — jamais la taire à tort.
HEADER_ZONE_HASHES: Final[str] = "X-Bretzel-Zone-Hashes"


# ───────────────────────────────────────────────────────────────────────────
# Framework-served routes (mounted under ``/_bretzel`` by the server layer)
# ───────────────────────────────────────────────────────────────────────────

ROUTE_PREFIX: Final[str] = "/_bretzel"
ROUTE_RUNTIME_JS: Final[str] = f"{ROUTE_PREFIX}/runtime.js"
ROUTE_THEME_CSS: Final[str] = f"{ROUTE_PREFIX}/theme.css"
ROUTE_STYLE_CSS: Final[str] = f"{ROUTE_PREFIX}/style.css"
# Les scripts tiers rapatriés dans ``./.bretzel/vendor/`` — htmx,
# idiomorph, iconify. Servis depuis ici plutôt que depuis trois CDN :
# le ``DOMContentLoaded`` d'une page passe de 644 à 110 ms (mesuré le
# 2026-08-27). Cf. ``bretzel/render/vendor.py``.
ROUTE_VENDOR: Final[str] = f"{ROUTE_PREFIX}/vendor"
# Les DONNÉES d'icône, relayées et mises en cache. Le composant web
# iconify va chercher ses glyphes chez trois hôtes tiers
# (``api.iconify.design`` et deux secours) : mesuré le 2026-09-13, les
# trois coupés rendent **0 glyphe sur 25**. Rapatrier le composant ne
# rapatrie pas ses glyphes — c'est une seconde dépendance, dans la même
# page, et elle survit à l'autre.
ROUTE_ICONS: Final[str] = f"{ROUTE_PREFIX}/icons"
# La marque du framework, servie par défaut quand une app ne pose pas
# son ``favicon=``. Deux fichiers et pas un de plus : le SVG suit
# ``prefers-color-scheme``, le PNG existe parce qu'iOS ne lit pas le
# SVG pour son écran d'accueil. Cf. ``bretzel/static/``.
ROUTE_FAVICON: Final[str] = f"{ROUTE_PREFIX}/favicon.svg"
ROUTE_TOUCH_ICON: Final[str] = f"{ROUTE_PREFIX}/apple-touch-icon.png"
ROUTE_ACTION: Final[str] = f"{ROUTE_PREFIX}/action"
ROUTE_SSE: Final[str] = f"{ROUTE_PREFIX}/sse"
# Les assets utilisateur (``Bretzel(static_dir=…)``) — HORS du préfixe
# ``/_bretzel``, qui est réservé au framework : ce chemin-là apparaît
# dans les URLs que l'app écrit elle-même.
ROUTE_STATIC_DIR: Final[str] = "/static"
# NOT a live channel — a standard HTTP GET hit by the runtime AFTER an
# SSE state-dirty event, to fetch the updated HTML of a subscribing
# zone. The SSE stream is the only long-lived connection.
ROUTE_REFETCH: Final[str] = f"{ROUTE_PREFIX}/refetch"

#: Les routes du framework qu'une garde d'auth peut laisser OUVERTES.
#:
#: Elles ne portent aucune donnée d'app : le runtime, la feuille générée
#: depuis le thème, la feuille compilée, et les trois scripts tiers
#: rapatriés. Une page de connexion en a besoin **avant** que quiconque
#: soit connecté — sans elles, elle s'affiche sans style, son formulaire
#: ne POSTe pas, et sans htmx elle n'a même plus de bridge.
#:
#: ⚠️ **Tout le reste de ``/_bretzel`` reste FERMÉ**, et ce n'est pas
#: intuitif : ``/_bretzel/refetch/…`` re-rend une zone, ``/_bretzel/sse``
#: pousse des rendus, ``/_bretzel/action/…`` exécute du code d'app et
#: ``/_bretzel/datatable.csv`` exporte des lignes. Les ouvrir, c'est
#: laisser une app entière se rendre pour un anonyme.
#:
#: **Pourquoi cette constante existe.** Le premier exemple à écrire une
#: garde (``examples/crm``, 2026-08-20) a dû énumérer ces trois chemins à
#: la main ET raisonner sur les quatre autres. C'est de la connaissance
#: du framework dans du code d'app : le jour où une route interne est
#: ajoutée, chaque garde se casse ou s'ouvre **en silence**. Le classement
#: appartient donc à celui qui monte les routes.
#:
#: Gaté par ``tests/consistency/test_framework_routes_are_classified.py``,
#: qui lit les routes RÉELLEMENT montées et exige que chacune soit d'un
#: côté ou de l'autre.
PUBLIC_ASSET_ROUTES: Final[frozenset[str]] = frozenset({
    ROUTE_RUNTIME_JS,
    ROUTE_THEME_CSS,
    ROUTE_STYLE_CSS,
    # Motif de chemin, pas une URL : la route est montée avec un
    # paramètre. ⚠️ Une garde ne peut donc PAS comparer un chemin reçu à
    # cet ensemble — il faut :func:`is_public_asset_path`.
    f"{ROUTE_VENDOR}/{{filename}}",
    # Même raison, même forme : les glyphes d'une page de connexion sont
    # demandés avant que quiconque soit connecté.
    f"{ROUTE_ICONS}/{{chemin:path}}",
    # L'icône, pour la même raison que les feuilles : une page de
    # connexion la demande AVANT que quiconque soit connecté. Fermée,
    # elle rendrait la page de login (200, du HTML) là où le navigateur
    # attend une image — donc pas d'icône, et rien dans les logs.
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

#: Le marqueur qu'une zone ``@refreshable`` pose sur son élément, portant
#: son propre identifiant. Il existe pour que le runtime puisse énumérer
#: les zones du document sans deviner : l'identifiant vient de
#: ``_stable_id`` et commence par ``refresh_``, mais ce préfixe est une
#: convention Python — le lire en JS ferait un miroir qui dérive au
#: premier renommage. Alimente :data:`HEADER_ZONES`.
DATA_ZONE: Final[str] = "data-bz-zone"

# Viewport cookie — a client→server wire string, so it lives here (single
# source, per this module's rule). Written pre-paint by the boot script
# (``render/shell.py`` interpolates this name into the JS) and read at render
# by ``render/screen.py``. Value format ``"{mobile},{touch}"`` (``1``/``0``).
# Cf. ``.claude/bretzel/screen-responsive-nav.md``.
SCREEN_COOKIE: Final[str] = "bz_screen"

# Le cookie de LANGUE. Il gagne sur ``Accept-Language`` — l'en-tête décrit
# la configuration de l'OS, pas un choix de lecture, donc sans ce cookie
# un visiteur au système anglais qui veut lire en français n'aurait aucun
# moyen de le dire. Posé par ``Language.set()``, lu par le middleware
# de contexte de rendu. Même rôle que ``bz_screen`` juste au-dessus : le
# navigateur sait, le cookie porte, le serveur rend depuis une vraie
# valeur.
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

# Clé RÉSERVÉE du registre ``$bz.pending`` : « une NAVIGATION est en
# vol ». Le bridge l'arme en plus de l'élément déclencheur quand la
# requête est boostée ou porte ``hx-push-url``, et la barre de shell
# (``render/shell.nav_progress_html``) n'est qu'un ``bz-show`` dessus.
#
# Le ``@`` initial met la clé hors d'atteinte d'un ``action_id``, qui
# vaut toujours ``module::qualname``. C'est ici et pas dans le shell
# parce que les deux côtés du fil la nomment — le Python l'écrit dans
# l'attribut, le JS l'arme (``__NAV_PENDING_KEY__``, substitué au
# build comme les balises d'enveloppe et de patch).
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
