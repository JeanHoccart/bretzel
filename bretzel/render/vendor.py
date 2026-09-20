"""The three third-party scripts, served from your own host, not a CDN.

What it fixes
-------------

A Bretzel page loads three scripts that do not come from us: htmx, the
idiomorph extension, and the iconify web component. Measured on
2026-08-27 on an app in ``prod`` mode, cold cache, minimal page:

===============================  ==========
resource                         duration
===============================  ==========
``unpkg.com/htmx``                  593 ms
``unpkg.com/idiomorph-ext``         592 ms
``code.iconify.design/iconify``     489 ms
``/_bretzel/runtime.js`` (local)     41 ms
``/_bretzel/style.css`` (local)      21 ms
===============================  ==========

That page's ``DOMContentLoaded`` lands at **644 ms**: it is held
entirely by the first three lines. The two resources served by the app
arrive in 20-40 ms — same connection, already open, already encrypted.
Three third-party origins means three DNS resolutions, three TLS
handshakes and three availabilities that do not depend on us.

The pattern is the Tailwind binary's
------------------------------------

Nothing third-party enters the repository. The files are **downloaded on
demand** into ``./.bretzel/vendor/``, exactly as
:func:`bretzel.theme.build.download_binary` puts the Tailwind compiler in
``./.bretzel/bin/``. The folder is a project cache, not a source — it
does not have to be committed.

Consequence: the fallback is the rule, not the exception. As long as the
download has not happened, the shell points at the CDN and everything
works as before. That is a choice, not an accident: an app that has never
run the command must not stop starting.

    python -m bretzel.render.vendor

⚠️ **In DEV, the app does it by itself since 2026-09-13**
(:func:`ensure_vendored`, called on the first ASGI call). The command was
only known to whoever had read it, so the CDN fallback was the rule for
nearly everyone — and a suite of 84 probes, which runs in dev, depended
on it without knowing. In production nothing changes: going out to the
network when a server starts is an operator's decision, and the command
stays the explicit path.

The fingerprint is verified
---------------------------

Each file carries its expected SHA-256. One byte that does not match and
the download is refused, the file erased: serving from our own origin a
script we have not verified would be strictly worse than letting the CDN
serve it, since we would be lending it our name.
"""

from __future__ import annotations

import hashlib
import urllib.request
from pathlib import Path
from typing import Final, NamedTuple

from bretzel.runtime.protocol import ROUTE_ICONS, ROUTE_VENDOR

#: Re-exported: the path is a word of the protocol, so it lives in
#: ``protocol.py`` with the other routes — that is also what lets
#: ``PUBLIC_ASSET_ROUTES`` classify it without reaching up the stack.
__all__ = (
    "ROUTE_ICONS",
    "ensure_vendored",
    "ROUTE_VENDOR",
    "VendoredAsset",
    "download",
    "download_all",
    "route_for",
    "url_for",
    "vendor_dir",
    "vendored_assets",
    "vendored_is_available",
    "vendored_local_path",
)


class VendoredAsset(NamedTuple):
    """A third-party script: its file name, its source, its fingerprint."""

    filename: str
    url: str
    sha256: str


def vendor_dir() -> Path:
    """``./.bretzel/vendor/`` — the project cache, next to the cwd.

    Same root as the Tailwind binary, for the same reason: one cache per
    project, never shared between two checkouts, never committed.
    """
    return Path.cwd() / ".bretzel" / "vendor"


def cached_name(asset: VendoredAsset) -> str:
    """Return the cache filename containing the expected content fingerprint."""
    stem, _, extension = asset.filename.rpartition(".")
    return f"{stem}.{asset.sha256[:8]}.{extension}"


def vendored_local_path(asset: VendoredAsset) -> Path:
    """Return the local cache path for ``asset`` whether or not it exists."""
    return vendor_dir() / cached_name(asset)


def vendored_is_available(asset: VendoredAsset) -> bool:
    """Return whether a vendored asset exists locally."""
    return vendored_local_path(asset).is_file()


