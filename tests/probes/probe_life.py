"""Probe — ``examples/life`` computes on the server and draws in the browser.

What it measures, and why ``TestClient`` cannot
-----------------------------------------------
The board is coloured by ``bz-class`` bindings on a client state that the
server rewrites: the SSR holds no live cell at all. Only a browser shows
whether a generation lands, whether Play really ticks five times a
second, whether Pause really stops, and what one tick costs on the wire.

- Step from the glider gun gives exactly what :func:`next_generation`
  computes in Python — the rule, end to end;
- a click flips one cell, for one request;
- Play advances several generations a second, each tick a small answer
  (the board is never re-rendered);
- Pause stops, Random fills about a quarter, Clear empties;
- live cells contrast with dead ones in both themes, every grid line is
  one pixel, and the board fits a 1280 × 700 window.

Run :  py tests/probes/probe_life.py
       py -m pytest tests/probes/test_probes.py -m probes -k life
"""

from __future__ import annotations

import re
import sys
from itertools import pairwise

from playwright.sync_api import TimeoutError as PlaywrightTimeout

from bretzel.probe import Probe, Window, probe
from examples.life.features.board import (
    CELLS,
    LIVE,
    SIZE,
    glider_gun,
    next_generation,
)

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

APP = "examples.life.main:app"

CELL = "[hx-post$='::toggle']"
CELLS_JS = f'[...document.querySelectorAll("{CELL}")]'

ALIVE_JS = f"""() => {CELLS_JS}
    .flatMap((c, i) => c.classList.contains('{LIVE}') ? [i] : [])"""

# An expression, not a function : ``becomes_true`` waits on it too.
GENERATION_EXPR = """Number([...document.querySelectorAll('span')]
    .find(s => s.textContent.trim() === 'Generation')
    .nextElementSibling.textContent.trim())"""

COLOURS_JS = f"""() => {{
    const cells = {CELLS_JS};
    const live = cells.find(c => c.classList.contains('{LIVE}'));
    const dead = cells.find(c => !c.classList.contains('{LIVE}'));
    return [live, dead].map(c => getComputedStyle(c).backgroundColor);
}}"""

FIRST_ROW_X_JS = f"""() => {CELLS_JS}.slice(0, {SIZE})
    .map(c => c.getBoundingClientRect().x)"""

STEP_SIZES_JS = """() => performance.getEntriesByType('resource')
    .filter(e => e.name.includes('::step'))
    .map(e => e.encodedBodySize)"""


def alive(w: Window) -> set[int]:
    return set(w.page.evaluate(ALIVE_JS))


def generation(w: Window) -> int:
    return int(w.page.evaluate(GENERATION_EXPR))


def button(name: str) -> str:
    return f'role=button[name="{name}"]'


def becomes_true(w: Window, expr: str, *, timeout: int = 5000) -> bool:
    """True as soon as ``expr`` holds, False at the timeout."""
    try:
        w.page.wait_for_function(expr, timeout=timeout)
    except PlaywrightTimeout:
        return False
    return True


def contrast(a: str, b: str) -> float:
    """WCAG contrast ratio of two ``rgb()`` colours."""
    def luminance(colour: str) -> float:
        channels = [int(v) / 255 for v in re.findall(r"\d+", colour)[:3]]
        lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
               for c in channels]
        return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def first_render(p: Probe, a: Window) -> None:
    p.check("1 600 cells", a.count(CELL) == CELLS, a.count(CELL))
    gun, drawn = set(glider_gun()), alive(a)
    p.check("the glider gun is drawn", drawn == gun, sorted(drawn ^ gun)[:10])
    gen = generation(a)
    p.check("generation 0", gen == 0, gen)
    a.shot("gun")


