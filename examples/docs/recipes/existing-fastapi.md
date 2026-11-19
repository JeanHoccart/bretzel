# Add screens to a FastAPI app

> I already have a FastAPI app with GET and POST /api/books. Add Bretzel screens to it without breaking the API.

Keep your FastAPI module as it is. Below, it sits at the top of the file so the recipe runs on its own; in your project, replace that part with `from books import api, list_books`. Save it as `app.py` and run `bretzel dev app:app`: the server now runs `app`, no longer `api`.

```python
"""Bretzel screens added to an existing FastAPI app, whose API stays as it was."""

import sys

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from bretzel import Bretzel, page, ui

# -- The existing FastAPI app, unchanged ---------------------------------

api = FastAPI(title="Books API")

BOOKS = [
    {"id": 1, "title": "Dune", "author": "Frank Herbert"},
    {"id": 2, "title": "Emma", "author": "Jane Austen"},
]


class BookIn(BaseModel):
    title: str
    author: str


@api.get("/api/books")
def list_books() -> list[dict]:
    return BOOKS


@api.get("/api/books/{book_id}")
def get_book(book_id: int) -> dict:
    for book in BOOKS:
        if book["id"] == book_id:
            return book
    raise HTTPException(status_code=404, detail="Book not found")


@api.post("/api/books", status_code=201)
def create_book(book: BookIn) -> dict:
    created = {"id": max(b["id"] for b in BOOKS) + 1, **book.model_dump()}
    BOOKS.append(created)
    return created


# -- The Bretzel screens, added beside it --------------------------------

@page("/", title="Books")
def books_page() -> None:
    with ui.container(width="md", classes="py-8"), ui.vstack(gap="lg"):
        ui.heading("Books", level=1)
        ui.table(
            columns=[ui.column("title", label="Title"), ui.column("author", label="Author")],
            rows=list_books(),
            row_key="id",
        )


app = Bretzel(title="Books")
app.fastapi.include_router(api.router)
app.include(sys.modules[__name__])
```

## Why it works

- `app.fastapi.include_router(api.router)` puts every route of the existing app on the FastAPI app Bretzel serves, with its own `/docs` and `/openapi.json`, which still describe the books API.
- The API answers as before: a program that sends no cookie (`curl`, another service) writes without a CSRF token, and an error stays FastAPI's JSON, `{"detail": "Book not found"}`, for any client that does not ask for HTML.
- A program that keeps cookies (a `requests.Session` that fetched a page first) needs the token like a browser: send no cookie, use an `Authorization: Bearer` token, or echo the `X-Bretzel-CSRF` token of its session. Refused, it reads why in a JSON `detail`.
- The screen calls `list_books()` like any Python function: one source for the page and the API.
- **The trap: `include_router` takes the routes, nothing else.** The existing app's middleware, exception handlers and startup hooks stay behind: declare them again on `app.fastapi`. And leave out `api_docs=True`: the existing `/docs` already answers, and Bretzel's would sit behind it.
