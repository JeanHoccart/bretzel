"""Default :class:`Stepper` / :class:`Step` / :class:`StepPanel` theme.

**One visual identity, two orientations.** The numbered chip is the
state carrier; the connector that follows it takes a tint when the step
is done. Everything is driven by a SINGLE attribute, ``data-status``,
set on the step's ``<li>`` and being ``done`` / ``current`` /
``upcoming`` / ``error``:

- rendered STATIC on the server side, so the first paint is right before
  the runtime hydrates (same idiom as Tabs' ``data-selected``);
- kept reactive by ``bz-attr:data-status`` — except on a step in
  ``error``, whose status is frozen by the developer and therefore has
  no reason to be recomputed.

The descendants read it through ``group-data-[status=…]/step:``. The
group is **named** (``group/step``): without the name, a stepper nested
in another's panel would see the inner chip inherit the outer step's
status (the Tailwind ``group-*`` selector matches ANY carrying ancestor
— it is exactly the Tree chevrons' trap).

Slots :
- ``root``        : the wrapper — it carries the ``bz-data`` scope, so
  also the hidden input and the panels, which an ``<ol>`` cannot host
  (it only accepts ``<li>``)
- ``list``        : the ``<ol>`` that lines up the steps
- ``step``        : the ``<li>`` — carries ``group/step`` + ``data-status``
- ``rail``        : the chip + connector line
- ``bullet``      : the chip (number / check / icon), a ``<button>`` if
  ``clickable``, a ``<span>`` otherwise
- ``connector``   : the line between two chips (absent on the last)
- ``body``        : the label + description column
- ``label``       : the step's title
- ``description`` : the secondary line
- ``panels``      : the ``StepPanel`` container (grid-stack)
- ``panel``       : one ``StepPanel``

The sizes (``sizes``) carry the chip, the two lines of text and the
icon's size token. What depends on the ORIENTATION and not on the size —
flex directions, the connector's thickness and axis, margins — lives in
``orientations``, read by hand by ``Stepper.render()`` (the base composer
only knows ``variants`` / ``sizes`` / ``modifiers``).
"""

from __future__ import annotations

from typing import Any

