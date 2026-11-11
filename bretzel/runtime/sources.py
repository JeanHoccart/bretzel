"""Where the runtime's client code lives, and in which order it loads."""

from __future__ import annotations

from pathlib import Path

_HERE = Path(__file__).resolve().parent
SRC = _HERE / "_src"
COMPONENTS = _HERE.parent / "components"

#: The concatenation order: a module may use what the ones before it define.
#: A bare name is a kernel module (``_src/``); a path is a component's engine,
#: under ``components/``, beside the component it serves.
MODULES: tuple[str, ...] = (
    "index",
    "signals",
    "directives",
    "scope",
    "persistence",
    "bridge",
    "helpers",
    "locale",
    "inputs/calendar/calendar",
    "inputs/file_upload/file_upload",
    "feedback/notification/notification",
    "charts/charts",
    "inputs/number_input/number_input",
    "inputs/slider/slider",
    "inputs/select/select",
    "inputs/combobox/combobox",
    "navigation/pagination/pagination",
    "data/accordion/accordion",
    "layout/carousel/carousel",
    "inputs/time_picker/time_picker",
    "layout/dnd",
    "layout/resizable/resizable",
    "inputs/signature_pad/signature_pad",
    "verbs",
    "data/diagram/diagram",
    "data/scheduler/scheduler",
    "tip",
    "inputs/message_input/message_input",
    "data/message/message_list",
)
SOURCES: tuple[Path, ...] = tuple(
    (COMPONENTS / f"{name}.js") if "/" in name else (SRC / f"{name}.js")
    for name in MODULES
)

__all__ = ["COMPONENTS", "MODULES", "SOURCES", "SRC"]
