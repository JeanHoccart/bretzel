"""STATE — Server state.

The server side of state: the truth. Four scopes according to reach and
lifetime, the declaration (field / validator / computed), and "mutate →
re-render" shown live. The mirror at the bottom reads this page's classes
from the code.
"""

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


# ── Demonstration states (the mirror reads them live) ───────────────────

class SrvCounter(SessionState):
    """A server counter — survives the session, mutated by a handler."""

    n: int = field(default=0)


class Cart(SessionState):
    """A rich example — field / factory / validator / computed together."""

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


class Status(enum.Enum):
    """An app enum — the store files it by its VALUE."""

    DRAFT = "draft"
    SENT = "sent"


class Invoice(SessionState):
    """BUSINESS types filed as they are — not strings to re-parse."""

    issued: datetime.date = field(default_factory=datetime.date.today)
    amount: decimal.Decimal = field(default_factory=lambda: decimal.Decimal("0"))
    reference: uuid.UUID = field(default_factory=uuid.uuid4)
    status: Status = field(default=Status.DRAFT)


class Visits(AppState):
    """A total SHARED by the whole process — hence `merge="add"`."""

    views: int = field(default=0, merge="add")


class Sales(PageState, addressable=True):
    """State in the ADDRESS — two fields published, one that is not."""

    region: str = field(default="all", url="region")
    minimum: int = field(default=0, url="min")
    #: No ``url=``: so this field cannot be published, even with
    #: ``addressable=True``. It is the guarantee, not a guideline.
    notes: str = field(default="")


def bump() -> None:
    SrvCounter().n += 1


def decr() -> None:
    SrvCounter().n -= 1


@refreshable
def counter_demo() -> None:
    c = SrvCounter()
    with ui.hstack(align="center", gap="md"):
        ui.button("−", variant="outline", on_click=decr, disabled=c.n == 0)
        ui.heading(str(c.n), level=2, size="2xl",
                   classes="font-mono w-12 text-center")
        ui.button("+1", on_click=bump)
    ui.text(
        'Click → the handler mutates `SrvCounter().n` → the zone, '
        'which read `SrvCounter`, re-renders. One server round trip.',
        color="muted", size="sm",
    )


@page(PATH, layout=shell, title="Server state · Bretzel docs",
      description="Server state in Bretzel: typed Python classes scoped per page, session, user or app — the source of truth, kept on the server.")
