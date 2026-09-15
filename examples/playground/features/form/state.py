"""Server-state classes for the Form feature playground.

Scenario form models (LoginForm / SignupForm / ProfileForm / AccountForm)
— each a typed ``PageState`` holding the data AND the validators.

Pattern : the submit handler takes ``form: XForm`` ; the dispatcher
hydrates + validates it and collects any validator rejections into
``form.errors`` (per-field, plus ``"_"`` for cross-field ``FormError``).
Each ``form_field`` infers its message from the bound input — no separate
error-store ClientState. ``DemoErrors`` (below) is kept only for the
Reference card's explicit reactive-error showcase.
"""

from __future__ import annotations

from bretzel.state import (
    ClientState,
    FormError,
    PageState,
    field,
    validator,
)


# ───────────────────────────────────────────────────────────────────
# Scenario 1 — Login (per-field validator + inline error)
# ───────────────────────────────────────────────────────────────────


class LoginForm(PageState):
    """Login scenario : per-field validators on email format AND
    password check (toy — the correct password is ``"123"``).

    Both validators raise ``ValueError`` with field-specific messages ;
    the dispatcher collects them into ``form.errors`` and each
    ``form_field`` displays its own inline (inferred from the bound
    input, auto-clearing on edit)."""

    email:    str  = field(default="")
    password: str  = field(default="")
    logged_in: bool = field(default=False)

    @validator("email")
    def check_email(self, v: str) -> str:
        # Toy validator — real apps use ``email-validator`` lib.
        # Raising aborts the assignment and re-raises on the caller.
        if v and "@" not in v:
            raise ValueError("Invalid email format")
        return v

    @validator("password")
    def check_password(self, v: str) -> str:
        # Toy auth — real apps hash + compare against a credential
        # store. The point here is showing how a server-side rule
        # surfaces as an inline FormField error that auto-clears on
        # the next keystroke. Hint : ``"123"`` is the right answer.
        if v and v != "123":
            raise ValueError("Wrong password (hint : 123)")
        return v


# ───────────────────────────────────────────────────────────────────
# Scenario 2 — Signup (cross-field validator + Alert + Notification)
# ───────────────────────────────────────────────────────────────────


class SignupForm(PageState):
    """Signup scenario : per-field validator + whole-instance
    validator for password match."""

    email:    str  = field(default="")
    password: str  = field(default="")
    confirm:  str  = field(default="")
    created:  bool = field(default=False)

    @validator("email")
    def check_email(self, v: str) -> str:
        if v and "@" not in v:
            raise ValueError("Invalid email format")
        return v

    @validator
    def passwords_match(self) -> None:
        if (self.password and self.confirm
                and self.password != self.confirm):
            raise FormError("Passwords don't match")


# ───────────────────────────────────────────────────────────────────
# Scenario 3 — Profile edit (transformation validators + Alert success)
# ───────────────────────────────────────────────────────────────────


class ProfileForm(PageState):
    """Profile edit scenario : transformation validators that
    normalise the value at write time. Pre-filled with realistic
    defaults so the user can edit and re-save."""

    name:    str  = field(default="Jean Dupont")
    email:   str  = field(default="jean@example.com")
    saved_at: str = field(default="")           # ISO HH:MM:SS

    @validator("name")
    def normalize_name(self, v: str) -> str:
        return v.strip()

    @validator("email")
    def normalize_email(self, v: str) -> str:
        v = v.strip().lower()
        if v and "@" not in v:
            raise ValueError("Invalid email format")
        return v


# ───────────────────────────────────────────────────────────────────
# Reference demo — pure FormField reactive error showcase
# ───────────────────────────────────────────────────────────────────


class DemoErrors(ClientState, persist="memory"):
    """ClientState used by the Reference card's reactive-error demo.

    No HTML5 ``required=`` involved — the demo button always writes
    a fake server error so the FormField inline behaviour can be
    studied in isolation (display + auto-clear-on-input)."""

    email: str = field(default="")


# ───────────────────────────────────────────────────────────────────
# S3 — Server playground. Form's only constructor prop is on_submit
# (a handler, not a toggle) plus the universal escape hatches/modifiers
# — a genuinely thin panel, no props grid needed beyond those.
# ───────────────────────────────────────────────────────────────────


class FormPlayground(PageState):
    # Escape hatches.
    classes:     str = field(default="")
    custom_id:   str = field(default="")
    aria_label:  str = field(default="")
    style:       str = field(default="")
    extra_attrs: str = field(default="")
    # Universal modifiers.
    visible:     str = field(default="on")
    tooltip:     str = field(default="")
    # Event-handler shape.
    on_submit_mode: str = field(default="server")  # server | client | both


# ───────────────────────────────────────────────────────────────────
# S4/S6 — canonical event-log cards (Form has one event : submit)
# ───────────────────────────────────────────────────────────────────


class FormEvents(PageState):
    log: list = field(default_factory=list)


class FormClientEvents(ClientState, persist="memory"):
    log: list = field(default_factory=list)


# ───────────────────────────────────────────────────────────────────
# Scenario 4 — Typed form model (the V3 idiomatic pattern)
# ───────────────────────────────────────────────────────────────────


# Pretend these already exist — the computed validator rejects them
# (a server-only rule HTML5 can't express).
TAKEN_USERNAMES = frozenset({"ada", "admin", "root"})


class AccountForm(PageState):
    """The idiomatic V3 form pattern : ONE typed ``State`` holds the
    data AND the validators. The submit handler takes
    ``form: AccountForm`` (hydrated + coerced + validated by the
    dispatcher) and checks ``form.errors`` ; each ``form_field`` infers
    its field from the bound input and displays / auto-clears the
    message with zero call-site wiring — no separate ``*Errors``
    ClientState, no manual ``setattr`` loop, no ``error=`` prop. This is
    what the Login / Signup / Profile cards do by hand, collapsed."""

    username: str = field(default="")
    email:    str = field(default="")

    @validator("username")
    def check_username(self, v: str) -> str:
        v = (v or "").strip()
        # Computed rule — only the server knows the taken set. Empty is
        # allowed so resetting the form doesn't trip this.
        if v.lower() in TAKEN_USERNAMES:
            raise ValueError("That username is already taken.")
        return v

    @validator("email")
    def check_email(self, v: str) -> str:
        v = (v or "").strip().lower()
        if v and "@" not in v:
            raise ValueError("Enter a valid email address.")
        return v
