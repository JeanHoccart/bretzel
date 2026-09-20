"""A component's THEME card — what `describe X --theme` returns.

Why it exists
-------------
The normal card names the keys one is allowed to write in
``Theme(components={…})``, and stops just short of the question one
really asks. Measured on 2026-09-10 while writing the kanban's preset:
**about ten ``theme.py`` opened by hand** while ``describe`` was running.

The two lines it returned for ``button`` and for ``select`` were
IDENTICAL although the two shapes are incompatible — ``button`` expects
``"md": "h-10 px-4"``, ``select`` expects ``"md": {"trigger": …}`` — and
``input`` showed ``icon_pad_left`` nowhere, which lives INSIDE a step
without being a slot.

The three gaps, and what each one costs
---------------------------------------
1. **the SHAPE** (string or dict of sub-keys). Unguessable, and it is
   what decides whether the override is read: a dict written where the
   theme ships a string loses ALL the step's tokens — the component
   renders bare, in 200, with no error; the reverse raises an
   ``AttributeError`` at render time that names neither the theme, nor
   the component, nor the key;
2. **the current value** — without it one does not know what one is
   replacing;
3. **a step's sub-keys**, absent from both lists.

What it refuses to do
---------------------
Vomit the table. ``select`` has 18 slots, ``datatable`` far more, and
70 855 characters of Tailwind classes across the catalogue: an output
printing them all is no longer readable, so it no longer answers. The
card therefore shows ONE step in full — the one the component takes by
DEFAULT, read from its signature — and merely names the others.

It is read from ``cls.THEME``, so it cannot drift: same argument as
``bretzel describe``.
"""

from __future__ import annotations

from typing import Any

#: The parameter that chooses within a group, when there is one. A group
#: absent from this table has no "default step" — ``slots`` is not a
#: choice, it is the list of the component's pieces.
GROUP_TO_PARAM = {
    "sizes": "size",
    "variants": "variant",
    "shapes": "shape",
    "tones": "tone",
}

#: Beyond that, we name without showing. One more line costs nothing;
#: ten screens of Tailwind classes cost the whole reading.
_MAX_NAMED = 24


def _shape_of(value: Any) -> str:
    return "dict" if isinstance(value, dict) else "str"


def _value_lines(value: Any) -> list[str]:
    """What ONE step is worth, shown in full.

    A dict opens onto its sub-keys — which is precisely what no list
    showed, and ``icon_pad_left`` is the example: it lives in a ``sizes``
    step without being a slot.
    """
    if not isinstance(value, dict):
        return [f"      {value}"]
    # A COMPUTED width, not a fixed one: `select` carries a
    # `header_btn_primary` of 18 characters, and a column of 16 glued the
    # name to its value.
    width = max(len(str(sub)) for sub in value) + 2
    return [
        f"      {sub!s:<{width}}{sub_value}" for sub, sub_value in value.items()
    ]


def _default_key(cls: Any, group: str, table: dict) -> str | None:
    """The step the component takes without being asked.

    Read from the REACTIVE PROP and not from the signature: ``__init__``
    returns ``None`` for ``size=`` across the whole catalogue — it is the
    descriptor that carries the real default (``'md'``). Looking in the
    signature therefore gave "no default step" everywhere, and the card
    kept silent about exactly what the item asked for: a step's sub-keys.

    Checked present in the table before being rendered: a default
    designating no key must not print a value at random.
    """
    param = GROUP_TO_PARAM.get(group)
    if param is None:
        return None
    descriptor = getattr(cls, "__reactive_props__", {}).get(param)
    default = getattr(descriptor, "default", None) if descriptor else None
    if default is None:
        import inspect

        try:
            parameter = inspect.signature(cls.__init__).parameters.get(param)
        except (TypeError, ValueError):
            return None
        default = None if parameter is None else parameter.default
    key = str(default) if default is not None else None
    return key if key in {str(k) for k in table} else None


def theme_sheet(ui_name: str) -> str:
    """``ui_name``'s theme card, as text.

    Raises :class:`KeyError` when the name is not a component, with the
    same sentence as ``describe`` — a user who gets a name wrong must
    read the same thing on both sides.
    """
    from bretzel.components import ui as ui_module

    cls = getattr(ui_module, ui_name, None)
    if not isinstance(cls, type):
        raise KeyError(f"`ui.{ui_name}` does not exist")
    theme = getattr(cls, "THEME", None)
    theme_key = getattr(cls, "THEME_KEY", "") or ""
    if not isinstance(theme, dict) or not theme_key:
        raise KeyError(f"`ui.{ui_name}` has no theme")

    out = [
        f"Theme for ui.{ui_name} — Theme(components={{{theme_key!r}: {{…}}}})",
        "",
    ]
    for group, table in theme.items():
        if not isinstance(table, dict):
            out += [f"  {group}", f"    (single value) {table}", ""]
            continue

        keys = [str(k) for k in table]
        forms = {_shape_of(v) for v in table.values()}
        shape = forms.pop() if len(forms) == 1 else "mixed"
        out.append(f"  {group}  —  {len(keys)} keys, shape '{shape}'")

        shown = _default_key(cls, group, table)
        if shown is not None:
            param = GROUP_TO_PARAM[group]
            out.append(f"    {shown}  (default for {param}=):")
            out += _value_lines(table[shown])
            others = [k for k in keys if k != shown]
            if others:
                out.append(f"    other values: {', '.join(others)}")
        elif len(keys) <= _MAX_NAMED:
            out.append(f"    {', '.join(keys)}")
        else:
            out.append(f"    {', '.join(keys[:_MAX_NAMED])}, … (+{len(keys) - _MAX_NAMED})")
        out.append("")

    out += [
        "⚠️ The SHAPE determines whether your override is applied.",
        "   A dict where the built-in theme provides a string drops every",
        "   token in that tier; the component renders unstyled without an error.",
        "   A string where the built-in theme provides a dict raises at render time.",
        "   A NEW key is the supported way to extend the theme.",
    ]
    return "\n".join(out)
