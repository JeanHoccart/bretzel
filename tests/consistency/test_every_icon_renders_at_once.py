"""Gate: icons are drawn at once, not when they scroll into view.

``<iconify-icon>`` watches its own visibility by default: off screen, it
leaves its host EMPTY — zero wide — draws the glyph when it enters the
viewport, and empties it again when it leaves. Next to a label, the label
sat one icon to the left and jumped sideways while scrolling (reported
2026-10-23). The shell's icons script makes the class's ``startObserver``
a no-op before the browser upgrades the page (``render/shell.py``), which
covers every icon — a component's, an app's, raw markup.

Two ends to hold: the script still does it, and the vendored component
still has the method it disables.
"""

from __future__ import annotations

from bretzel.render.shell import _ICON_CHECKS, _ICON_STARTS_OBSERVER, inline_scripts
from bretzel.render.vendor import vendored_local_path

MUTATION_PROOF = "test_the_detector_still_bites"


def disables_lazy_icons(script: str) -> bool:
    return '"iconify-icon"' in script and "startObserver=function(){}" in script


def test_the_icons_script_turns_lazy_mode_off() -> None:
    assert disables_lazy_icons(inline_scripts(768)["icons"]), (
        "the shell's icons script no longer disables the component's lazy "
        "mode: off-screen icons render empty and push their labels."
    )


def test_the_vendored_component_has_the_method_we_disable() -> None:
    """If an upgrade renamed it, the script would silently do nothing."""
    from bretzel.render.vendor import vendored_assets

    script = next(a for a in vendored_assets() if "iconify" in a.filename)
    text = vendored_local_path(script).read_text(encoding="utf-8")
    assert _ICON_STARTS_OBSERVER in text
    for method in _ICON_CHECKS:
        assert method in text, f"the vendored component lost {method!r}: icons flash empty"


def test_the_detector_still_bites() -> None:
    assert not disables_lazy_icons('window.IconifyProviders={};')
    assert disables_lazy_icons('if(n==="iconify-icon"){c.prototype.startObserver=function(){};}')
