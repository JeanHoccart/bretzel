"""Messagerie — a demonstrator of **the address as state**, in a frozen
document.

Run: ``py -m examples.messagerie.main`` (port 8005).

What this example shows, and why it exists. A mailbox is the most
recognisable form of two mechanics nothing else here staged:

1. **The view lives in the URL.** ``View`` declares ``URL = {…}``: the
   open folder and the message being read become address parameters. The
   base layer rewrites the browser's bar at every mutation, with no
   navigation and no reload, and reads it back at the next render. Three
   behaviours arrive at once without a line coding them — the link
   shares, the bookmark finds the view again, and the browser's arrows
   go back and forth. The CRM already published a table's sort, but with
   the names inherited from ``DatatableState``; here the names are
   written.

2. **The document does not scroll, its regions do.** ``ui.viewport`` +
   three ``ui.pane``: the list scrolls without taking the folders along,
   a long message's body scrolls without taking the list along. It is
   the tools' model, and Bretzel keeps the other one by default — this
   one is written.

To which is added **drag and drop into a folder** (``ui.dropzone`` /
``ui.drag_each``), which is not an extra in a mail client but its main
verb, and which tells the same story: filing a message changes the view,
so it changes the address.

**No sidebar**, deliberately: the folder column is the navigation. **No
database**: the mailbox is an ``AppState`` seeded in memory, so
restarting the server resets it. And **nothing leaves** — "Send" files
the message in *Sent*, there is no SMTP behind it.

This app does not use the ``Feature`` contracts. That is not an
oversight: app structure is what ``examples/mad`` stages, and adding it
here would put two subjects in an example that demonstrates one.
"""

from bretzel import Bretzel
from examples.messagerie.core.theme import THEME
from examples.messagerie.features import inbox, shell

app = Bretzel(
    title="Bretzel · Messagerie",
    secret_key="dev-messagerie-secret-change-me",
    theme=THEME,
    mode="dev",
    lang="en",
    texts={
        "file_upload.dropzone": "Drop files here, or click to pick some",
        "file_upload.button": "Send the file",
        "file_upload.remove": "Remove the file",
        "file_upload.multiple_capped": "Several files (up to {max})",
    },
)

app.include(shell, inbox)


if __name__ == "__main__":
    app.run(port=8005, reload=True)
