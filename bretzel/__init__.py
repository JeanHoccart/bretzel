"""Bretzel — Server-Driven UI for Python."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

from bretzel import state as state
from bretzel.components import ui

try:
    __version__ = _pkg_version("bretzel")
except PackageNotFoundError:  # raw source tree, not installed as a distribution
    __version__ = "0.1.0a1"
from bretzel.render import Language
from bretzel.render.decorators import (
    download,
    error_page,
    layout,
    page,
    refresh,
    refreshable,
)
from bretzel.render.screen import Screen
from bretzel.runtime.verbs import (
    copy,
    fullscreen,
    print_page,
    share,
    vibrate,
)
from bretzel.server import (
    AuthRequiredError,
    Bretzel,
    BretzelConfig,
    BretzelError,
    Feature,
    FeatureError,
    abort,
    background,
    idempotent,
    push_url,
    redirect,
    reload,
)
from bretzel.server import auth as _auth_module
from bretzel.server import oauth as _oauth_module
from bretzel.server.pwa import PWA, PWAIcon
from bretzel.state import LiveConnection
from bretzel.theme import ColorScheme

# ``auth`` is exposed as a module so ``from bretzel import auth`` then
# ``auth.login(user_id)`` works as documented in spec 07. ``oauth``
# takes the same shape: one writes ``oauth.OIDC(...)``, never a bare
# class import — the prefix says which protocol is being spoken.
auth = _auth_module
oauth = _oauth_module

__all__ = [
    "__version__",
    "Bretzel",
    "BretzelConfig",
    "PWA",
    "PWAIcon",
    "BretzelError",
    "AuthRequiredError",
    "Feature",
    "FeatureError",
    "abort",
    "redirect",
    "push_url",
    "Language",
    "reload",
    "background",
    "copy",
    "fullscreen",
    "print_page",
    "share",
    "vibrate",
    "idempotent",
    "download",
    "error_page",
    "layout",
    "page",
    "refresh",
    "refreshable",
    "Screen",
    "ColorScheme",
    "LiveConnection",
    "ui",
    "state",
    "auth",
    "oauth",
]
