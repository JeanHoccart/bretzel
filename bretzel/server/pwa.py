"""``PWA`` — the declaration that makes an app installable.

::

    app = Bretzel(secret_key=…, pwa=PWA(name="Tracker",
                                        icon="/static/logo.png"))

TWO TIERS, and the first is the one you write
---------------------------------------------
``icon=`` takes ONE path and the framework does the rest. ``icons=``
exists for the 20 %: per-size DRAWING — a simplified icon at 48 px, a
detailed one at 512.

⚠️ **The first version of this API had only tier 2**, and the user found
it "unnatural" to read. They were right, and the fault is identifiable:
it MIRRORED the spec, which asks for a list of icons with their sizes.
Mirroring a spec 1:1 gives a spec API — one wrote ``192`` twice (in the
file name AND in the argument), ``"192x192"`` was a string meaning a
square, and ``maskable`` a piece of jargon. Cf. the
``two_tier_api_philosophy`` memory: the magic default for the 80 %, the
escape hatch for the 20 %.

It mounts ``GET /manifest.webmanifest`` and sets its ``<link>`` in the
document head, plus the ``<meta name="theme-color">`` that colours the
system bar once the app is installed.

What it gives, and what it does NOT
-----------------------------------
The manifest is what describes the app to the system: its name, its
icon, its colour, and the fact that it opens in a CLEAN window
(``display: "standalone"``) rather than in a tab. That is what turns an
internal tool into something with an icon in the Start menu.

⚠️ **It makes nothing available offline**, and that has to be said
plainly. Offline requires a *service worker* — a script intercepting
every request and serving a cache. That is NOT shipped here,
deliberately: a service worker is a whole lifecycle of its own
(versions, invalidation, updating an app already installed on a user's
machine), and it is a place where one silently breaks an app in
production while believing one is improving it. The ``cache="shell"``
the thesis sketched therefore awaits a slice of its own.

⚠️ **And one must VERIFY, not assume, whether the install prompt appears
without a service worker.** Chrome long required both (manifest +
service worker with a ``fetch`` handler) to offer "Install". That
requirement has moved across versions, and this comment has not been
measured — so it promises nothing. What IS measured: the manifest is
served, valid, correctly typed and linked.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

#: The manifest's path. Root and not ``/_bretzel/``: its SCOPE is the
#: folder containing it, and a manifest served under ``/_bretzel/`` would
#: describe an app whose root was ``/_bretzel/``.
MANIFEST_ROUTE = "/manifest.webmanifest"


#: ``sizes="any"`` says "this image is valid at every size". That is
#: exact for an SVG, and accepted for a PNG the system will scale. It is
#: what lets tier 1 ask for ONLY a path: without it, one would have to
#: know the file's pixels, hence read it — and a path can point at a CDN.
_ANY_SIZE = "any"


@dataclass(frozen=True, slots=True)
class PWAIcon:
    """Describe one icon in the web application manifest."""

    src: str
    sizes: str | int
    type: str | None = None
    purpose: str | None = None

    def as_dict(self) -> dict[str, str]:
        # An integer is a SQUARE. It is the shape of 99 % of app
        # icons, and writing it ``"192x192"`` forced one to repeat the
        # number already present in the file name.
        size = (f"{self.sizes}x{self.sizes}"
                  if isinstance(self.sizes, int) else self.sizes)
        out = {"src": self.src, "sizes": size}
        if self.type:
            out["type"] = self.type
        elif self.src.lower().endswith(".png"):
            out["type"] = "image/png"
        elif self.src.lower().endswith(".svg"):
            out["type"] = "image/svg+xml"
        if self.purpose:
            out["purpose"] = self.purpose
        return out


@dataclass(frozen=True, slots=True)
class PWA:
    """Declare the metadata that makes an application installable."""

    name: str
    short_name: str | None = None
    description: str | None = None
    #: **Tier 1**: ONE path, and the framework does the rest. Emitted
    #: with ``sizes="any"``, which is exact for an SVG and accepted for a
    #: PNG the system scales.
    #:
    #: The alternative would have been to read the file's pixels to
    #: declare its real size. Rejected: a path can point at a CDN, so it
    #: would only work half the time — and magic that works
    #: intermittently costs more than no magic.
    icon: str | None = None
    #: Allow the system to CROP the icon into its own shape. ⚠️ Only
    #: turn this on when the drawing has margin around it: otherwise
    #: Android cuts into it. Applies only to ``icon=``.
    maskable: bool = False
    #: ``standalone`` is the default because it is the reason to exist:
    #: a clean window, with no address bar. ``browser`` would cancel the
    #: point, ``fullscreen`` is for kiosks.
    display: str = "standalone"
    start_url: str = "/"
    #: The colour of the system bar once installed. ``None`` → nothing
    #: is emitted, and the system chooses.
    theme_color: str | None = None
    background_color: str | None = None
    icons: tuple[PWAIcon, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError(
                "PWA(name=…) is empty. It is the name the system "
                "displays under the icon; without it the app would "
                "install without being nameable."
            )
        if self.icon and self.icons:
            raise ValueError(
                "PWA: ``icon=`` and ``icons=`` are both given. They are "
                "the TWO TIERS of the same thing — ``icon=`` for the "
                "common case (one file, every size), ``icons=`` when "
                "per-size drawing is needed. Letting them coexist would "
                "force inventing a precedence rule nobody would guess."
            )
        if not self.start_url.startswith("/"):
            raise ValueError(
                f"PWA(start_url={self.start_url!r}): a start path "
                f"begins with '/'. Relative, it would resolve against the "
                f"manifest's location and open a page nobody chose."
            )

    def as_manifest(self) -> dict[str, Any]:
        """Return the web application manifest as a serializable dictionary."""
        out: dict[str, Any] = {
            "name": self.name,
            "short_name": self.short_name or self.name,
            "display": self.display,
            "start_url": self.start_url,
        }
        if self.description:
            out["description"] = self.description
        if self.theme_color:
            out["theme_color"] = self.theme_color
        if self.background_color:
            out["background_color"] = self.background_color
        if self.icon:
            unique = PWAIcon(
                self.icon,
                _ANY_SIZE,
                purpose="maskable" if self.maskable else None,
            )
            out["icons"] = [unique.as_dict()]
        elif self.icons:
            out["icons"] = [icon.as_dict() for icon in self.icons]
        return out

    def as_json(self) -> str:
        # ``ensure_ascii=False``: an accented app name must arrive
        # as-is, the manifest being served as UTF-8.
        return json.dumps(self.as_manifest(), ensure_ascii=False)
