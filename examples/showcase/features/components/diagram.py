"""``/diagram`` — a directed graph, laid out for you on the server."""

from bretzel import refreshable, ui
from bretzel.state import PageState, field
from examples.showcase.lib.example import example, page_header

SUMMARY = ("A directed graph laid out on the server: list the edges, get "
           "the layers. Pipelines, service maps, org charts.")


def pipeline() -> None:
    ui.diagram(edges=[
        ("checkout", "lint"),
        ("checkout", "unit tests"),
        ("lint", "build image"),
        ("unit tests", "build image"),
        ("build image", "deploy staging"),
        ("build image", "security scan"),
        ("deploy staging", "deploy production"),
        ("security scan", "deploy production"),
    ], size="sm")


def service_map() -> None:
    ui.diagram(
        nodes=[
            ui.node("web", label="Web app", icon="monitor", badge="Next"),
            ui.node("mobile", label="Mobile app", icon="smartphone"),
            ui.node("gateway", label="API gateway", icon="shield-check",
                    color="primary"),
            ui.node("orders", label="Orders", icon="shopping-cart"),
            ui.node("billing", label="Billing", icon="credit-card",
                    color="warning", badge="degraded"),
            ui.node("postgres", label="Postgres", icon="database"),
            ui.node("stripe", label="Stripe", icon="landmark", color="info"),
        ],
        edges=[
            ui.edge("web", "gateway"),
            ui.edge("mobile", "gateway"),
            ui.edge("gateway", "orders"),
            ui.edge("gateway", "billing"),
            ui.edge("orders", "postgres"),
            ui.edge("billing", "postgres"),
            ui.edge("billing", "stripe", label="webhooks", style="dashed"),
        ],
    )


def person(node):
    with (ui.card(padding="sm", classes="h-full w-full") as box,
          ui.hstack(gap="sm", align="center")):
        ui.avatar(src=f"https://i.pravatar.cc/96?u={node.key}",
                  name=node.label, size="sm")
        with ui.vstack(gap="none", classes="min-w-0"):
            ui.text(node.label, size="sm", weight="medium", truncate=True)
            ui.text(node.group, size="xs", color="muted", truncate=True)
    return box


def org_chart() -> None:
    ui.diagram(
        nodes=[
            ui.node("maya", label="Maya Chen", group="CEO"),
            ui.node("omar", label="Omar Haddad", group="VP Engineering"),
            ui.node("lena", label="Lena Novak", group="VP Sales"),
            ui.node("tom", label="Tom Becker", group="Platform lead"),
            ui.node("ines", label="Inès Moreau", group="Product design"),
            ui.node("sam", label="Sam Okafor", group="Account executive"),
        ],
        edges=[("maya", "omar"), ("maya", "lena"), ("omar", "tom"),
               ("omar", "ines"), ("lena", "sam")],
        direction="down", size="lg", render=person,
    )


def modules() -> list:
    return [
        ui.node("checkout", label="checkout", icon="shopping-bag"),
        ui.node("invoices", label="invoices", icon="file-text"),
        ui.node("reports", label="reports", icon="chart-column"),
        ui.node("pricing", label="pricing", icon="tag"),
        ui.node("tax", label="tax", icon="percent"),
        ui.node("customers", label="customers", icon="users"),
        ui.node("ledger", label="ledger", icon="book-open"),
        ui.node("db", label="db", icon="database"),
    ]


def dependencies() -> list[tuple[str, str]]:
    return [
        ("checkout", "pricing"), ("checkout", "customers"),
        ("invoices", "tax"), ("invoices", "customers"), ("invoices", "ledger"),
        ("reports", "ledger"), ("pricing", "tax"),
        ("customers", "db"), ("ledger", "db"), ("tax", "db"),
    ]


class Explorer(PageState):
    focus: str = field(default="")


def explore(key: str) -> None:
    state = Explorer()
    state.focus = "" if state.focus == key else key


def show_all() -> None:
    Explorer().focus = ""


@refreshable
def dependency_graph() -> None:
    focus = Explorer().focus
    with ui.hstack(justify="between", align="center", wrap=True):
        ui.text(f"Everything that touches {focus}" if focus
                else "Click a module to see its neighbours",
                size="sm", color="muted")
        ui.button("Show all", variant="ghost", size="sm", icon_left="maximize-2",
                  on_click=show_all, disabled=not focus)
    ui.diagram(nodes=modules(), edges=dependencies(), focus=focus or None,
               on_item_click=explore, color="secondary", size="sm")


def explorer() -> None:
    dependency_graph()


def page() -> None:
    page_header("diagram", "Diagram", SUMMARY)
    example("A CI pipeline", pipeline, full=True,
            note="Edges alone are enough: the nodes come from their names, "
                 "and the layers from the direction of the arrows.")
    example("A service map", service_map, full=True,
            note="ui.node adds an icon, a colour and a badge; ui.edge a "
                 "label and a dashed style for what is asynchronous.")
    example("An org chart", org_chart, uses=[person], full=True,
            note="render= draws each node your way. direction=\"down\" "
                 "reads top to bottom.")
    example("Explore a neighbourhood", explorer,
            uses=[modules, dependencies, Explorer, explore, show_all,
                  dependency_graph], full=True,
            note="on_item_click receives the node's key. Setting focus "
                 "narrows the graph to what touches that node.")
