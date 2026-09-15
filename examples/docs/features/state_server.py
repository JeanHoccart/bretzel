"""State — server-side state."""

from __future__ import annotations

import datetime
import decimal
import enum
import uuid

from bretzel import page, refreshable, ui
from bretzel.state import (
    AppState,
    PageState,
    SessionState,
    computed,
    field,
    validator,
)
from examples.docs.features.shell import shell
from examples.docs.lib.blocks import source_block, state_mirror

PATH = "/state-server"


class SrvCounter(SessionState):
    """A server counter changed by a handler."""

    n: int = field(default=0)


class Cart(SessionState):
    """A compact example combining fields, a factory, validation, and computed state."""

    items: list[dict] = field(default_factory=list)
    coupon: str = field(default='')
    discount: float = field(default=0.0)

    @validator("coupon")
    def _upper(self, value: str) -> str:
        return value.strip().upper()

    @computed
    def total(self) -> float:
        raw = sum(it.get("price", 0.0) for it in self.items)
        return raw * (1 - self.discount)


class Etat(enum.Enum):
    """An application enum stored by its value."""

    DRAFT = "draft"
    SENT = "sent"


class Facture(SessionState):
    """Domain types are stored as-is, rather than as strings to parse again."""

    emise: datetime.date = field(default_factory=datetime.date.today)
    montant: decimal.Decimal = field(default_factory=lambda: decimal.Decimal("0"))
    reference: uuid.UUID = field(default_factory=uuid.uuid4)
    etat: Etat = field(default=Etat.DRAFT)


class Visites(AppState):
    """A process-wide total, hence `merge="add"`."""

    vues: int = field(default=0, merge="add")


class Ventes(PageState, addressable=True):
    """State in the URL: two published fields and one private field."""

    region: str = field(default="all", url="region")
    mini: int = field(default=0, url="mini")
    #: Without ``url=``, this field cannot be published, even with
    #: ``addressable=True``.
    notes: str = field(default="")


def bump() -> None:
    SrvCounter().n += 1


def decr() -> None:
    SrvCounter().n -= 1


@refreshable(deps=[SrvCounter])
def counter_demo() -> None:
    c = SrvCounter()
    with ui.hstack(align="center", gap="md"):
        ui.button("−", variant="outline", on_click=decr, disabled=c.n == 0)
        ui.heading(str(c.n), level=2, size="2xl",
                   classes="font-mono w-12 text-center")
        ui.button("+1", on_click=bump)
    ui.text(
        "Click → the handler changes `SrvCounter().n` → the `deps=[SrvCounter]` "
        "region renders again. One server round trip.",
        color="muted", size="sm",
    )


