"""A ``ui.form_field`` label names its control, whatever the control.

Found by an outside build on 2026-10-22: the label's ``for=<name>``
pointed at an id no control carries, so it labelled nothing — a screen
reader read the placeholder, ``get_by_label`` found no field — and a
``required=True`` asterisk inside the label changed its text to "Email*".
"""

from __future__ import annotations

import re

from starlette.testclient import TestClient

from bretzel import Bretzel, ui
from bretzel.render import page


def submit() -> None:
    pass


def rendered() -> str:
    app = Bretzel(secret_key="v" * 32, mode="dev")

    @page("/")
    def home() -> None:
        with ui.form_field(label="Email", name="email", required=True):
            ui.input(name="email", type="email")
        with ui.form_field(label="Customer", name="customer"):
            ui.combobox(name="customer", options=["Ann", "Bob"])
        with ui.form_field(label="Status", name="status"):
            ui.select(name="status", options=["Open", "Closed"])
        with ui.form(on_submit=submit):
            ui.input(name="x")

    app.include(home)
    with TestClient(app) as client:
        return client.get("/").text


def labels(html: str) -> dict[str, str]:
    """label text → label id."""
    return {
        re.sub(r"<[^>]+>", "", m.group(2)).strip(): m.group(1)
        for m in re.finditer(r'<label[^>]*\bid="([^"]+)"[^>]*>(.*?)</label>', html, re.S)
    }


def test_every_control_is_labelled_by_its_label() -> None:
    html = rendered()
    found = labels(html)
    assert set(found) >= {"Email", "Customer", "Status"}, found
    # Email: the <input> itself. Customer: the search input AND the
    # role=combobox trigger. Status: the role=combobox button.
    assert re.search(rf'<input[^>]*name="email"[^>]*aria-labelledby="{found["Email"]}"', html)
    assert re.search(rf'<input[^>]*aria-labelledby="{found["Customer"]}"', html)
    assert re.search(rf'role="combobox"[^>]*aria-labelledby="{found["Customer"]}"', html)
    assert re.search(rf'<button[^>]*role="combobox"[^>]*aria-labelledby="{found["Status"]}"', html)


def test_the_asterisk_stays_out_of_the_label_text() -> None:
    html = rendered()
    assert "Email" in labels(html), "the label text of a required field is not 'Email'"
    assert re.search(r'</label><span[^>]*aria-hidden="true"[^>]*>\*</span>', html)


def test_a_form_leaves_validation_to_the_server() -> None:
    form = re.search(r"<form[^>]*>", rendered()).group(0)
    assert "novalidate" in form, form
