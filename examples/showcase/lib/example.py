"""The two blocks every component page is made of.

``page_header`` names the component; ``example`` shows one use of it —
the rendered preview, and in a second tab the code that produced it.

The code shown IS the code that ran: ``example`` reads the source of the
render function it is given (and of the handlers or states passed in
``uses=``), so a snippet cannot drift from its preview.
"""

import inspect
import textwrap
from collections.abc import Callable, Sequence

from bretzel import ui


def source_of(*objects: object) -> str:
    """The source of each object, dedented, separated by a blank line.

    A ``@refreshable`` zone is a handle around its function: its source
    is the function's, decorator line included.
    """
    return "\n\n\n".join(
        textwrap.dedent(inspect.getsource(getattr(obj, "fn", obj))).strip()  # type: ignore[arg-type]
        for obj in objects
    )


def page_header(names: str | tuple[str, ...], title: str, summary: str) -> None:
    """The page's title block: the ``ui.*`` name(s), the title, one sentence."""
    shown = (names,) if isinstance(names, str) else names
    with ui.vstack(gap="sm"):
        ui.text(" · ".join(f"ui.{name}" for name in shown), size="sm", weight="medium",
                color="primary", classes="font-mono")
        ui.heading(title, level=1, size="3xl")
        ui.text(summary, size="lg", color="muted", classes="max-w-2xl")


def example(
    title: str,
    render: Callable[[], None],
    *,
    note: str = "",
    uses: Sequence[object] = (),
    full: bool = False,
) -> None:
    """One use of a component: a titled preview, and its code.

    ``full=True`` lets the preview take the whole width (tables, charts,
    layouts); otherwise it is centred, the way a control sits in a form.
    ``uses=`` lists the handlers and states the render refers to, so the
    code tab shows everything needed to reproduce the preview.
    """
    with ui.vstack(gap="sm"):
        ui.heading(title, level=2, size="lg")
        if note:
            ui.text(note, color="muted", classes="max-w-2xl")
        # A @refreshable zone is a handle around its function.
        fn = getattr(render, "fn", render)
        with ui.tabs(value="preview", size="sm",
                     name=f"{fn.__module__.rsplit('.', 1)[-1]}-{fn.__name__}"):
            ui.tab("preview", label="Preview", icon="eye")
            ui.tab("code", label="Code", icon="code")
            with (
                ui.tab_panel(tab="preview"),
                ui.card(padding="lg", classes="min-h-40 flex flex-col justify-center"),
                ui.vstack(gap="md", align="stretch" if full else "center", classes="w-full"),
            ):
                render()
            with ui.tab_panel(tab="code"):
                ui.code(source_of(*uses, render), lang="python")
