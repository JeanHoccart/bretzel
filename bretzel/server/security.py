"""Security headers — the boring ones always, the CSP on request.

Two tiers, and the line between them is "can this break the app".

**The boring headers** (:data:`BORING_HEADERS`) depend on nothing
Bretzel does not know: they are set by default, and
``Bretzel(security_headers=False)`` removes them. No decision to take.

**The CSP**, on the other hand, depends on what the app loads — its
fonts, its CDNs, its remote ``ui.video`` — and the framework cannot
guess it. So it is opt-in: ``Bretzel(csp="report-only")`` then
``csp=True``. But the developer does not write the policy: Bretzel knows
**its own** needs and computes them; ``csp_sources=`` only serves to
declare what the app adds.

What Bretzel owes itself
------------------------

- ``'unsafe-eval'``: the directive engine compiles every ``bz-*``
  attribute into a function (``new Function`` in
  :file:`runtime/_src/02_directives.js` and :file:`03_scope.js`).
  Measured on 2026-09-05: 29 % of the 134 057 expressions the playground
  emits fall outside an interpretable subset (arrow functions with
  statement bodies 17 %, ``if``/``return`` 9.5 %, computed indexing 9 %,
  ``new X()`` 2.3 %), and it is the framework's directives that write
  them — ``bz-init`` 97 %, ``bz-on:focus`` 97 %, ``bz-class`` 92 %.
  Doing without it would require a JS interpreter, not a cleanup pass.

  ⚠️ This does NOT cancel the protection: without ``'unsafe-inline'`` in
  ``script-src``, an injected ``<script>`` tag does not run — and that
  is the dominant XSS class. ``'unsafe-eval'`` only serves an attacker
  once they can already get a string into an expression, which
  :func:`~bretzel.core.escape.escape_js` closes.

- **Three fingerprints** rather than a ``nonce``. The inline bodies the
  shell emits (:func:`~bretzel.render.shell.inline_scripts`) are
  deterministic — measured: 3 distinct fingerprints across 77 pages × 2
  requests. A ``nonce`` would have forced one value per response (hence
  an uncacheable page) and one more parameter on every custom shell; the
  hashes cost nothing and touch no signature.

- **The icon API hosts.** The current shell configures
  ``<iconify-icon>`` to go through the local ``/_bretzel/icons`` route.
  The historical origins stay allowed for compatibility; it is the
  server that queries them on a cache miss, not the visitor's browser.

- **The assets' origins, as they are**. The CDN fallback is the rule as
  long as ``python -m bretzel.render.vendor`` has not run (cf.
  :mod:`bretzel.render.vendor`): a hard-coded policy would lie half the
  time. The URLs therefore come from
  :func:`~bretzel.render.shell.shell_sources`, the same source as what
  the shell emits — and that is what makes the policy follow by itself
  when a fourth dependency arrives.

"""

from __future__ import annotations

import base64
import hashlib
from collections.abc import Iterable, Mapping, Sequence
from typing import Final
from urllib.parse import urlsplit

__all__ = [
    "BORING_HEADERS",
    "CSP_DIRECTIVES",
    "ICON_API_ORIGINS",
    "build_policy",
    "script_hash",
]


#: Set on every response, unless ``security_headers=False``.
#:
#: None of the three depends on what the app loads, which is why they are
#: a default and the CSP is not.
#:
#: - ``nosniff`` stops the browser re-guessing a response's type — that
#:   is what turns an uploaded file into a script.
#: - ``strict-origin-when-cross-origin`` is modern browsers' default;
#:   writing it makes it true on old ones too.
#: - ``SAMEORIGIN`` and not ``DENY``: an app is entitled to include
#:   itself in an iframe (previews, docs), and clickjacking comes from
#:   elsewhere. When the CSP is active, ``frame-ancestors`` says the same
#:   thing and takes precedence.
BORING_HEADERS: Final[dict[str, str]] = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "X-Frame-Options": "SAMEORIGIN",
}

#: Iconify's historical hosts, kept in the policy for compatibility. The
#: shell today directs glyphs to the local ``/_bretzel/icons`` route; the
#: server relay uses the same list.
#:
#: Gated by ``tests/consistency/test_the_icon_hosts_are_in_the_policy.py``:
#: an iconify update changing those hosts must turn red here rather than
#: make the icons disappear in production.
ICON_API_ORIGINS: Final[tuple[str, ...]] = (
    "https://api.iconify.design",
    "https://api.simplesvg.com",
    "https://api.unisvg.com",
)