def route_for(asset: VendoredAsset) -> str:
    return f"{ROUTE_VENDOR}/{cached_name(asset)}"


def url_for(asset: VendoredAsset) -> str:
    """The URL to put in the ``<script>``: local if present, CDN otherwise.

    The choice is made at RENDER time and not at startup, at the cost of
    a ``stat``: running the download command while a dev server is up
    must be enough to switch over on the next reload, with no restart. In
    production the file is there or it is not — the ``stat`` then hits an
    entry the system keeps in cache.
    """
    return route_for(asset) if vendored_is_available(asset) else asset.url


def download(asset: VendoredAsset, *, force: bool = False) -> Path:
    """Download ``asset`` into the cache, fingerprint verified.

    The file is only written to its final place AFTER verification: an
    interrupted download must not leave behind a truncated file that
    :func:`vendored_is_available` would declare good, and that the app
    would then serve instead of the CDN.
    """
    target = vendored_local_path(asset)
    if target.is_file() and not force:
        return target

    target.parent.mkdir(parents=True, exist_ok=True)
    print(f"[bretzel] Downloading {asset.filename} from {asset.url}")
    # Explicit ``User-Agent``: ``code.iconify.design`` answers **403** to
    # ``urllib``'s default header (measured on 2026-08-27). unpkg does not
    # care; setting it for all three avoids having two paths.
    request = urllib.request.Request(
        asset.url, headers={"User-Agent": "bretzel-vendor/1.0"}
    )
    with urllib.request.urlopen(request) as response:  # URL en dur
        payload = response.read()

    digest = hashlib.sha256(payload).hexdigest()
    if digest != asset.sha256:
        raise RuntimeError(
            f"{asset.filename}: unexpected digest.\n"
            f"  expected : {asset.sha256}\n"
            f"  got      : {digest}\n"
            "The file was NOT installed. If the upstream version has "
            "moved, update the fingerprint in bretzel/render/vendor.py — "
            "never the other way round."
        )

    target.write_bytes(payload)
    print(f"[bretzel] {asset.filename} -> {target} ({len(payload):,} octets)")
    return target


def download_all(*, force: bool = False) -> list[Path]:
    """Everything that can be brought in-house, in the project cache."""
    return [download(asset, force=force) for asset in downloadable_assets()]


def browser_css_asset() -> VendoredAsset:
    """The browser Tailwind compiler — the FOURTH third party.

    It lives apart from :func:`vendored_assets` because it does not load
    on every page: only when the CSS pipeline is ``browser``, that is to
    say in dev. Putting it in the common list would make it emit in
    production, where the sheet is already compiled.

    ⚠️ **It is the heaviest of the four — 276 KB — and it was the only
    one that was neither verifiable nor vendorable**, because its URL was
    a RANGE (``@4``). Consequence measured on 2026-09-13: every dev page
    made two round trips to unpkg (a 302, then the bundle), and when that
    third party faltered, *no* sheet was produced — a button's ink went
    from ``oklab(…)`` to ``rgb(0, 0, 0)``. A whole suite of probes runs
    in dev: its reliability hung on a third-party site, and its red moved
    from one probe to another without ever speaking about the code.
    """
    from bretzel.render.shell import (  # casse un cycle : shell → vendor
        DEFAULT_TAILWIND_BROWSER_URL,
    )

    return VendoredAsset(
        "tailwind-browser.js",
        DEFAULT_TAILWIND_BROWSER_URL,
        "a60c785630a06196808cbe79e6f7bdb4abcc8f4421a47b56f29338fc84805e3b",
    )


def downloadable_assets() -> tuple[VendoredAsset, ...]:
    """Return every third-party asset that can be downloaded locally."""
    return (*vendored_assets(), browser_css_asset())