STEPPER_THEME: dict[str, Any] = {
    "slots": {
        # The list above the panels; the ``gap`` does not count the
        # hidden input (a ``display:none`` element is not a flex item).
        "root": "flex flex-col gap-5",
        "list": "flex list-none",
        # ``group/step`` NAMED — cf. the docstring (the anonymous group trap).
        "step": "group/step relative flex min-w-0",
        "rail": "flex",
        # No dimension here: the box comes from ``sizes``, the axis from
        # ``orientations``. The four statuses compete for the same
        # element, in the order upcoming (base) → current → done →
        # error.
        "bullet": (
            "flex items-center justify-center shrink-0 rounded-full "
            "border-(length:--bz-stroke-strong) font-semibold "
            "transition-[color,background-color,border-color] "
            "duration-200 ease-out "
            "border-text/15 bg-background text-muted "
            "group-data-[status=current]/step:border-(--bz-solid) "
            "group-data-[status=current]/step:bg-(--bz-bg) "
            "group-data-[status=current]/step:text-(--bz-text) "
            "group-data-[status=done]/step:border-(--bz-solid) "
            "group-data-[status=done]/step:bg-(--bz-solid) "
            "group-data-[status=done]/step:text-(--bz-on-solid) "
            "group-data-[status=error]/step:border-error "
            "group-data-[status=error]/step:bg-error "
            # ``text-background`` and not ``text-white``: the chip in
            # error is FILLED, it needs the opposite of the page
            # background — a frozen white would be right in light and
            # wrong in dark, without showing in the mode being tested.
            "group-data-[status=error]/step:text-background "
            "focus-visible:outline-none focus-visible:ring-2 "
            "focus-visible:ring-offset-2 "
            "focus-visible:ring-offset-background "
            "focus-visible:ring-(--bz-focus) "
            # ``enabled:`` compiles to ``&:enabled``, which matches ONLY
            # form controls: on the ``<span>`` chip of the
            # non-clickable mode, these two rules are no-ops — which is
            # exactly what we want, an indicator has no pointer cursor.
            # No hover tint: it would fight the four status fills on the
            # same element (and it would be dead anyway on a coarse
            # pointer).
            #
            # ⚠️ It was ``not-disabled:`` until 2026-08-13, and the
            # comment above already described the intent — but NOT what
            # the variant does. In Tailwind v4 ``not-*`` is a generic
            # negation: ``&:not(:disabled)`` matches any non-disabled
            # element, ``<span>`` included. Measured in the browser: an
            # indicator stepper's chip rendered ``cursor: pointer`` — it
            # looked clickable with nothing being so.
            "enabled:cursor-pointer enabled:active:scale-95 "
            # ⚠️ ``aria-disabled:`` and NOT ``disabled:``: the chip is a
            # ``<span>`` in non-clickable mode, and ``:disabled`` only
            # matches form controls — so both rules were dead there.
            # Unlike the two ``not-disabled:`` above, whose no-op is
            # INTENDED (an indicator has no pointer cursor), this one was
            # a defect: a locked step did not even dim.
            "aria-disabled:opacity-50 aria-disabled:cursor-not-allowed"
        ),
        "connector": (
            "shrink-0 rounded-full bg-text/15 "
            "transition-colors duration-200 ease-out "
            "group-data-[status=done]/step:bg-(--bz-solid)"
        ),
        "body": "flex flex-col min-w-0",
        "label": (
            "font-medium truncate text-muted "
            "transition-colors duration-200 ease-out "
            "group-data-[status=current]/step:text-text "
            "group-data-[status=done]/step:text-text "
            "group-data-[status=error]/step:text-error"
        ),
        "description": "text-muted truncate",
        # The panels stack in the SAME grid cell: a cross-fade would
        # otherwise pile them vertically (idiom taken from Tabs, where
        # the symptom was paid for).
        "panels": "grid",
        "panel": "outline-none col-start-1 row-start-1",
    },
    "sizes": {
        "xs": {
            "bullet": "w-6 h-6 text-[10px]",
            "label": "text-xs",
            "description": "text-[10px]",
            "icon_size": "xs",
        },
        "sm": {
            "bullet": "w-7 h-7 text-xs",
            "label": "text-sm",
            "description": "text-xs",
            "icon_size": "xs",
        },
        "md": {
            "bullet": "w-9 h-9 text-sm",
            "label": "text-base",
            "description": "text-xs",
            "icon_size": "sm",
        },
        "lg": {
            "bullet": "w-11 h-11 text-base",
            "label": "text-lg",
            "description": "text-sm",
            "icon_size": "md",
        },
        "xl": {
            "bullet": "w-14 h-14 text-lg",
            "label": "text-xl",
            "description": "text-base",
            "icon_size": "lg",
        },
    },
    # Read by hand by ``render()`` — the composer only applies
    # ``variants`` (root only) / ``sizes`` / ``modifiers``.
    "orientations": {
        "horizontal": {
            "list": "flex-row items-start",
            # Each step takes an equal share AND its connector eats the
            # remaining space; the LAST one has no connector, so it must
            # not claim a share (its label would stick to the centre of
            # an empty column).
            "step": "flex-col flex-1",
            "step_last": "flex-col flex-none",
            "rail": "flex-row items-center w-full gap-2",
            "connector": "h-0.5 flex-1",
            "body": "mt-2 pr-3",
            "body_last": "",
        },
        "vertical": {
            "list": "flex-col",
            "step": "flex-row gap-3",
            "step_last": "flex-row gap-3",
            "rail": "flex-col items-center gap-1 self-stretch",
            "connector": "w-0.5 flex-1 min-h-5",
            "body": "pb-6",
            # The last step no longer pushes anything below it.
            "body_last": "pb-0",
        },
    },
}
