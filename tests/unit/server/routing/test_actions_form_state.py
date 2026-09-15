"""Typed form-model hydration in the action dispatcher.

Covers the ``def handler(form: MyState)`` injection path : a parameter
annotated with a ``ServerState`` subclass is resolved and hydrated from the
submission, with type coercion + validators, so handlers read typed fields
instead of ``get("name")``. Validation errors are **collected** onto
``form.errors`` (not raised), so the handler can re-render the form with a
message per ``form_field``.

NB : these state classes rely on ``from __future__ import annotations`` so
the metaclass sees their field annotations and wraps them as ``Field``
descriptors (PEP 649 / 3.14 — without the future-import the namespace
carries ``__annotate__`` instead of a populated ``__annotations__`` at
class-build time, and no fields get created). Cf. ``traps.md`` § PEP 649.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

from bretzel import ui
from bretzel.components.base.testing import render_isolated
from bretzel.render import serialize_html
from bretzel.server.routing.actions import _hydrate_state, _state_params
from bretzel.state import FormError, ServerState, field, validator
from bretzel.state.scopes.client import rendering_scope

# ── Appeler la coroutine d'hydratation depuis un test synchrone ──────
#
# ``_hydrate_state`` est une coroutine depuis le 2026-09-04 : elle résout
# par le REGISTRE (qui peut attendre) plutôt que par ``state_cls()`` (qui
# ne peut pas), sans quoi un backend lisant de façon asynchrone rendait
# des valeurs par défaut. Ici il n'y a aucun registre actif, donc le
# chemin retombe sur le constructeur nu — ce que ces tests mesurent.


def hydrate(state_cls: type, form_data: dict[str, Any]) -> Any:
    return asyncio.run(_hydrate_state(state_cls, form_data))


# ── A representative typed form model ────────────────────────────────


class ExpenseForm(ServerState, scope="page"):
    label: str = field(default='')
    amount: float = field(default=0.0)
    qty: int = field(default=0)
    category: str = field(default='food')

    @validator("amount")
    def _positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("Amount must be greater than zero.")
        return value


# ── _hydrate_state : coercion + selection ────────────────────────────


def test_hydrate_coerces_strings_to_declared_types() -> None:
    form = hydrate(ExpenseForm, {"label": "Books", "amount": "12.5", "qty": "3"})
    assert form.label == "Books"
    assert form.amount == 12.5 and type(form.amount) is float
    assert form.qty == 3 and type(form.qty) is int
    assert form.errors == {}


def test_hydrate_ignores_unbound_form_keys() -> None:
    # ``_args`` / CSRF / unrelated fields must not blow up or land anywhere.
    form = hydrate(ExpenseForm, {"label": "X", "_args": "...", "junk": "y"})
    assert form.label == "X"


def test_partial_form_keeps_untouched_field_defaults() -> None:
    # Only ``label`` submitted — the rest stay at their declared defaults
    # rather than being wiped to empty.
    form = hydrate(ExpenseForm, {"label": "Only label"})
    assert form.amount == 0.0
    assert form.category == "food"


def test_empty_numeric_field_is_skipped_not_crashed() -> None:
    # An erased ``type="number"`` input arrives as "" — must keep the
    # default instead of raising on ``float("")``.
    form = hydrate(ExpenseForm, {"amount": ""})
    assert form.amount == 0.0
    assert form.errors == {}


# ── _hydrate_state : error collection ────────────────────────────────


def test_validator_rejection_collected_into_errors() -> None:
    form = hydrate(ExpenseForm, {"amount": "-5"})
    assert form.errors == {"amount": "Amount must be greater than zero."}
    # The rejected assignment is rolled back — the field keeps its default.
    assert form.amount == 0.0


def test_malformed_number_collected_into_errors() -> None:
    form = hydrate(ExpenseForm, {"qty": "not-a-number"})
    assert "qty" in form.errors


def test_multiple_errors_collected_in_one_pass() -> None:
    # Every bad field reports — the loop doesn't stop at the first error.
    form = hydrate(ExpenseForm, {"amount": "-5", "qty": "x", "label": "OK"})
    assert set(form.errors) == {"amount", "qty"}
    # …and valid fields still land.
    assert form.label == "OK"


def test_valid_submission_has_no_errors() -> None:
    form = hydrate(ExpenseForm, {"label": "Books", "amount": "10", "qty": "2"})
    assert form.errors == {}


# ── _state_params (annotation resolution) ────────────────────────────


def test_state_params_resolves_serverstate_annotation() -> None:
    def handler(form: ExpenseForm, note: str = "") -> None: ...

    assert _state_params(handler) == {"form": ExpenseForm}


def test_state_params_empty_for_plain_handler() -> None:
    def handler(label: str = "", amount: float = 0.0) -> None: ...

    assert _state_params(handler) == {}


# ── form_field auto-infers the error from the bound child ────────────


def test_form_field_auto_infers_error_from_bound_child() -> None:
    # No ``error=`` on the form_field : it reads the wrapped input's bound
    # field (``value=form.amount``) and shows ``form.errors["amount"]``.
    form = ExpenseForm()
    form.__dict__["_bz_errors"] = {"amount": "Amount must be greater than zero."}
    with render_isolated(), rendering_scope():
        field = ui.form_field(label="Amount")
        with field:
            ui.number_input(value=form.amount)
        html = serialize_html(field)
    assert "greater than zero" in html
    assert 'role="alert"' in html


def test_form_field_no_error_when_model_clean() -> None:
    form = ExpenseForm()
    with render_isolated(), rendering_scope():
        field = ui.form_field(label="Amount")
        with field:
            ui.number_input(value=form.amount)
        html = serialize_html(field)
    assert 'role="alert"' not in html


# ── Form-level (cross-field) errors ──────────────────────────────────


class _CrossForm(ServerState, scope="page"):
    a: str = field(default='')
    b: str = field(default='')

    @validator
    def _match(self) -> None:
        # Whole-instance validator → raises FormError on a cross-field
        # invariant ; routes to the form-level ``"_"`` key.
        if self.a and self.b and self.a != self.b:
            raise FormError("a and b must match")


def test_form_error_routes_to_form_level_key() -> None:
    form = hydrate(_CrossForm, {"a": "x", "b": "y"})
    assert form.errors == {"_": "a and b must match"}


def test_form_error_coexists_with_per_field_errors() -> None:
    class _Mixed(ServerState, scope="page"):
        email: str = field(default='')
        a: str = field(default='')
        b: str = field(default='')

        @validator("email")
        def _email(self, v: str) -> str:
            if v and "@" not in v:
                raise ValueError("bad email")
            return v

        @validator
        def _match(self) -> None:
            if self.a and self.b and self.a != self.b:
                raise FormError("mismatch")

    form = hydrate(_Mixed, {"email": "nope", "a": "x", "b": "y"})
    assert form.errors == {"email": "bad email", "_": "mismatch"}


def test_explicit_error_overrides_inference() -> None:
    # An explicit ``error=`` always wins over the inferred message.
    form = ExpenseForm()
    form.__dict__["_bz_errors"] = {"amount": "inferred message"}
    with render_isolated(), rendering_scope():
        field = ui.form_field(label="Amount", error="explicit message")
        with field:
            ui.number_input(value=form.amount)
        html = serialize_html(field)
    assert "explicit message" in html
    assert "inferred message" not in html


# ── Raw-value preservation on rejection ──────────────────────────────


def test_rejected_value_preserved_for_redisplay() -> None:
    form = hydrate(ExpenseForm, {"amount": "-5"})
    assert form.errors == {"amount": "Amount must be greater than zero."}
    # Outside render : the authoritative clean value (rolled back).
    assert form.amount == 0.0
    # Inside render : the field surfaces what the user actually typed.
    with rendering_scope():
        assert str(form.amount) == "-5"


def test_input_redisplays_raw_rejected_value() -> None:
    form = hydrate(ExpenseForm, {"amount": "-5"})
    with render_isolated(), rendering_scope():
        inp = ui.input(value=form.amount)
        html = serialize_html(inp)
    assert 'value="-5"' in html


# ── a11y : aria-required propagation ─────────────────────────────────


def test_form_field_marks_required_child_aria_required() -> None:
    with render_isolated(), rendering_scope():
        field = ui.form_field(label="Email", required=True)
        with field:
            ui.input(value="")
        html = serialize_html(field)
    assert 'aria-required="true"' in html


def test_error_sets_aria_invalid_and_describedby() -> None:
    form = ExpenseForm()
    form.__dict__["_bz_errors"] = {"amount": "Amount must be greater than zero."}
    with render_isolated(), rendering_scope():
        field = ui.form_field(label="Amount")
        with field:
            ui.number_input(value=form.amount)
        html = serialize_html(field)
    assert 'aria-invalid="true"' in html
    # the input's aria-describedby points at the error span's id
    m = re.search(r'aria-describedby="([^"]+)"', html)
    assert m is not None, "no aria-describedby on the input"
    assert f'id="{m.group(1)}"' in html  # the error span carries that id
    assert 'role="alert"' in html


def test_no_error_no_aria_invalid_or_describedby() -> None:
    form = ExpenseForm()
    with render_isolated(), rendering_scope():
        field = ui.form_field(label="Amount")
        with field:
            ui.number_input(value=form.amount)
        html = serialize_html(field)
    assert "aria-invalid" not in html
    assert "aria-describedby" not in html


# ── Reactive auto-clear wiring (browser-verified behaviour) ──────────


def test_inferred_error_emits_auto_clear_wiring() -> None:
    form = ExpenseForm()
    form.__dict__["_bz_errors"] = {"amount": "bad"}
    with render_isolated(), rendering_scope():
        field = ui.form_field(label="Amount")
        with field:
            ui.number_input(value=form.amount)
        html = serialize_html(field)
    # Local bz-data flag + clear-on-input + span tied to the flag.
    assert "bz-data" in html and "errShown" in html
    assert "bz-on:input" in html
    assert "bz-show" in html


def test_explicit_error_stays_frozen_no_auto_clear() -> None:
    with render_isolated(), rendering_scope():
        field = ui.form_field(label="Amount", error="frozen")
        with field:
            ui.number_input(value="0")
        html = serialize_html(field)
    assert "frozen" in html
    assert "errShown" not in html  # explicit error doesn't auto-clear
