# A JSON route beside a page

> A page that lists our products, and a JSON endpoint /api/products that returns the same list.

Save it as `app.py`, run `bretzel dev app:app`, then open http://127.0.0.1:8000 and http://127.0.0.1:8000/api/products.

```python
"""A page that lists products, and the same list as JSON at /api/products."""

import sys

from bretzel import Bretzel, page, ui


def products() -> list[dict]:
    """The one source both read. In a real app: a query."""
    return [
        {"sku": "MUG-01", "name": "Coffee mug", "price": 12.5},
        {"sku": "TEE-02", "name": "T-shirt", "price": 24.0},
        {"sku": "CAP-03", "name": "Cap", "price": 18.0},
        {"sku": "BAG-04", "name": "Tote bag", "price": 15.0},
    ]


def price_cell(value, row: dict) -> str:
    return f"{value:.2f} EUR"


@page("/", title="Products")
def home() -> None:
    with ui.container(width="md", classes="py-8"), ui.vstack(gap="lg"):
        ui.heading("Products", level=1)
        ui.table(
            columns=[
                ui.column("name", label="Product"),
                ui.column("sku", label="Reference"),
                ui.column("price", label="Price", align="right", render=price_cell),
            ],
            rows=products(),
            row_key="sku",
        )
        ui.link("The same list in JSON", href="/api/products", external=True)


app = Bretzel(title="Products")


@app.fastapi.get("/api/products")
def api_products() -> list[dict]:
    return products()


app.include(sys.modules[__name__])
```

## Why it works

- `app.fastapi` is the FastAPI app Bretzel serves: a JSON route is declared on it exactly as in FastAPI, and FastAPI turns what it returns into JSON.
- The page and the route both call `products()`: one source, so the screen and the JSON never disagree.
- An error stays FastAPI's: `raise HTTPException(404, "No such product")` answers `{"detail": "No such product"}` to a program, and the app's error page to a browser.
- **The trap: a page is for people, a route for programs.** A `@page` always answers HTML; data for another program goes through `app.fastapi`. `Bretzel(api_docs=True)` lists these routes at `/docs`.
