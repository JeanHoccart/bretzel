"""Record, then compare, the HTML the framework produces — byte for byte.

The guard of a speed-up: an optimisation that changes a single byte of
output does not pass. Two corpora, rendered in-process:

- **the catalogue**: every public component, built bare by the shared
  table (``tests/consistency/_discovery.rendered_html_of``);
- **the example apps**: every page of ``examples/*/main.py`` that takes
  no path parameter, fetched with ``GET`` (an app that redirects to its
  login gives its login page — still a render).

What varies by run is masked: signatures and render timestamps, page
identities, CSRF tokens. The rest must not move. Run it twice before a
change: a page that differs between two identical runs is reported as
unstable and left out, rather than blamed on the change.

::

    python -m tests.perf.html_snapshot record /tmp/before
    # … the optimisation …
    python -m tests.perf.html_snapshot compare /tmp/before
"""

from __future__ import annotations

import importlib
import json
import re
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

_REPO = Path(__file__).resolve().parents[2]

#: What legitimately changes between two renders of the same thing.
_VOLATILE = [
    (re.compile(r'data-bz-sig="[0-9a-f]+"'), 'data-bz-sig="·"'),
    (re.compile(r'data-bz-ts="\d+"'), 'data-bz-ts="·"'),
    # A zone's fingerprint counts the render timestamp's window: it moves
    # with the clock. What it summarises is compared byte for byte anyway.
    (re.compile(r'data-bz-h="[0-9a-f]+"'), 'data-bz-h="·"'),
    (re.compile(r"bz-page-[0-9a-f-]{8,}"), "bz-page-·"),
    (re.compile(r'"(page_id|pageId|page)"\s*:\s*"[0-9a-f-]{8,}"'), r'"\1":"·"'),
    (re.compile(r'(name="_csrf"[^>]*value=")[^"]+'), r"\1·"),
    (re.compile(r'(csrf[^"]*"\s*:\s*")[^"]+'), r"\1·"),
    (re.compile(r'(content=")[A-Za-z0-9_\-]{20,}(")'), r"\1·\2"),
    (re.compile(r"\?h=[0-9a-f]+"), "?h=·"),
    (re.compile(r'(tab=)[0-9a-f-]{8,}'), r"\1·"),
    # Page identities (``data-bretzel-page-id``, the ``X-Bretzel-Page-ID``
    # header in ``hx-headers``…): any 32-hex or dashed UUID token.
    (re.compile(r"\b[0-9a-f]{8}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{12}\b"), "·"),
]


def _mask(html: str) -> str:
    for pattern, repl in _VOLATILE:
        html = pattern.sub(repl, html)
    return html


def _catalogue() -> dict[str, str]:
    from tests.consistency._discovery import public_component_classes, rendered_html_of

    out = {}
    for cls in public_component_classes():
        html = rendered_html_of(cls)
        if html is not None:
            out[f"component/{cls.__name__}"] = _mask(html)
    return out


def _examples() -> dict[str, str]:
    from starlette.testclient import TestClient

    out: dict[str, str] = {}
    for main in sorted((_REPO / "examples").glob("*/main.py")):
        name = main.parent.name
        try:
            module = importlib.import_module(f"examples.{name}.main")
        except Exception as exc:  # an example that needs a service: say so
            out[f"example/{name}"] = f"<import failed: {type(exc).__name__}>"
            continue
        app = getattr(module, "app", None)
        if app is None:
            continue
        with TestClient(app) as client:
            for fn in list(app._pages):
                meta = fn._bz_page
                path = getattr(meta, "path", "")
                if not path or "{" in path:
                    continue
                response = client.get(path, follow_redirects=True)
                out[f"example/{name}{path}"] = f"{response.status_code}\n{_mask(response.text)}"
    return out


def snapshot() -> dict[str, str]:
    return {**_catalogue(), **_examples()}


def main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[1] not in ("record", "compare"):
        print(__doc__)
        return 2
    target = Path(argv[2])
    if argv[1] == "record":
        first, second = snapshot(), snapshot()
        unstable = sorted(k for k in first if first.get(k) != second.get(k))
        target.mkdir(parents=True, exist_ok=True)
        stable = {k: v for k, v in first.items() if k not in unstable}
        (target / "snapshot.json").write_text(json.dumps(stable, indent=0, sort_keys=True))
        print(f"recorded {len(stable)} renders, {len(unstable)} unstable left out: {unstable}")
        return 0
    before = json.loads((target / "snapshot.json").read_text())
    now = snapshot()
    changed = sorted(k for k in before if now.get(k) != before[k])
    for key in changed[:10]:
        a, b = before[key], now.get(key, "<missing>")
        i = next((n for n, (x, y) in enumerate(zip(a, b, strict=False)) if x != y), min(len(a), len(b)))
        print(f"✗ {key}\n    before: …{a[max(0, i - 80):i + 120]!r}\n    now:    …{b[max(0, i - 80):i + 120]!r}")
    print(f"{len(before) - len(changed)}/{len(before)} identical")
    return 1 if changed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