def state_server_page() -> None:
    with ui.container(width="xl"):
        with ui.vstack(gap="lg"):
            ui.heading('Server state', level=1, size="3xl")
            ui.text(
                'Server state is the source of truth: it lives in Python, '
                'it is stored server side, it can be shared and protected.'
                ' One inherits from one of the pre-scoped bases according '
                'to the scope wanted.',
                color="muted", size="lg",
            )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading('The four scopes', level=2)
                    ui.text(
                        'One does not pass `scope=`: one inherits from the'
                        ' base. The lifetime changes, the API is '
                        'identical.',
                        color="muted", size="sm",
                    )
                    ui.table(
                        columns=[
                            ui.column("scope", label="Base"),
                            ui.column("vit", label='Scope'),
                            ui.column("survie", label='Lifetime'),
                        ],
                        rows=[
                            {"scope": "PageState", "vit": '1 page shown',
                             "survie": 'survives actions (POST), reset on '
                                       'F5 / nav'},
                            {"scope": "SessionState", "vit": "session cookie",
                             "survie": 'until the session expires'},
                            {"scope": "UserState", "vit": 'authenticated account',
                             "survie": 'AuthRequiredError with no auth'},
                            {"scope": "AppState", "vit": "whole process",
                             "survie": 'shared by every request'},
                        ],
                        size="sm",
                    )
                    ui.text(
                        'A simple rule: start with `PageState`; move up to'
                        ' Session / User / App only when sharing demands '
                        'it.',
                        color="muted", size="sm",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Mutate → re-render", level=2)
                    ui.text(
                        'A handler mutates the state; every '
                        '`@refreshable` zone that reads that '
                        'state is re-rendered automatically. The detail '
                        '(controlling what re-renders, realtime) is in '
                        '“Server reactivity”.',
                        color="muted", size="sm",
                    )
                    ui.divider()
                    counter_demo()

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading('Declaring a state', level=2)
                    ui.text(
                        'An immutable default → directly. A mutable '
                        'default → `field(default_factory=…)`. '
                        '`@validator` normalises on write, `@computed` '
                        'derives automatically.',
                        color="muted", size="sm",
                    )
                    source_block(Cart)

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading('Business types in the store', level=2)
                    ui.text(
                        'A field is not limited to what JSON can write. '
                        '`date`, `datetime`, `Decimal`, `UUID` and any app'
                        ' enumeration cross the store and come back the '
                        'RIGHT type — you never read back a string to re-'
                        'parse. The containers follow: `list[date]`, '
                        '`dict[str, Decimal]`.',
                        color="muted", size="sm",
                    )
                    source_block(Invoice)
                    ui.text(
                        'For a type of your own, `register_type(MyType, '
                        'encode=…, decode=…)` once at startup. It is the '
                        'same route as the shipped types: there is no '
                        'special case reserved for the framework.',
                        color="muted", size="sm",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading('What concurrency breaks', level=2)
                    ui.text(
                        'Two requests writing the SAME field do not see '
                        'each other. The commit writes only the fields '
                        'touched, so two gestures on different fields '
                        'coexist with no effort — but two gestures on the '
                        'same total lose each other, in silence: the '
                        'counter advances more slowly than the clicks, and'
                        ' only a second user reveals it.',
                        color="muted", size="sm",
                    )
                    source_block(Visits)
                    ui.text(
                        '`merge="add"` declares the field ADDITIVE: the '
                        'store combines the two increments instead of '
                        'keeping one. With no waiting, no lock. `bretzel '
                        'check` has a rule for forgetting it (`undeclared-'
                        'shared-counter`), because the mistake neither '
                        'raises nor shows.',
                        color="muted", size="sm",
                    )
                    ui.divider()
                    ui.text(
                        'When the gesture COMPUTES from what it read — '
                        'filtering a list, removing an item — no merge can'
                        ' repair it. There, one serialises:',
                        color="muted", size="sm",
                    )
                    ui.code(
                        "def delete(target: str) -> None:\n"
                        "    with Kanban.lock() as store:\n"
                        "        store.tasks = [t for t in store.tasks\n"
                        "                       if t[\"id\"] != target]\n",
                        lang="python",
                    )
                    ui.text(
                        'The block is a small transaction: the lock taken '
                        'THEN the state re-read on entry, the fields '
                        'written THEN the lock released on exit. Two '
                        'requests on the same key wait for each other — '
                        'that is the price, and it is paid only there. '
                        '`async with` inside an `async def`.',
                        color="muted", size="sm",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading('State in the URL', level=2)
                    ui.text(
                        'A `PageState` is keyed by a render uuid that is '
                        'NEW at every navigation: that is why a sort or a '
                        'filter survives neither a page change nor the '
                        'back button. Declaring the fields the URL is '
                        'authoritative for makes the view shareable by '
                        "link, and the browser's arrows go back and forth "
                        'again.',
                        color="muted", size="sm",
                    )
                    source_block(Sales)
                    ui.text(
                        '`field(url=…)` NAMES, `addressable=True` TURNS ON'
                        ' — and the two are separate because a published '
                        'field is PUBLIC: browser history, access logs, '
                        '`Referer` header. A field nothing has named '
                        'cannot leave by accident; that is how '
                        '`DatatableState.filters` stays out of the address'
                        ' by construction. To survive a navigation WITHOUT'
                        ' being published, it is the scope you need: '
                        '`scope="session"`.',
                        color="muted", size="sm",
                    )

            with ui.card(color="surface"):
                with ui.vstack(gap="md"):
                    ui.heading('The states, at a glance', level=2)
                    ui.text(
                        'Scope, fields (type, default, validators) and '
                        "computed of this page's states — read at render "
                        'time from the code.',
                        color="muted", size="sm",
                    )
                    for cls in (SrvCounter, Cart, Invoice, Visits, Sales):
                        with ui.card():
                            state_mirror(cls)
