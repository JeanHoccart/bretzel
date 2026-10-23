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

They ship inside the wheel
--------------------------

Since 0.1.0a3 the three scripts and the Lucide icon set (the default
``ui.icon`` set) live in ``bretzel/render/_vendor/`` and are part of the
package: a production page talks to no third-party host, with no
command to run first. Decided on 2026-10-22, after an outside build of a
helpdesk app found that a production page loaded htmx, idiomorph and
iconify from CDNs unless ``python -m bretzel.render.vendor`` had been run
— a command only named in a startup warning — and fetched its glyphs
from api.iconify.design at runtime. The four files weigh 95 KB gzipped.

What still goes through ``./.bretzel/vendor/``, the project cache: the
dev-only browser CSS compiler (:func:`browser_css_asset`, 276 KB, never
loaded in production) and the glyphs of icon sets other than Lucide,
relayed once by the server then cached. ``python -m bretzel.render.vendor``
still downloads the first; in DEV the app does it by itself
(:func:`ensure_vendored`, called on the first ASGI call).

The fingerprint is verified
---------------------------

Each file carries its expected SHA-256. One byte that does not match and
the download is refused, the file erased: serving from our own origin a
script we have not verified would be strictly worse than letting the CDN
serve it, since we would be lending it our name.
"""

from __future__ import annotations

import hashlib
import json
import urllib.request
from functools import cache
from pathlib import Path
from typing import Final, NamedTuple
from urllib.parse import parse_qs, urlsplit

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


#: The files shipped in the wheel. Third-party, pinned by fingerprint;
#: licenses in ``_vendor/THIRD_PARTY_LICENSES.md``.
PACKAGED_DIR: Final[Path] = Path(__file__).resolve().parent / "_vendor"


def packaged_path(asset: VendoredAsset) -> Path:
    """Where ``asset`` sits inside the installed package."""
    return PACKAGED_DIR / asset.filename


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


def cache_path(asset: VendoredAsset) -> Path:
    """Return the project-cache path for ``asset`` whether or not it exists."""
    return vendor_dir() / cached_name(asset)


def vendored_local_path(asset: VendoredAsset) -> Path:
    """The file to serve: the packaged copy, else the project cache."""
    packaged = packaged_path(asset)
    return packaged if packaged.is_file() else cache_path(asset)


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
    if not force and vendored_is_available(asset):
        return vendored_local_path(asset)
    # Always the project cache: ``force`` must never rewrite a file
    # inside the installed package.
    target = cache_path(asset)

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
    print(f"[bretzel] {asset.filename} -> {target} ({len(payload):,} bytes)")
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


@cache
def _packaged_icon_set(prefix: str) -> dict | None:
    """A set shipped in ``_vendor/`` (Iconify JSON), read once: it never changes."""
    path = PACKAGED_DIR / f"{prefix}.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def packaged_icon_payload(path: str) -> bytes | None:
    """Answer ``/<prefix>.json?icons=a,b`` from a set shipped in the wheel.

    Speaks the one endpoint the web component calls, in the shape the
    Iconify API answers it (``prefix``, ``icons``, ``aliases``,
    ``not_found``), so the component cannot tell the difference. ``None``
    when the set is not shipped: the caller then relays as before.
    """
    parts = urlsplit(path)
    name = parts.path.lstrip("/")
    if not name.endswith(".json"):
        return None
    data = _packaged_icon_set(name[: -len(".json")])
    if data is None:
        return None
    wanted = [n for n in parse_qs(parts.query).get("icons", [""])[0].split(",") if n]
    icons: dict[str, dict] = {}
    aliases: dict[str, dict] = {}
    missing: list[str] = []
    for icon in wanted:
        if icon in data["icons"]:
            icons[icon] = data["icons"][icon]
        elif icon in data.get("aliases", {}):
            alias = data["aliases"][icon]
            aliases[icon] = alias
            parent = alias.get("parent")
            if parent in data["icons"]:
                icons[parent] = data["icons"][parent]
        else:
            missing.append(icon)
    body: dict = {
        "prefix": data["prefix"],
        "icons": icons,
        "width": data.get("width", 24),
        "height": data.get("height", 24),
        "lastModified": data.get("lastModified", 0),
    }
    if aliases:
        body["aliases"] = aliases
    if missing:
        body["not_found"] = missing
    return json.dumps(body, separators=(",", ":")).encode("utf-8")


def icon_payload(path: str, *, allow_download: bool = True) -> bytes | None:
    """Return an Iconify API response body: shipped set, cache, then upstream."""
    packaged = packaged_icon_payload(path)
    if packaged is not None:
        return packaged
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
