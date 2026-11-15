"""TagsInput playground — the server handlers the cards wire."""

import unicodedata

from examples.playground.features.tags_input.state import (
    CONTACTS,
    AddressSearch,
    TagsInputEvents,
    TagsInputPlayground,
)


def fold(text: str) -> str:
    """Lower case, accents dropped: « Hélène » is found by « helene »."""
    return "".join(c for c in unicodedata.normalize("NFD", text.casefold())
                   if not unicodedata.combining(c))


def matching_contacts(query: str) -> list[tuple[str, str]]:
    """The address book's entries whose name or address holds every word."""
    words = fold(query).split()
    return [(address, name) for address, name in CONTACTS
            if all(w in fold(f"{name} {address}") for w in words)]


def search_addresses(query: str = "") -> None:
    AddressSearch().query = query


def log(name: str) -> None:
    state = TagsInputEvents()
    state.log = [*state.log, name]


def log_change(value: str = "") -> None: log(f"change(value={value!r})")
def log_focus() -> None: log("focus")
def log_blur() -> None: log("blur")
def log_search(query: str = "") -> None:
    if query:
        log(f"search(query={query!r})")


def clear_log() -> None:
    TagsInputEvents().log = []


def server_changed(state: TagsInputPlayground) -> None:
    pass
