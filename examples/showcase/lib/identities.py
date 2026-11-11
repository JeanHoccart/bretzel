"""Ready-made identities — a whole theme each, picked in one click.

An identity is not a colour: it is the eleven semantic colours in both
modes, the three radius families, the stroke, the density and the
font, chosen TOGETHER. What makes two apps look alike is rarely the
accent; it is the neutrals, the corners and the type, left at their
defaults.

Each entry overrides the shipped values (:data:`SHIPPED_DEFAULTS`), so
an identity that omits a knob inherits the framework's, never the
previous identity's.
"""

from dataclasses import dataclass, field

from examples.showcase.lib.studio import (
    FONTS,
    SHIPPED_DEFAULTS,
    STEP,
    assign_expression,
)

FONT = dict(FONTS)


@dataclass(frozen=True)
class Identity:
    name: str
    tagline: str
    overrides: dict[str, str | float] = field(default_factory=dict)

    @property
    def values(self) -> dict[str, str | float]:
        values = {**SHIPPED_DEFAULTS, **self.overrides}
        # A density given before the three spacing families (2026-10-26)
        # meant all of them: the two others follow it unless said.
        if "spacing" in self.overrides:
            for family in ("space_box", "space_gap"):
                values[family] = self.overrides.get(family, self.overrides["spacing"])
        return values

    def apply(self) -> str:
        """The client expression that paints the app with this identity."""
        return assign_expression(self.values)

    def swatches(self) -> list[str]:
        """The four colours that say the identity at a glance."""
        values = self.values
        return [str(values[k]) for k in ("primary", "secondary", "surface", "text")]


