"""The three third-party scripts, served from your own host, not a CDN.

What it fixes
-------------

A Bretzel page loads three scripts that do not come from us: htmx, the
idiomorph extension, and the iconify web component. From a CDN, on a
cold cache, they hold ``DOMContentLoaded`` back, whereas a resource served
by the app arrives over a connection already open, already encrypted.
Three third-party origins means three DNS resolutions, three TLS
handshakes and three availabilities that do not depend on us.

They ship inside the wheel
--------------------------

The three scripts and the Lucide icon set (the default ``ui.icon`` set)
live in ``bretzel/render/_vendor/`` and are part of the package: a
production page talks to no third-party host, with no command to run
first.

What still goes through ``./.bretzel/vendor/``, the project cache: the
dev-only browser CSS compiler (:func:`browser_css_asset`, never loaded
in production) and the glyphs of icon sets other than Lucide,
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
import os
import re
import threading
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
    # ``urllib``'s default header. unpkg does not care; setting it for all
    # three avoids having two paths.
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

    ⚠️ **It is the heaviest of the four, and its URL must stay exact**: a
    RANGE (``@4``) can be neither verified nor vendored. Served from
    there, every dev page makes two round trips to unpkg (a 302, then the
    bundle), and when that third party falters, *no* sheet is produced —
    a button's ink goes from ``oklab(…)`` to ``rgb(0, 0, 0)``. A whole
    suite of probes runs in dev: its reliability must not hang on a
    third-party site.
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


def main(argv: list[str] | None = None) -> int:
    """``bretzel vendor`` (and ``python -m bretzel.render.vendor``).

    Arguments are read, so ``--help`` does not START the download."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="bretzel vendor",
        description=(
            "Download the third-party scripts (htmx, idiomorph, iconify) into "
            "./.bretzel/vendor/, so that no page loads them from a CDN."
        ),
    )
    parser.add_argument("--force", action="store_true",
                        help="download again, even what is already there")
    args = parser.parse_args(argv)
    for path in download_all(force=args.force):
        print(f"[bretzel] vendored {path}")
    return 0


if __name__ == "__main__":  # pragma: no cover — manual entry point
    raise SystemExit(main())


# ───────────────────────────────────────────────────────────────────────────
# Icon DATA — relayed by the server and cached
# ───────────────────────────────────────────────────────────────────────────
#
# Vendoring ``iconify-icon.min.js`` only vendors the component. The shell
# configures the component to call ``/_bretzel/icons``; that route reads
# the sets shipped in the wheel, then the project cache, then queries the
# Iconify APIs from the server. The visitor's browser therefore contacts
# none of those hosts.
#
# The geometry does not move — a missing icon keeps its box, which the
# CSS sizes at ``1em`` — so it only shows on a screenshot. It remains a
# network dependency on the first access to a glyph absent from the cache.
#
# ⚠️ **The route is public and answers ONE request: the component's.**
# ``/<prefix>.json?icons=a,b``, every word in Iconify's grammar, checked
# before the prefix touches a path or a name an upstream URL. A route
# relaying whatever it is given would pay for it three ways: the prefix,
# joined as it came, would read any ``.json`` of the disk (``..%2F``,
# ``..\``, ``C:/``) and, on Windows, open an SMB connection to the host a
# ``\\host\share`` names; every distinct query would write one more file
# to the cache, forever; and an upstream call on the event loop would let
# one slow answer freeze every other request of the worker (the route
# hands it to a thread).
# The cache is therefore kept by ICON, one set file per prefix: it is
# bounded by the icons that exist, not by the requests one can invent.

ICON_CACHE_DIRNAME = "icons"

#: Upstream, and its two fallbacks — the order is Iconify's.
ICON_API_HOSTS: Final[tuple[str, ...]] = (
    "https://api.iconify.design",
    "https://api.simplesvg.com",
    "https://api.unisvg.com",
)

#: Iconify's grammar for a set prefix and for an icon name: lowercase
#: words joined by single hyphens. Neither a dot, a slash nor a backslash.
_ICON_WORD = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
#: The component cuts a request at 500 characters of URL: fewer names fit.
MAX_ICONS_PER_REQUEST: Final[int] = 100
#: What an upstream answer may say of its icons, set-wide.
_ICON_DEFAULTS = ("left", "top", "width", "height")

#: One writer at a time on a cached set: two pages asking for two new
#: glyphs of the same set must both end up in its file.
_CACHE_WRITING = threading.Lock()


class IconRequest(NamedTuple):
    """The component's request: a set and the names it wants from it."""

    prefix: str
    names: tuple[str, ...]


def icon_request(path: str) -> IconRequest | None:
    """``/<prefix>.json?icons=a,b`` read, or ``None`` for anything else."""
    parts = urlsplit(path)
    file_name = parts.path.lstrip("/")
    if not file_name.endswith(".json"):
        return None
    prefix = file_name[: -len(".json")]
    query = parse_qs(parts.query, keep_blank_values=True)
    if not _ICON_WORD.fullmatch(prefix) or list(query) != ["icons"] or len(query["icons"]) != 1:
        return None
    names = tuple(dict.fromkeys(n for n in query["icons"][0].split(",") if n))
    if not 0 < len(names) <= MAX_ICONS_PER_REQUEST:
        return None
    if not all(_ICON_WORD.fullmatch(name) for name in names):
        return None
    return IconRequest(prefix, names)


def icon_cache_dir() -> Path:
    """``./.bretzel/vendor/icons/`` — created on demand."""
    d = vendor_dir() / ICON_CACHE_DIRNAME
    d.mkdir(parents=True, exist_ok=True)
    return d