def _base_policy(
    *,
    hashes: Sequence[str],
    js_ext: Sequence[str],
    css_ext: Sequence[str],
) -> dict[str, list[str]]:
    """The policy Bretzel owes itself.

    Extracted so that :data:`CSP_DIRECTIVES` DERIVES from it instead of
    copying it: adding a directive here makes it extensible by an app
    without anyone thinking about it, where two lists diverged silently.
    """
    return {
        "default-src": ["'self'"],
        # ``'unsafe-eval'``: the directive engine. Not
        # ``'unsafe-inline'`` — that is what kills the injected <script>.
        "script-src": ["'self'", "'unsafe-eval'", *hashes, *js_ext],
        # ``'unsafe-inline'`` is IRREDUCIBLE here: the page carries
        # ``style=`` attributes, and a hash or a nonce does not cover an
        # attribute — worse, in the presence of either the browser
        # IGNORES ``'unsafe-inline'`` and the attribute is dropped
        # anyway. The browser Tailwind compiler (dev mode) additionally
        # injects its sheet at runtime.
        "style-src": ["'self'", "'unsafe-inline'", *css_ext],
        "img-src": ["'self'", "data:", "blob:"],
        "font-src": ["'self'", "data:"],
        # The bridge POSTs same-origin, and so does the SSE. The icon
        # hosts stay allowed for compatibility with the old direct path.
        "connect-src": ["'self'", *ICON_API_ORIGINS, *js_ext],
        "media-src": ["'self'", "data:", "blob:"],
        "manifest-src": ["'self'"],
        "form-action": ["'self'"],
        # The counterpart of ``X-Frame-Options: SAMEORIGIN``, and it
        # takes precedence.
        "frame-ancestors": ["'self'"],
        "base-uri": ["'self'"],
        # Nothing needs <object>/<embed>, and they bypass
        # ``script-src`` on old engines.
        "object-src": ["'none'"],
    }


#: The directives an app is allowed to extend through ``csp_sources``.
#:
#: The list exists so that **a typo is an error**: ``{"img_src": [...]}``
#: or ``{"image-src": [...]}`` does nothing at all in a browser, the
#: resource is simply blocked, and the only hint is a console line.
#: Refusing the key at startup costs less.
CSP_DIRECTIVES: Final[frozenset[str]] = frozenset(
    # DERIVED from the base policy, no longer copied: two lists to keep
    # in agreement diverged at the first addition, and the symptom landed
    # on the developer TRYING to extend the directive, not on the one who
    # added it.
    _base_policy(hashes=(), js_ext=(), css_ext=())
) | frozenset(
    # The two the base layer does not carry: with no default value,
    # they inherit from ``default-src``, and an app must be able to
    # declare them.
    {"frame-src", "worker-src"}
)


def script_hash(body: str) -> str:
    """Return the ``'sha256-…'`` of an inline ``<script>`` body.

    The browser hashes the bytes **exactly** as they are between the
    tags: no trim, no normalisation. Hence the bare ``encode("utf-8")``.
    """
    digest = hashlib.sha256(body.encode("utf-8")).digest()
    return f"'sha256-{base64.b64encode(digest).decode('ascii')}'"


def _origin(url: str) -> str | None:
    """Return an absolute URL's origin, or ``None`` when it is relative.

    A relative URL (``/_bretzel/vendor/htmx.min.js``) is covered by
    ``'self'`` and has nothing to add to the policy.
    """
    parsed = urlsplit(url)
    if not parsed.scheme or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


def build_policy(
    *,
    inline_bodies: Iterable[str],
    script_urls: Iterable[str],
    style_urls: Iterable[str] = (),
    extra: Mapping[str, Sequence[str]] | None = None,
) -> str:
    """Compose the value of the ``Content-Security-Policy`` header.

    ``script_urls`` and ``style_urls`` are the URLs the shell will
    actually emit — that is what makes the policy correct whether
    vendoring has happened or not, and what makes it follow by itself
    when a fourth dependency arrives. The two are separate because a
    script origin has no business in ``style-src``: putting it there
    would allow a stylesheet we never intended to load.
    ``inline_bodies`` are the bodies of
    :func:`~bretzel.render.shell.inline_scripts`.

    The values of ``extra`` are added **on top of** the framework's
    sources: an app can widen, never narrow. Narrowing would happen
    silently and would break the framework for the developer who did it.
    """
    js_ext = sorted({o for u in script_urls if (o := _origin(u))})
    css_ext = sorted({o for u in style_urls if (o := _origin(u))})
    hashes = [script_hash(b) for b in inline_bodies]

    policy = _base_policy(hashes=hashes, js_ext=js_ext, css_ext=css_ext)

    for name, added in (extra or {}).items():
        if name not in CSP_DIRECTIVES:
            known = ", ".join(sorted(CSP_DIRECTIVES))
            raise ValueError(
                f"csp_sources: unknown directive {name!r}. "
                f"A misspelled directive does NOTHING in a browser — the "
                f"resource is blocked with no message. The accepted "
                f"directives are: {known}."
            )
        # ⚠️ A directive ABSENT from the policy is not permissive: it
        # falls back on ``default-src``. Declaring it therefore takes it
        # out of that fallback, and what ``default-src`` allowed is lost
        # — it is a NARROWING disguised as an addition.
        #
        # Measured on 2026-09-05 on the playground:
        # ``frame-src: ["data:"]`` blocked a SAME-ORIGIN iframe that used
        # to pass, because ``frame-src`` had until then inherited from
        # ``default-src 'self'``. So we seed with what the directive
        # inherited, for "widen, never narrow" to be true and not merely
        # written.
        policy.setdefault(name, list(policy["default-src"]))
        for source in added:
            if source not in policy[name]:
                policy[name].append(source)

    return "; ".join(f"{name} {' '.join(vals)}" for name, vals in policy.items())
