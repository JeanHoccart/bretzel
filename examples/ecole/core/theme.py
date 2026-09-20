"""core/theme — the app's only real global.

**The density comes from the framework**, and the app has nothing to ask
for: it is the DEFAULT shipped since 2026-09-13. This file only decides
the COLOURS.

The scale was written by hand in a ``core/preset.py`` on 2026-09-12, on
the user's judgement in front of the screen (*"look, kanban is more
compact by default"*) — first by copying the kanban's 300 lines, then by
moving two Tailwind tokens. The second attempt was the right one, and it
became the shipped scale: two apps writing the same correction is a gap
in the framework, not an app preference.

**The colours: calm, and no pure black.** A timetable grid is a WALL of
coloured cards, and at that density a very dark background under a
saturated hue tires in ten seconds. So the dark background is a slightly
warm grey, the text comes down from pure white, and the accent is a muted
blue-green that lets red and amber say what they have to say — they are
what carries the information (an hour with a nature, a day without class,
a refused mark).

**Light is paper, not a screen**: ``#f6f5f2``, because the app is looked
at next to exercise books.

⚠️ **The 19 px base size was REMOVED on 2026-09-12**, on the user's
judgement in front of the screen: *"it is too big"*. EF-U3 asked for
*"nothing shows below 19 px — the tablet is a workstation, not a
consultation"*, and that was applied by moving the typographic root. The
result held the requirement to the letter and missed its intent: on a
desktop screen, an app 19 % larger does not read better, it shows less —
the week went off the screen.

The need behind EF-U3 stays true and stays to be handled where it arises:
on the tablet, where the browser has its own size setting. What has
changed is that it is now EXPRESSIBLE — ``Theme(text={…})`` takes the
whole scale, without copying a component slot.

What stays true is gated:
``tests/consistency/test_ecole_never_sets_a_text_size.py`` holds that the
app decides no text size — it is what leaves the theme sole authority
over density.
"""

from bretzel.theme import Theme

#: What FLIES during a drag, and what the original seat becomes.
#:
#: The runtime already does what Sortable.js and dnd-kit's
#: ``DragOverlay`` do: the real node stays in the flow, marked
#: ``data-bz-dragging``, and an anonymous clone classed
#: ``.bz-drag-preview`` follows the pointer. The default is a **1:1**
#: clone — so, on a seating plan, the same large card twice, on top of
#: each other. Seen on screen: *"it is quite disconcerting to see the
#: whole card take the place."*
#:
#: What the others do, and what is copied here: **what flies is smaller
#: than the original**. Trello, Linear and Notion fly a compact card and
#: leave an empty slot behind; the calendars let the TARGET carry the
#: information. On a grid of fixed slots, it is the second that counts —
#: hence the original seat emptied rather than greyed out.
#:
#: ⚠️ **No API touched**, and it is the point of the trial: the clone
#: carries a known class, the original a theme state. So an app can
#: redraw both without asking the framework for anything. What it does
#: not give: the CHOICE of what flies. We hide pieces of the clone
#: instead of declaring a representation — so this block knows
#: ``vignette_assise``'s structure (avatar, first name, surname, icons)
#: and would break if it changed order. It is the trial's limit, not a
#: fatality.
APERCU_DE_GLISSER = """
/* La pastille qui suit le doigt : l'avatar et le prénom, rien d'autre. */
.bz-drag-preview {
  width: auto !important;
  height: auto !important;
  border-radius: 999px;
  background: var(--color-surface);
  color: var(--color-surface-foreground);
  border: 1px solid var(--bz-stroke-strong, rgb(128 128 128 / 0.35));
  box-shadow: 0 10px 24px -8px rgb(0 0 0 / 0.45);
  padding: 0.25rem 0.75rem 0.25rem 0.25rem;
  opacity: 1;
}
/* La vignette passe en rangée : avatar puis prénom, côte à côte. */
.bz-drag-preview > * {
  flex-direction: row !important;
  align-items: center !important;
  gap: 0.5rem !important;
  padding: 0 !important;
}
/* Le nom de famille et la rangée d'icônes ne volent pas. */
.bz-drag-preview > * > :nth-child(n+3) {
  display: none !important;
}
"""

#: The blue-green accent. Muted on purpose: it serves to say "this is a
#: lesson", that is, the ORDINARY case, which must not shout.
ACCENT = "#2f7d6b"

THEME = Theme(
    css=APERCU_DE_GLISSER,
    # The original seat EMPTIES rather than greying out: on a grid of
    # slots, what informs is the place freed and the target aimed at,
    # not a pale copy under the one that flies. The framework's default
    # (`opacity-30 grayscale`) is good for a LIST, where the item leaves
    # the flow — here it stays in its seat.
    components={
        "draggable": {
            "slots": {"dragging": "data-[bz-dragging=true]:opacity-0"},
        },
    },
    semantic={
        "primary": ACCENT,
        "secondary": "#7a6a9c",
        # Paper, not a screen.
        "background": "#f6f5f2",
        "surface": "#ffffff",
        "interface": "#ecebe7",
        "text": "#1f2328",
        "muted": "#5f6874",
    },
    semantic_dark={
        "primary": "#5fb3a1",
        "secondary": "#a892d4",
        # A slightly warm grey, not a near-black: see the docstring.
        "background": "#15181c",
        "surface": "#1c2026",
        "interface": "#272c34",
        # An off-white: pure white on a dark background blooms.
        "text": "#e6e8ea",
        "muted": "#9aa3ad",
    },
)