def ensure_vendored() -> bool:
    """Download missing third-party assets without making startup fatal."""
    missing = [a for a in downloadable_assets() if not vendored_is_available(a)]
    for asset in missing:
        try:
            download(asset)
        except Exception as exc:  # network, HTTP, digest — never fatal
            print(
                f"[bretzel] {asset.filename} not vendored ({exc}) — the "
                f"page will request it from {asset.url}"
            )
    return all(vendored_is_available(a) for a in downloadable_assets())


def vendored_assets() -> tuple[VendoredAsset, ...]:
    """Return the third-party scripts loaded by every page, in order."""
    from bretzel.render.shell import (  # casse un cycle : shell → vendor
        DEFAULT_HTMX_URL,
        DEFAULT_ICONIFY_URL,
        DEFAULT_IDIOMORPH_URL,
    )

    return (
        VendoredAsset(
            "htmx.min.js",
            DEFAULT_HTMX_URL,
            "e209dda5c8235479f3166defc7750e1dbcd5a5c1808b7792fc2e6733768fb447",
        ),
        VendoredAsset(
            "idiomorph-ext.min.js",
            DEFAULT_IDIOMORPH_URL,
            "1589f425608653a841fa06ef2bb103a59e19f1e6d27064cff894d365efd6d948",
        ),
        VendoredAsset(
            "iconify-icon.min.js",
            DEFAULT_ICONIFY_URL,
            "758d94838db0cafdeb97eb0b54a120de36cfb3c7fe862eed989f37e80c550f02",
        ),
    )


if __name__ == "__main__":  # pragma: no cover — manual entry point
    download_all()


# ───────────────────────────────────────────────────────────────────────────
# Icon DATA — relayed by the server and cached
# ───────────────────────────────────────────────────────────────────────────
#
# Vendoring ``iconify-icon.min.js`` only vendors the component. The shell
# configures the component to call ``/_bretzel/icons``; that route reads
# the local cache first, then queries the Iconify APIs from the server.
# The visitor's browser therefore contacts none of those hosts.
#
# The geometry does not move — a missing icon keeps its box, which the
# CSS sizes at ``1em``. That is why this third party did not produce the
# moving reds of ``-m probes`` (that was the CSS compiler), and why it
# only shows on a screenshot. It remains a network dependency on the
# first access to a glyph absent from the cache.

ICON_CACHE_DIRNAME = "icons"

#: Upstream, and its two fallbacks — the order is Iconify's.
ICON_API_HOSTS: Final[tuple[str, ...]] = (
    "https://api.iconify.design",
    "https://api.simplesvg.com",
    "https://api.unisvg.com",
)


def icon_cache_dir() -> Path:
    """``./.bretzel/vendor/icons/`` — created on demand."""
    d = vendor_dir() / ICON_CACHE_DIRNAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def _icon_cache_file(path: str) -> Path:
    """A request's cache file, named by its FINGERPRINT.

    An Iconify request's path carries a list of icons in the query
    (``lucide.json?icons=check,x``), so it contains characters a file
    name does not accept, and it can exceed the maximum length of a
    Windows path. A fingerprint settles both.
    """
    digest = hashlib.sha256(path.encode("utf-8")).hexdigest()[:32]
    return icon_cache_dir() / f"{digest}.json"


def icon_payload(path: str, *, allow_download: bool = True) -> bytes | None:
    """Return an Iconify API response body from cache or upstream."""
    cached = _icon_cache_file(path)
    if cached.is_file():
        return cached.read_bytes()
    if not allow_download:
        return None
    for host in ICON_API_HOSTS:
        req = urllib.request.Request(
            host + path,
            # ⚠️ An explicit ``User-Agent``, and it is not cosmetic:
            # without it, the API returns **403** (measured on
            # 2026-09-13), and the diagnosis arrives in the form of
            # missing icons.
            headers={"User-Agent": "bretzel/vendor"},
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = resp.read()
        except Exception:  # network, HTTP, DNS — we try the next one
            continue
        if body:
            cached.write_bytes(body)
            return body
    return None