@cache
def _packaged_icon_set_at(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _packaged_icon_set(prefix: str) -> dict | None:
    """A set shipped in ``_vendor/`` (Iconify JSON), read once: it never
    changes. ``None`` for a prefix outside Iconify's grammar, before any
    path is built from it."""
    if not _ICON_WORD.fullmatch(prefix):
        return None
    path = PACKAGED_DIR / f"{prefix}.json"
    if not path.is_file():
        return None
    return _packaged_icon_set_at(path)


def _answer(data: dict, names: tuple[str, ...]) -> dict:
    """``names`` from a set, in the shape the Iconify API answers them
    (``prefix``, ``icons``, ``aliases``, ``not_found``): the component
    cannot tell a shipped or cached set from the API."""
    icons: dict[str, dict] = {}
    aliases: dict[str, dict] = {}
    missing: list[str] = []
    for icon in names:
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
    return body


def _serialized(body: dict) -> bytes:
    return json.dumps(body, separators=(",", ":")).encode("utf-8")


def packaged_icon_payload(path: str) -> bytes | None:
    """Answer ``/<prefix>.json?icons=a,b`` from a set shipped in the wheel.

    ``None`` when the request is not the component's or the set is not
    shipped: the caller then looks in the cache, then upstream.
    """
    request = icon_request(path)
    data = _packaged_icon_set(request.prefix) if request else None
    if request is None or data is None:
        return None
    return _serialized(_answer(data, request.names))


def _cached_icon_set(prefix: str) -> dict:
    """The icons of ``prefix`` already relayed, by name (empty at first)."""
    path = icon_cache_dir() / f"{prefix}.json"
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            pass  # a file cut short: its glyphs come back from upstream
    return {"prefix": prefix, "icons": {}, "aliases": {}}


def _fetch_icons(request: IconRequest) -> dict | None:
    """The upstream answer for ``request``, or ``None`` if no host gives one."""
    path = f"/{request.prefix}.json?icons={','.join(request.names)}"
    for host in ICON_API_HOSTS:
        req = urllib.request.Request(
            host + path,
            # ⚠️ An explicit ``User-Agent``, and it is not cosmetic:
            # without it, the API returns **403**, and the diagnosis
            # arrives in the form of missing icons.
            headers={"User-Agent": "bretzel/vendor"},
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
        except Exception:  # network, HTTP, DNS, not JSON — we try the next one
            continue
        if isinstance(data, dict) and data.get("prefix") == request.prefix:
            return data
    return None


def _keep_icons(prefix: str, fetched: dict) -> dict:
    """Add what upstream sent to the set's cache file; return the set.

    Each icon is kept with the set-wide defaults of ITS answer written on
    it (``width``, ``height``…): two answers need not share them. Only
    names in Iconify's grammar, and icons that have a ``body``, are kept.
    """
    defaults = {k: fetched[k] for k in _ICON_DEFAULTS if k in fetched}
    icons = {
        name: {**defaults, **icon}
        for name, icon in (fetched.get("icons") or {}).items()
        if _ICON_WORD.fullmatch(str(name))
        and isinstance(icon, dict) and isinstance(icon.get("body"), str)
    }
    aliases = {
        name: alias
        for name, alias in (fetched.get("aliases") or {}).items()
        if _ICON_WORD.fullmatch(str(name))
        and isinstance(alias, dict) and isinstance(alias.get("parent"), str)
    }
    with _CACHE_WRITING:
        kept = _cached_icon_set(prefix)
        if icons or aliases:
            kept["icons"].update(icons)
            kept.setdefault("aliases", {}).update(aliases)
            path = icon_cache_dir() / f"{prefix}.json"
            aside = path.with_suffix(".part")
            aside.write_text(json.dumps(kept, separators=(",", ":")), encoding="utf-8")
            os.replace(aside, path)
    return kept


def icon_payload(path: str, *, allow_download: bool = True) -> bytes | None:
    """Answer the component's request: shipped set, cache, then upstream.

    ``None`` — a 404, after which the component tries its own hosts —
    when the request is not the component's, or when a glyph is missing
    and no upstream host answered. Blocking (a network call): the route
    runs it on a thread, never on the event loop.
    """
    request = icon_request(path)
    if request is None:
        return None
    shipped = _packaged_icon_set(request.prefix)
    if shipped is not None:
        return _serialized(_answer(shipped, request.names))
    kept = _cached_icon_set(request.prefix)
    known = kept["icons"].keys() | kept.get("aliases", {}).keys()
    unknown = tuple(name for name in request.names if name not in known)
    if unknown:
        fetched = _fetch_icons(IconRequest(request.prefix, unknown)) if allow_download else None
        if fetched is None:
            return None
        kept = _keep_icons(request.prefix, fetched)
    return _serialized(_answer(kept, request.names))


def packaged_glyph(icon: str) -> tuple[str, int, int] | None:
    """``(body, width, height)`` of ``prefix:name`` from a set shipped in
    the wheel, without touching the network. ``None`` when the set is not
    shipped, the name unknown, or an alias transforms its parent (rotate,
    flip) — the component then draws it as before."""
    prefix, _, name = icon.partition(":")
    data = _packaged_icon_set(prefix) if name else None
    if data is None:
        return None
    alias = data.get("aliases", {}).get(name)
    if alias is not None:
        if set(alias) != {"parent"}:
            return None
        name = alias["parent"]
    glyph = data["icons"].get(name)
    if glyph is None:
        return None
    return (glyph["body"], glyph.get("width", data.get("width", 24)),
            glyph.get("height", data.get("height", 24)))