def colours_and_sizes(p: Probe, a: Window) -> None:
    for theme in ("light", "dark"):
        a.page.emulate_media(color_scheme=theme)
        live, dead = a.page.evaluate(COLOURS_JS)
        ratio = contrast(live, dead)
        p.check(f"[{theme}] live cells contrast with dead ones (≥ 3:1)",
                ratio >= 3, f"{ratio:.2f} — {live} / {dead}")
    a.page.emulate_media(color_scheme="light")

    cell = a.box(CELL)
    p.check("a cell is square", abs(cell.width - cell.height) < 0.5, cell)
    p.check("a cell is at least 8 px", cell.width >= 8, cell.width)
    xs = a.page.evaluate(FIRST_ROW_X_JS)
    pitches = {round(b - x, 2) for x, b in pairwise(xs)}
    p.check("every grid line is one pixel (one pitch)", len(pitches) == 1, pitches)
    controls = a.box(button("Clear"))
    p.check(
        "the controls fit a 1280 × 700 window",
        controls.bottom <= 700,
        f"bottom at {controls.bottom:.0f}",
    )


def one_step(p: Probe, a: Window) -> None:
    expected = next_generation(set(glider_gun()))
    with p.requests() as net:
        a.click(button("Step"))
    p.check("Step costs one request", net.total == 1, net)
    drawn, gen = alive(a), generation(a)
    p.check("Step gives the next generation", drawn == expected,
            sorted(drawn ^ expected)[:10])
    p.check("generation 1", gen == 1, gen)


def flip_a_cell(p: Probe, a: Window) -> None:
    last = f"{CELL} >> nth={CELLS - 1}"
    with p.requests() as net:
        a.click(last)
    p.check("a click costs one request", net.total == 1, net)
    p.check("a click brings a cell to life", CELLS - 1 in alive(a))
    a.click(last)
    a.settle()
    p.check("a second click kills it", CELLS - 1 not in alive(a))


def play_and_pause(p: Probe, a: Window) -> None:
    before = generation(a)
    mark = a.mark()
    a.click(button("Play"))
    p.check("Play advances at least 6 generations in 2 s",
            becomes_true(a, f"{GENERATION_EXPR} >= {before + 6}", timeout=2000),
            f"{generation(a) - before} generations")
    a.shot("playing")
    a.click(button("Pause"))
    a.settle()   # the tick in flight at Pause may still land
    stopped = generation(a)
    ticks = sum(1 for s in a.since(mark) if "::step" in s.url)
    p.check("one request per generation", ticks == stopped - before,
            f"{ticks} ticks for {stopped - before} generations")
    p.hold(0.5)   # 2.5 ticks : long enough for a running interval to show
    later = generation(a)
    p.check("Pause stops", later == stopped, f"{stopped} → {later}")
    sizes = a.page.evaluate(STEP_SIZES_JS)
    p.check("a tick answers under 20 kB (the board is not re-rendered)",
            sizes and max(sizes) < 20_000, f"max {max(sizes, default=0)} B")


def random_and_clear(p: Probe, a: Window) -> None:
    a.click(button("Random"))
    p.check("Random fills about a quarter",
            becomes_true(a, f"({ALIVE_JS})().length > 250"), len(alive(a)))
    a.settle()
    gen, count = generation(a), len(alive(a))
    p.check("Random restarts at generation 0", gen == 0, gen)
    p.check("and no more than a third", count < CELLS / 3, count)
    a.click(button("Clear"))
    p.check("Clear empties the board",
            becomes_true(a, f"({ALIVE_JS})().length === 0"), len(alive(a)))


def main() -> None:
    with probe(APP) as p:
        (a,) = p.windows
        a.goto("/")
        first_render(p, a)
        colours_and_sizes(p, a)
        one_step(p, a)
        flip_a_cell(p, a)
        play_and_pause(p, a)
        random_and_clear(p, a)


# No ``test_*`` function here : ``tests/probes/test_probes.py`` runs
# every probe in a subprocess and judges its exit code.
if __name__ == "__main__":
    main()