@page(PATH, layout=shell, title="Server state")
def state_server_page() -> None:
    with ui.container(width="xl"):
        with ui.vstack(gap="lg"):
            ui.heading("Server state", level=1, size="3xl")
            ui.text(
                "Server state is the source of truth: it lives in Python, is stored "
                "on the server, and can be shared and protected. Inherit a pre-scoped "
                "base class for the lifetime you need.",
                color="muted", size="lg",
            )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("The four scopes", level=2)
                    ui.text(
                        "You do not pass `scope=`: inherit the base class. The lifetime "
                        "changes; the API stays the same.",
                        color="muted", size="sm",
                    )
                    ui.table(
                        columns=[
                            ui.column("scope", label="Base"),
                            ui.column("lives", label="Scope"),
                            ui.column("lifetime", label="Lifetime"),
                        ],
                        rows=[
                            {"scope": "PageState", "lives": "one displayed page",
                             "lifetime": "survives actions (POST); resets on refresh/navigation"},
                            {"scope": "SessionState", "lives": "session cookie",
                             "lifetime": "until the session expires"},
                            {"scope": "UserState", "lives": "authenticated account",
                             "lifetime": "AuthRequiredError without authentication"},
                            {"scope": "AppState", "lives": "entire process",
                             "lifetime": "shared by every request"},
                        ],
                        size="sm",
                    )
                    ui.text(
                        "Simple rule: start with `PageState`; move to Session, User, or "
                        "App only when sharing requires it.",
                        color="muted", size="sm",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Change → re-render", level=2)
                    ui.text(
                        "A handler changes state; every `@refreshable(deps=[…])` region "
                        "that reads it renders again automatically. See Server reactivity "
                        "to control what renders and to work in real time.",
                        color="muted", size="sm",
                    )
                    ui.divider()
                    counter_demo()

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Declare state", level=2)
                    ui.text(
                        "Use immutable defaults directly and mutable defaults with "
                        "`field(default_factory=…)`. `@validator` normalizes on write; "
                        "`@computed` derives values automatically.",
                        color="muted", size="sm",
                    )
                    source_block(Cart)

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Domain types in the store", level=2)
                    ui.text(
                        "A field is not limited to what JSON can encode. `date`, "
                        "`datetime`, `Decimal`, `UUID`, and application enums cross the "
                        "store and come back with the right type. Containers follow: "
                        "`list[date]`, `dict[str, Decimal]`.",
                        color="muted", size="sm",
                    )
                    source_block(Facture)
                    ui.text(
                        "For your own type, call `register_type(MyType, encode=…, "
                        "decode=…)` once at startup. It uses the same path as built-in "
                        "types—there is no framework-only special case.",
                        color="muted", size="sm",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("What concurrency can break", level=2)
                    ui.text(
                        "Two requests that write the same field do not see each other. "
                        "A commit writes only touched fields, so changes to different fields "
                        "coexist. But two changes to the same total can silently overwrite one "
                        "another: the counter rises more slowly than the clicks.",
                        color="muted", size="sm",
                    )
                    source_block(Visites)
                    ui.text(
                        "`merge=\"add\"` declares an additive field: the store combines "
                        "both increments instead of keeping one. No wait and no lock. "
                        "`bretzel check` detects a forgotten declaration because the failure "
                        "does not raise an error.",
                        color="muted", size="sm",
                    )
                    ui.divider()
                    ui.text(
                        "When an action computes from what it read—filtering a list or "
                        "removing an item—no merge can repair it. Serialize access instead:",
                        color="muted", size="sm",
                    )
                    ui.code(
                        "def remove(target: str) -> None:\n"
                        "    with Kanban.lock() as store:\n"
                        "        store.tasks = [task for task in store.tasks\n"
                        "                       if task[\"id\"] != target]\n",
                        lang="python",
                    )
                    ui.text(
                        "The block is a small transaction: take the lock and reread state "
                        "on entry, write fields, then release it on exit. Two requests for "
                        "the same key wait for each other—that cost is paid only there. Use "
                        "`async with` inside an `async def`.",
                        color="muted", size="sm",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("State in the URL", level=2)
                    ui.text(
                        "A `PageState` is keyed by a fresh render UUID on each navigation, "
                        "so a sort or filter does not survive navigation or Back. Declare the "
                        "fields the URL represents to make a view shareable by link and let "
                        "browser navigation restore it.",
                        color="muted", size="sm",
                    )
                    source_block(Ventes)
                    ui.text(
                        "`field(url=…)` names a field and `addressable=True` enables it. "
                        "They are separate because a published field is public: browser "
                        "history, access logs, and the `Referer` header can contain it. A "
                        "field without `url=` cannot leak by accident. To survive navigation "
                        "without publication, use `scope=\"session\"`.",
                        color="muted", size="sm",
                    )

            with ui.card(color="surface"):
                with ui.vstack(gap="md"):
                    ui.heading("State summary", level=2)
                    ui.text(
                        "Scopes, fields (type, default, validators), and computed values "
                        "for the state classes on this page, read from the code at render time.",
                        color="muted", size="sm",
                    )
                    for cls in (SrvCounter, Cart, Facture, Visites, Ventes):
                        with ui.card():
                            state_mirror(cls)
