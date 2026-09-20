"""Resolved app configuration — populated once at :class:`Bretzel` init.

Frozen dataclass so app code can't mutate the resolved view at runtime.
Validation happens in :py:meth:`__post_init__` ; clear errors at boot
beat opaque crashes mid-request.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from bretzel.render import LanguageTables
from bretzel.server.crypto import (
    PURPOSE_ACTION,
    PURPOSE_AUTH,
    PURPOSE_CSRF,
    derive_key,
)

#: The subset of BCP-47 an app declares in practice: a language,
#: possibly a script, possibly a region — ``fr``, ``zh-Hant``,
#: ``pt-BR``, ``zh-Hant-TW``. The extensions (``-u-ca-buddhist``) and the
#: private tags are outside what ``<html lang>`` asks for, and accepting
#: them would amount to validating nothing.
_BCP47 = re.compile(r"[A-Za-z]{2,3}(-[A-Za-z]{4})?(-([A-Za-z]{2}|\d{3}))?")


class ConfigError(ValueError):
    """Raised at :class:`BretzelConfig` construction when a required
    setting is missing or malformed."""


@dataclass(frozen=True, slots=True)
class BretzelConfig:
    """The resolved, validated configuration of a :class:`Bretzel` app.

    Construction goes through :py:meth:`from_kwargs` so we can apply
    env-var fallbacks consistently. Direct ``BretzelConfig(...)`` use
    is supported in tests but skips the env lookup.
    """

    # ── Identification ────────────────────────────────────────────────
    title: str = "Bretzel App"
    # ``description`` flows into the document head as the global
    # ``<meta name="description">`` fallback when a page doesn't set
    # its own via ``@page(description=...)``.
    description: str | None = None

    # ── Security primitives ───────────────────────────────────────────
    secret_key: str = ""  # mandatory — validated below
    # CSRF protection is always-on. The ``/_bretzel/action/*`` route is
    # protected by per-call HMAC on ``action_id + bound_args`` ; every
    # other non-safe method (POST/PUT/PATCH/DELETE) goes through the
    # :class:`CSRFMiddleware`, which verifies a session-bound token in
    # the ``X-Bretzel-CSRF`` header (echoed from the page envelope) and
    # checks the request ``Origin`` against ``trusted_hosts`` (or the
    # request ``Host`` when none configured).
    #
    # Each surface uses its OWN derived key
    # (:func:`bretzel.server.crypto.derive_key`) — compromising the
    # action signing key doesn't compromise the auth cookie or vice
    # versa. The derivation happens once at config construction ; the
    # three keys live in ``_action_key`` / ``_auth_key`` / ``_csrf_key``
    # below and are addressed by name from the relevant call sites.
    _action_key: bytes = field(init=False, repr=False, compare=False, default=b"")
    _auth_key: bytes = field(init=False, repr=False, compare=False, default=b"")
    _csrf_key: bytes = field(init=False, repr=False, compare=False, default=b"")

    # ── Persistence + scaling ─────────────────────────────────────────
    redis_url: str | None = None
    workers: int = 1

    # ── Sessions / auth ───────────────────────────────────────────────
    # Bretzel auth is intentionally MINIMAL : just the 4 helpers
    # (``login`` / ``logout`` / ``user_id`` / ``is_authenticated``) + the
    # signed cookie. Login pages, password verification, post-auth
    # redirects — all of that is the user app's responsibility, not the
    # framework's.
    session_max_age_days: int = 30

    # ── Static / build ────────────────────────────────────────────────
    # When set, the folder is mounted at ``/static`` (the
    # ``ROUTE_STATIC_DIR`` constant) by ``_mount_static_dir`` at startup —
    # useful for user assets (favicon, logos, files to download). A path
    # that does not point at an existing folder RAISES at startup.
    static_dir: str | None = None

    # ── Icon ──────────────────────────────────────────────────────────
    # Three values, and the third is not cosmetic:
    #
    #   ``None``   (default) the Bretzel mark, served from
    #              ``bretzel/static/`` by ``ROUTE_FAVICON``;
    #   ``"/…"``   the app's icon, at the URL it gives — it is up to the
    #              app to serve it (``static_dir=`` does that);
    #   ``False``  none. The head still emits an empty ``<link>``
    #              (``href="data:,"``): with NO ``<link rel=icon>`` at
    #              all the browser goes looking for ``/favicon.ico`` by
    #              itself, so removing our mark would cost a 404 per
    #              page.
    #
    # The third case exists because someone shipping a real product must
    # be able to remove our mark BEFORE having their own.
    favicon: str | bool | None = None

    # ── Security middleware shortcuts ─────────────────────────────────
    cors_origins: tuple[str, ...] = ()
    trusted_hosts: tuple[str, ...] = ()
    # Anti-replay window (HMAC v2, opt-in) : reject a signed action whose
    # render timestamp is older than this many seconds. ``None`` = valid
    # forever (pre-v2). A stale action 403s → the client reloads the page.
    action_max_age: int | None = None

    # The three headers that depend on nothing (``nosniff``,
    # ``Referrer-Policy``, ``X-Frame-Options``). On by default because
    # they cannot break any app; the setting exists for the app that sets
    # them itself upstream, behind its proxy.
    security_headers: bool = True

    # The CSP, on TWO deliberately separate axes — the mode here, the
    # sources in ``csp_sources`` below. Mixing them (a dict meaning
    # "enable AND extend") would make two ways of writing the same thing.
    #
    # ``False`` by default, and that is the split: Bretzel cannot guess
    # the app's fonts, CDNs and iframes, so the app decides.
    # ``"report-only"`` is the first rung — the browser evaluates the
    # policy and reports what would have been dropped WITHOUT blocking
    # anything. You watch what comes back, you complete ``csp_sources``,
    # then you move to ``True``. That mode exists precisely so as not to
    # discover in production that an origin was missing.
    csp: bool | Literal["report-only"] = False

    # What the APP adds — Bretzel already computes what it owes itself
    # (its inline script fingerprints, ``'unsafe-eval'``, the icon API
    # hosts, its assets' origins depending on whether vendoring has
    # happened or not).
    #
    #     Bretzel(csp=True, csp_sources={
    #         "font-src": ["https://fonts.gstatic.com"],
    #         "frame-src": ["https://www.youtube.com"],
    #     })
    #
    # One can widen, never narrow: narrowing would happen silently and
    # would break the framework for whoever wrote it.
    csp_sources: Mapping[str, Sequence[str]] = field(
        default_factory=dict, compare=False
    )

    # ── Language ──────────────────────────────────────────────────────
    # The document's language, in BCP-47 (``"fr"``, ``"fr-CA"``,
    # ``"pt-BR"``). It does TWO things, and not one more:
    #
    #   1. ``<html lang="…">``, which is the standard attribute — a
    #      screen reader picks its voice from it, and the browser its
    #      hyphenation. The parameter existed in ``render/shell.py`` from
    #      the start and **nobody passed it**: every Bretzel page shipped
    #      a hard-coded ``lang="en"``, French apps included.
    #   2. It travels as far as the components, which give it to ``Intl``
    #      (browser) or to their formatter (server) for everything that
    #      is DERIVED: month and day names, time axes, number
    #      separators, currency.
    #
    # This is NOT i18n (out of scope for v2.0, cf. the charter): no
    # catalogue, no plural rule, no message extraction. The sentences the
    # framework wrote itself — "Clear filters", "No results" — derive
    # from no language; they are replaced one by one through
    # :attr:`texts`.
    lang: str = "en"
    # The framework's words, overridable. Keys in
    # :data:`bretzel.render.texts.DEFAULT_TEXTS`; an unknown key RAISES
    # at startup rather than being silently ignored — a typo in a dict
    # shows nowhere else.
    texts: Mapping[str, Any] = field(default_factory=dict, compare=False)
    # The languages the app can render. EMPTY = monolingual, and that is
    # the default: nothing changes for an app that declares nothing.
    #
    # Non-empty, the language is resolved PER REQUEST — the ``bz_lang``
    # cookie, then ``Accept-Language``, then ``lang``. That is Django's
    # order, Rails's and next-intl's, and it is not arbitrary: the header
    # is a first-visit default, never an authority, otherwise a language
    # selector becomes unwritable and two people opening the same URL see
    # two pages.
    #
    # ``lang`` must appear in it: it is the fallback, and a fallback
    # outside the list would return a language the app says it cannot
    # render.
    languages: tuple[str, ...] = ()
    #: DERIVED (``__post_init__``): the per-language word tables. Not a
    #: setting — it is not passed to ``Bretzel(...)``.
    text_tables: Any = field(init=False, repr=False, compare=False, default=None)

    # ── Responsive nav ────────────────────────────────────────────────
    # Single viewport threshold (CSS px) below which ``Screen().is_mobile``
    # is true. Read only by the pre-paint boot script (interpolated
    # server-side into the FOUC-style inline script — never hardcoded in
    # runtime.js, anti-rule 3). There is no live resize listener (the device
    # doesn't change mid-session). 768 = Tailwind's ``md``. Cf.
    # screen-responsive-nav.md.
    mobile_breakpoint: int = 768

    # NAVIGATION progress bar, on by default. On a page taking 800 ms to
    # come back, you click and nothing moves — so you click again. It is
    # the only loading indicator the framework turns on unasked, and the
    # reason is that it has NO placement decision to make: a strip at the
    # screen edge, one per app, never in the flow. (An in-flight action
    # indicator, by contrast, must say WHERE it shows — hence
    # ``ui.pending()``, explicit.)
    #
    # Turning it off is a legitimate aesthetic choice: an app with its
    # own loading chrome would have two.
    nav_progress: bool = True

    # ── PWA ───────────────────────────────────────────────────────────
    #: The installability declaration. ``None`` → no manifest route, no
    #: ``<link>``: an app that asks for nothing does not have to carry the
    #: vocabulary.
    pwa: Any = None

    @property
    def _manifest_url(self) -> str | None:
        """The manifest's URL, or ``None`` — read by the pipeline.

        A PROPERTY and not a field: it derives from ``pwa``, so the two
        cannot diverge. A field could have stayed set after ``pwa`` was
        removed, and the document head would then have linked a manifest
        nobody serves.
        """
        if self.pwa is None:
            return None
        from bretzel.server.pwa import MANIFEST_ROUTE
        return MANIFEST_ROUTE

    # ── Transport ─────────────────────────────────────────────────────
    # ``Secure`` on the cookies. ``None`` = derived from the request's
    # scheme (cf. ``auth.resolve_cookie_secure``) — it is a question of
    # transport, not of environment. Forcing it is only useful behind a
    # proxy terminating TLS without uvicorn running with
    # ``proxy_headers=True``: the app then sees ``http`` and would
    # underestimate.
    secure_cookies: bool | None = None

    # ── Preset ────────────────────────────────────────────────────────
    # ``mode`` ONLY sets the defaults of the settings below, plus governs
    # the assets / cache axis (CSS pipeline, headers, cache-bust) through
    # :attr:`is_dev`. It no longer decides anything else on its own: a
    # single boolean governing verbosity, error exposure AND cookie
    # security at once cost a session bug in production (cf.
    # ``auth.resolve_cookie_secure``).
    mode: Literal["dev", "prod"] = "prod"

    # ── CSS pipeline ──────────────────────────────────────────────────
    # Which path produces the CSS served to the browser. It is the ONLY
    # axis that changes what is RENDERED, hence a named setting rather
    # than an implication of the mode:
    #
    # - ``"build"``  : compiles ``style.css`` at startup, served as a
    #   render-blocking ``<link>``. The CSS is there at the first paint.
    # - ``"browser"``: the ``@tailwindcss/browser`` compiler compiles in
    #   the page. No binary to install, but the CSS arrives AFTER the
    #   first paint — cf. traps.md, any property under ``transition``
    #   then animates from its unstyled value.
    # - ``"auto"``   : ``build`` in production, ``browser`` in dev. Falls
    #   back to ``browser`` with a warning when no binary can be found.
    #
    # ``css="build"`` in dev gives exact parity with production, at the
    # cost of a compilation (~3 s) on every startup.
    css: Literal["auto", "build", "browser"] = "auto"

    # ── Independent axes (default: follows the preset) ─────────────────
    # Exposure — does the detail of exceptions go out in the response,
    # and is FastAPI's traceback page allowed to surface? It is a
    # security decision tied to being public or not.
    expose_errors: bool = False
    # Diagnostics — should the framework be talkative? Feature drift
    # warnings, ``each()`` without a stable key, readable generated IDs.
    # That is the ONLY meaning of "debug": it governs neither the
    # transport, nor the exposure, nor the assets.
    debug: bool = False

    @property
    def is_dev(self) -> bool:
        """Development preset — assets / cache axis only."""
        return self.mode == "dev"

    @property
    def css_pipeline(self) -> Literal["build", "browser"]:
        """The effective CSS pipeline, with ``"auto"`` resolved.

        ``auto`` keeps the historical trade-off: production compiles (the
        CSS must be there at the first paint), dev leaves the browser
        compiler so as not to require a binary nor pay ~3 s on every
        restart. The difference is now NAMED: ``css="build"`` in dev
        gives exact parity with production.
        """
        if self.css != "auto":
            return self.css
        return "browser" if self.is_dev else "build"

    # ── Validation ────────────────────────────────────────────────────

    def __post_init__(self) -> None:
        if not self.secret_key:
            raise ConfigError(
                "secret_key is required — pass it to Bretzel(secret_key=...) "
                "or set the BRETZEL_SECRET_KEY environment variable."
            )
        if len(self.secret_key) < 16:
            raise ConfigError(
                "secret_key must be at least 16 characters long. "
                "Use ``secrets.token_hex(32)`` to generate a strong one."
            )
        if self.workers < 1:
            raise ConfigError(
                f"workers must be >= 1, got {self.workers}."
            )
        if self.workers > 1 and self.redis_url is None:
            raise ConfigError(
                "Multi-worker deployments need redis_url configured "
                "(state + SSE broker need a shared backend across workers)."
            )
        if self.session_max_age_days < 1:
            raise ConfigError(
                f"session_max_age_days must be >= 1, got {self.session_max_age_days}."
            )
        # BCP-47, the form both ``<html lang>`` and ``Intl`` expect. We
        # validate the SHAPE, not existence: refusing "fr-CA" because it
        # is not in a list would make the framework lie about what it
        # knows. A malformed tag, on the other hand, shows nowhere —
        # ``Intl`` raises in the browser, so silently server-side, and
        # the HTML attribute is simply ignored.
        if not _BCP47.fullmatch(self.lang):
            raise ConfigError(
                f"lang must be a BCP-47 tag (e.g. 'fr', 'fr-CA', "
                f"'pt-BR'), got {self.lang!r}."
            )
        # Resolved once at startup: merging and validating the keys has
        # no reason to replay on every request, and an unknown key must
        # raise AT BOOT — not on the page that displays it.
        for code in self.languages:
            if not _BCP47.fullmatch(code):
                raise ConfigError(
                    f"languages contains {code!r}, which is not a BCP-47 "
                    f"tag (e.g. 'fr', 'fr-CA')."
                )
        if self.languages and self.lang not in self.languages:
            raise ConfigError(
                f"lang={self.lang!r} is not in languages="
                f"{list(self.languages)}. It is the negotiation's "
                f"fallback: outside the list, it would render a language "
                f"the app declares it cannot render."
            )
        # ``languages`` NORMALISED: a monolingual app declares
        # ``(lang,)``, not ``()``. Two representations of the same state
        # forced three modules to test for emptiness separately, and "one
        # language" is already the degenerate case of the general one.
        object.__setattr__(
            self, "languages", tuple(dict.fromkeys([self.lang, *self.languages]))
        )
        # ``texts`` stays WHAT THE USER WROTE — a setting. The resolved
        # tables are a separate object, which is QUERIED: a language
        # without a table falls back on the default there instead of
        # raising a ``KeyError`` on every request.
        object.__setattr__(
            self,
            "text_tables",
            LanguageTables(self.texts, languages=self.languages, default=self.lang),
        )
        if self.mobile_breakpoint < 1:
            raise ConfigError(
                f"mobile_breakpoint must be >= 1 (CSS px), got {self.mobile_breakpoint}."
            )
        # ``csp=True`` / ``False`` / ``"report-only"``, and nothing
        # else. A typo (``csp="report"``) would otherwise be treated as
        # truthy by the middleware and would set a BLOCKING header where
        # the developer believed they were only observing.
        if self.csp not in (True, False, "report-only"):
            raise ConfigError(
                f"csp must be True, False or 'report-only' — got "
                f"{self.csp!r}. 'report-only' makes the browser evaluate "
                f"the policy WITHOUT blocking anything: that is where one "
                f"starts."
            )
        if self.csp_sources and self.csp is False:
            raise ConfigError(
                "csp_sources is supplied but csp=False: the sources "
                "would be set nowhere. Add csp='report-only' "
                "(observation) or csp=True (blocking)."
            )
        # The keys are validated here rather than on the first render:
        # a misspelled directive does NOTHING in a browser, the resource
        # is simply blocked with no message.
        if self.csp_sources:
            from bretzel.server.security import CSP_DIRECTIVES

            for name in self.csp_sources:
                if name not in CSP_DIRECTIVES:
                    raise ConfigError(
                        f"csp_sources: unknown directive {name!r}. "
                        f"The accepted directives are: "
                        f"{', '.join(sorted(CSP_DIRECTIVES))}."
                    )
        if "*" in self.cors_origins:
            # The framework wires CORS with ``allow_credentials=True``
            # (cf. lifecycle.py), so a wildcard origin makes Starlette
            # reflect ANY Origin back with credentials — any site could
            # then send a signed action request with the user's cookies.
            # That is a CSRF hole on the whole action surface. Force the
            # app to list explicit origins.
            raise ConfigError(
                "cors_origins=['*'] is unsafe: CORS is wired with "
                "allow_credentials=True, so a wildcard origin lets any "
                "site send credentialed requests (including signed "
                "actions) — a CSRF hole. List explicit origins instead, "
                "e.g. cors_origins=['https://app.example.com']."
            )

        # Derive per-purpose keys once the master secret has been
        # validated. ``object.__setattr__`` because the dataclass is
        # frozen — these are computed fields, not user-supplied.
        object.__setattr__(self, "_action_key", derive_key(self.secret_key, PURPOSE_ACTION))
        object.__setattr__(self, "_auth_key", derive_key(self.secret_key, PURPOSE_AUTH))
        object.__setattr__(self, "_csrf_key", derive_key(self.secret_key, PURPOSE_CSRF))

    # ── Helpers ───────────────────────────────────────────────────────

    @classmethod
    def from_kwargs(cls, **kwargs: Any) -> BretzelConfig:
        """Resolve config from kwargs + env-var fallbacks.

        ``secret_key`` falls through to ``$BRETZEL_SECRET_KEY`` if not
        passed explicitly; ``mode`` falls through to ``$BRETZEL_MODE``
        ("dev" / anything else, unset → prod).

        This is where the preset becomes concrete values: ``debug`` and
        ``expose_errors`` when not supplied (or ``None``) take the mode's
        value. Each stays independently overridable — that is the whole
        point: ``mode="prod", debug=True`` gives a talkative production
        without exposing errors, and ``mode="dev", expose_errors=False``
        allows testing the real error pages locally.
        """
        if not kwargs.get("secret_key"):
            kwargs["secret_key"] = os.environ.get("BRETZEL_SECRET_KEY", "")
        if kwargs.get("mode") is None:
            kwargs["mode"] = (
                "dev"
                if os.environ.get("BRETZEL_MODE", "prod").strip().lower() == "dev"
                else "prod"
            )
        is_dev = kwargs["mode"] == "dev"
        for axis in ("debug", "expose_errors"):
            if kwargs.get(axis) is None:
                kwargs[axis] = is_dev
        if kwargs.get("css") is None:
            kwargs["css"] = "auto"
        # Coerce iterables to tuples so the frozen dataclass works.
        if "cors_origins" in kwargs and kwargs["cors_origins"] is not None:
            kwargs["cors_origins"] = tuple(kwargs["cors_origins"])
        if "trusted_hosts" in kwargs and kwargs["trusted_hosts"] is not None:
            kwargs["trusted_hosts"] = tuple(kwargs["trusted_hosts"])
        return cls(**kwargs)