IDENTITIES: list[Identity] = [
    Identity("Bretzel", "The shipped theme: plum accent, neutral greys."),
    Identity(
        "Harbor",
        "Crisp blue SaaS, cool neutrals.",
        {
            "primary": "#1f6feb", "d_primary": "#4d8ff5",
            "secondary": "#7c5cff", "d_secondary": "#9a82ff",
            "success": "#1a9d6b", "d_success": "#1a9d6b",
            "warning": "#e8a317", "d_warning": "#e8a317",
            "info": "#0ea5c6", "d_info": "#0ea5c6",
            "background": "#f6f8fb", "d_background": "#0b1220",
            "surface": "#ffffff", "d_surface": "#111a2b",
            "interface": "#edf1f7", "d_interface": "#1a2539",
            "text": "#0f1b2d", "d_text": "#e7edf6",
            "muted": "#5a6b85", "d_muted": "#8fa0bb",
            "box": 0.75, "field_": 0.5, "selector": 0.25,
        },
    ),
    Identity(
        "Paper",
        "Warm editorial, serif type, soft corners.",
        {
            "primary": "#b4532a", "d_primary": "#d06a3d",
            "secondary": "#2f6f6a", "d_secondary": "#4a9a93",
            "success": "#4a8a4f", "d_success": "#5fa564",
            "warning": "#d99a1e", "d_warning": "#d99a1e",
            "error": "#c8433a", "d_error": "#de5a50",
            "info": "#3b7fa3", "d_info": "#5a9cc0",
            "background": "#f7f3ec", "d_background": "#16120e",
            "surface": "#fffdf9", "d_surface": "#201a15",
            "interface": "#efe8dd", "d_interface": "#2c241d",
            "text": "#2b2118", "d_text": "#f3ebe1",
            "muted": "#7d6d5d", "d_muted": "#b0a08f",
            "box": 0.5, "field_": 0.375, "selector": 0.25,
            "space_box": STEP * 1.25, "space_gap": STEP * 1.25, "font": FONT["Book"],
        },
    ),
    Identity(
        "Forest",
        "Calm greens, humanist type, generous rounding.",
        {
            "primary": "#2d7a4f", "d_primary": "#44a36d",
            "secondary": "#b0782a", "d_secondary": "#c99440",
            "success": "#2d7a4f", "d_success": "#44a36d",
            "background": "#f5f7f3", "d_background": "#0d130f",
            "surface": "#ffffff", "d_surface": "#141c16",
            "interface": "#eaefe7", "d_interface": "#1d2820",
            "text": "#17241b", "d_text": "#e6eee7",
            "muted": "#5d6d61", "d_muted": "#95a699",
            "box": 1.0, "field_": 0.625, "selector": 0.375,
            "font": FONT["Humanist"],
        },
    ),
    Identity(
        "Brutal",
        "Black on paper, square corners, thick strokes, mono type.",
        {
            "primary": "#111111", "d_primary": "#fafafa",
            "secondary": "#ff4f1f", "d_secondary": "#ff6a3d",
            "success": "#00a35c", "d_success": "#00c46f",
            "warning": "#ffb000", "d_warning": "#ffb000",
            "error": "#ff2e2e", "d_error": "#ff4d4d",
            "info": "#2e6bff", "d_info": "#5a8bff",
            "background": "#f4f4f0", "d_background": "#000000",
            "surface": "#ffffff", "d_surface": "#0e0e0e",
            "interface": "#ebebe6", "d_interface": "#1b1b1b",
            "text": "#0a0a0a", "d_text": "#fafafa",
            "muted": "#52524e", "d_muted": "#a3a3a3",
            "box": 0.0, "field_": 0.0, "selector": 0.0,
            "stroke": 2.0, "font": FONT["Mono"],
        },
    ),
    Identity(
        "Candy",
        "Playful pinks, pill controls, rounded type.",
        {
            "primary": "#e0457b", "d_primary": "#ee5c8f",
            "secondary": "#7c4dff", "d_secondary": "#9a78ff",
            "success": "#22b07d", "d_success": "#2cc48d",
            "warning": "#f5a524", "d_warning": "#f5a524",
            "error": "#f0483e", "d_error": "#f5655c",
            "info": "#3b9eff", "d_info": "#5cb0ff",
            "background": "#fff7fb", "d_background": "#1a0f16",
            "surface": "#ffffff", "d_surface": "#24151f",
            "interface": "#fbeaf2", "d_interface": "#33202c",
            "text": "#2a1523", "d_text": "#fbe9f2",
            "muted": "#86617a", "d_muted": "#c29bb2",
            "box": 1.5, "field_": 2.0, "selector": 1.0,
            "space_box": STEP * 1.25, "space_gap": STEP * 1.25, "font": FONT["Rounded"],
        },
    ),
    Identity(
        "Midnight",
        "Gold on ink, geometric type, made for the dark.",
        {
            "primary": "#b8871b", "d_primary": "#d4a634",
            "secondary": "#6d7cff", "d_secondary": "#8b97ff",
            "background": "#f7f6f2", "d_background": "#0c0c10",
            "surface": "#ffffff", "d_surface": "#15151b",
            "interface": "#eeece5", "d_interface": "#202029",
            "text": "#1c1b18", "d_text": "#ecebf2",
            "muted": "#6e6b62", "d_muted": "#9a99a8",
            "box": 0.5, "field_": 0.375, "selector": 0.25,
            "font": FONT["Geometric"],
        },
    ),
    Identity(
        "Ledger",
        "Dense and sober, for data-heavy back offices.",
        {
            "primary": "#0b5cad", "d_primary": "#3b82d6",
            "secondary": "#0f8a8a", "d_secondary": "#2aa8a8",
            "background": "#f3f4f6", "d_background": "#0f1115",
            "surface": "#ffffff", "d_surface": "#171a20",
            "interface": "#e9ebef", "d_interface": "#22262e",
            "text": "#111827", "d_text": "#e5e7eb",
            "muted": "#4b5563", "d_muted": "#9ca3af",
            "box": 0.375, "field_": 0.25, "selector": 0.125,
            "spacing": STEP * 0.75, "space_box": STEP * 0.5, "space_gap": STEP * 0.5,
            "font": FONT["Grotesk"],
        },
    ),
]
