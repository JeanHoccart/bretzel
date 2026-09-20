"""A window — a browser context, its page, what it has seen.

A window is a Playwright context, not a tab: cookies and storage belong
to it, so two windows are two SESSIONS. It is the only way of measuring
what makes a fullstack framework — what one session writes and another
must see.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bretzel.probe._settle import settle_page

#: How long an element is allowed to keep us waiting before the harness
#: declares it will not come. Same order as the hand-written waits in the
#: repository's probes (5 s).
APPEAR_MS = 5000


@dataclass(frozen=True, slots=True)
class Box:
    """Describe an element's geometry in CSS pixels."""

    x: float
    y: float
    width: float
    height: float

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height

    @property
    def center(self) -> tuple[float, float]:
        return self.x + self.width / 2, self.y + self.height / 2


@dataclass(frozen=True, slots=True)
class Seen:
    """A request seen leaving from a window."""

    method: str
    url: str
    kind: str


class ElementNotFoundError(LookupError):
    """Raised when a selector matches no element in a probe window."""


class DropMissedError(AssertionError):
    """Raised when a drag operation does not land on its intended target."""


class Window:
    """Control one browser window during a probe."""

    def __init__(self, page: Any, base_url: str, out: Path, name: str) -> None:
        self.page = page
        self.name = name
        self._base = base_url.rstrip("/")
        self._out = out
        self.errors: list[str] = []
        self.console: list[str] = []
        self.broken: list[str] = []
        self._seen: list[Seen] = []
        self._wire()

    # ── what the window records by itself ─────────────────────────────
    #
    # The old harness merely PRINTED the JS errors, and that cost: 178
    # exceptions lived for two days in an output nobody reads until a
    # test falls. Here we collect, and the final sweep asserts.
    def _wire(self) -> None:
        self.page.on("pageerror", lambda err: self.errors.append(str(err)))
        self.page.on(
            "console",
            lambda msg: (
                self.console.append(f"{msg.type}: {msg.text}")
                if msg.type in ("error", "warning")
                else None
            ),
        )
        self.page.on("request", self._note)
        self.page.on("response", self._note_response)

    def _note_response(self, response: Any) -> None:
        if not response.url.startswith(self._base):
            return
        if response.status >= 400:
            self.broken.append(
                f"{response.status} {response.url[len(self._base):]}"
            )

    def _note(self, request: Any) -> None:
        if not request.url.startswith(self._base):
            return
        # `eventsource` is deliberately excluded: the SSE stream of a
        # `broadcast=` zone never closes, and counting it would make any
        # per-gesture count lie.
        if request.resource_type not in ("fetch", "xhr", "document"):
            return
        self._seen.append(
            Seen(request.method, request.url[len(self._base):], request.resource_type)
        )

    # ── agir ──────────────────────────────────────────────────────────
    def goto(self, path: str) -> None:
        if not path.startswith("/"):
            # Without this refusal, Playwright returns "Cannot navigate
            # to invalid URL" with the full stack. The case happens for
            # real: under Git Bash, a `--route /x` is rewritten to a
            # Windows path before even reaching Python (measured on
            # 2026-09-10).
            raise ValueError(
                f"a route starts with \"/\" — got {path!r}. Under Git "
                "Bash, prefix the command with MSYS_NO_PATHCONV=1."
            )
        # `wait_until="load"` and not `networkidle`: a page carrying a
        # `broadcast=` zone opens an EventSource, so network idleness
        # never happens and the goto expires at 30 s.
        self.page.goto(self._base + path, wait_until="load")
        # `load` has already passed: nothing is debouncing, so the
        # anti-debounce floor would have nothing to cover.
        self.settle(floor=0)

    def click(self, sel: str) -> None:
        self._one(sel).click()

    def type(self, sel: str, text: str) -> None:
        """Type text one key at a time."""
        el = self._one(sel)
        el.click()
        el.press_sequentially(text, delay=15)

    def press(self, keys: str) -> None:
        self.page.keyboard.press(keys)

    def hover(self, sel: str) -> None:
        self._one(sel).hover()

    def drag(self, src: str, dst: str) -> None:
        """Perform a drag with real mouse gestures."""
        mouse = self.page.mouse
        ax, ay = self.box(src).center
        mouse.move(ax, ay)
        mouse.down()
        bx, by = self.box(dst).center
        self._glide(ax, ay, bx, by)
        # The target moved under the gesture: we redo the last segment
        # towards where it is NOW. With no displacement it is a series of
        # moves on the spot, which the engine absorbs.
        cx, cy = self.box(dst).center
        self._glide(bx, by, cx, cy)
        self._assert_landed(dst)
        mouse.up()

    #: Where the element being dragged is, at this instant. The engine
    #: sets ``data-bz-dragging`` when the gesture opens and removes it on
    #: release, so that window is the only one where the question has an
    #: answer.
    _LANDED_JS = """
    (sel) => {
        const item = document.querySelector('[data-bz-dragging]');
        // No NODE drag in progress: a slider's thumb, a `ui.resizable`
        // handle… Nothing to check, and above all nothing to refuse.
        if (!item) return null;
        const target = document.querySelector(sel);
        if (!target) return null;
        const zone = item.closest('[data-bz-dropzone]');
        return {
            ok: target.contains(item),
            zone: zone ? zone.getAttribute('data-bz-dropzone') : null,
        };
    }
    """

    def _assert_landed(self, dst: str) -> None:
        """Just before releasing: is the element INSIDE the target?

        Re-aiming is not enough to guarantee it. It is provable for
        SIBLING zones of one flow — removing the element from its current
        zone shifts the target by one element's height, dropping it there
        makes it grow by as much, and the two cancel out at the edge that
        matters. It stops being provable as soon as the correction
        segment crosses a THIRD zone, which requires an element taller
        than an intermediate zone — a geometry nothing forbids.

        Hence this check rather than an argument: it costs one round trip
        and turns a mute landing into an error that names the harness. It
        is the half re-aiming was missing, and it already existed by hand
        in ``probe_kanban``.
        """
        landed = self.page.evaluate(self._LANDED_JS, dst)
        if landed is None or landed["ok"]:
            return
        self.page.mouse.up()  # never leave a button held down behind us
        raise DropMissedError(
            f"[{self.name}] the drag aimed at {dst!r} and the element is "
            f"in {landed['zone']!r} at release time.\n"
            "The harness aims at the target's CENTRE; a zone that already "
            "carries elements may need a higher point."
        )

    def _glide(self, ax: float, ay: float, bx: float, by: float) -> None:
        """Twelve mouse steps from (ax, ay) to (bx, by)."""
        mouse = self.page.mouse
        steps = 12
        for i in range(1, steps + 1):
            mouse.move(ax + (bx - ax) * i / steps, ay + (by - ay) * i / steps)

    # ── lire ──────────────────────────────────────────────────────────
    def has(self, sel: str) -> bool:
        return self.page.locator(sel).count() > 0

    def count(self, sel: str) -> int:
        return int(self.page.locator(sel).count())

    def text(self, sel: str) -> str:
        return (self._one(sel).inner_text() or "").strip()

    def value(self, sel: str) -> str:
        return str(self._one(sel).input_value())

    def box(self, sel: str) -> Box:
        raw = self._one(sel).bounding_box()
        if raw is None:
            raise ElementNotFoundError(
                f"[{self.name}] {sel!r} exists but has no geometry "
                "(display:none, or detached)."
            )
        return Box(raw["x"], raw["y"], raw["width"], raw["height"])

    def css(self, sel: str, prop: str) -> str:
        return str(
            self._one(sel).evaluate(
                "(el, p) => getComputedStyle(el).getPropertyValue(p)", prop
            )
        )

    def shot(self, name: str) -> Path:
        path = self._out / f"{self.name}-{name}.png"
        self.page.screenshot(path=str(path), full_page=False)
        return path

    # ── attendre ──────────────────────────────────────────────────────
    def settle(self, *, timeout: float = 5.0, floor: int | None = None) -> str:
        return settle_page(
            self.page,
            timeout=timeout,
            **({} if floor is None else {"floor": floor}),
        )

    def resize(self, size: tuple[int, int]) -> None:
        self.page.set_viewport_size({"width": size[0], "height": size[1]})

    def mark(self) -> int:
        """Return the number of requests observed by this window so far."""
        return len(self._seen)

    def since(self, mark: int) -> tuple[Seen, ...]:
        """Return requests observed since ``mark``."""
        return tuple(self._seen[mark:])

    def _one(self, sel: str) -> Any:
        """The first designated element — WAITING for it if it is coming.

        ``count()`` is a snapshot, and a probe nearly always acts on
        something a previous gesture has just brought up. Refusing
        immediately forced every caller to precede its click with a
        hand-written wait: measured while porting ``probe_messagerie`` on
        2026-09-11, six times in a single file, for a button that arrived
        200 ms later.

        It really is a STATE wait, not a duration: it hands back as soon
        as the node is attached. The ceiling is only there to say "it is
        not coming" instead of hanging.

        ⚠️ It holds ONLY for the elements one acts on or reads.
        :meth:`has` and :meth:`count` query the DOM directly, and must do
        so: a wait would make them lie about an absence, which is often
        what is being measured.
        """
        # Deferred import, like ``_browser``: Playwright is a
        # development extra, and ``import bretzel.probe`` must not depend
        # on it. We catch the timeout ALONE — a malformed selector must
        # raise as-is, not disguise itself as "nothing matches".
        from playwright.sync_api import TimeoutError as PlaywrightTimeout

        loc = self.page.locator(sel).first
        try:
            loc.wait_for(state="attached", timeout=APPEAR_MS)
        except PlaywrightTimeout as exc:
            raise ElementNotFoundError(
                f"[{self.name}] nothing matches {sel!r} after "
                f"{APPEAR_MS / 1000:g} s."
            ) from exc
        return loc
