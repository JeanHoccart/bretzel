"""features/errors — error: the 404 and 403 pages, inside the shell.

Without them, an ``abort(404)`` returns a bare response: the user loses
the navigation along with the page. Mounting them in the shell keeps the
rail at hand.
"""

from __future__ import annotations

from bretzel import Feature, error_page, ui
from examples.crm.features.shell import shell


@error_page(404, layout=shell)
def not_found() -> None:
    with ui.vstack(gap="md"):
        ui.empty_state(
            "Page introuvable", icon="search-x",
            description="This contact, this account or this address does not exist.",
        )
        ui.link("Back to the pipeline", href="/", variant="underline",
                color="primary")


@error_page(403, layout=shell)
def forbidden() -> None:
    ui.empty_state(
        "Access refused", icon="lock",
        description="This view is not open to this profile.",
    )


feature = Feature(name="errors", kind="error",
                  provides=[not_found, forbidden])
