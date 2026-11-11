"""``bretzel features`` and ``bretzel impact`` — the contracts, asked.

Two questions an assistant otherwise answers with ``grep``:

- **where is what, and what is wrong with the contracts** — the map of
  the app's features, then what to fix (``uses`` that lie, a public
  symbol nothing uses, a symbol taken from a feature that does not expose
  it);
- **what does a change touch** — the features importing a file's
  feature, directly or not, their pages, the probes that visit them: the
  checks to run before committing.

Both import the app (``module:attribute``, like ``check --deep``) and
read what :mod:`bretzel.server.feature_audit` derives from it.
"""

from __future__ import annotations

import json
from pathlib import Path


def _features(target: str):
    from bretzel.introspect._target import load_target

    app, origin = load_target(target)
    features = list(getattr(app, "features", ()))
    if not features:
        raise ValueError(f"`{target}` exposes no `Feature`: there is no contract to read.")
    return features, origin.resolve().parent


def _topics(root: Path) -> list[dict]:
    """Each ``Topic`` of the app, and the functions reading and writing it."""
    from bretzel.lint.corpus import modules
    from bretzel.lint.rules.topics import topics_in

    uses = topics_in(modules([root]))
    return [{"topic": name, "reads": sorted(use.readers), "writes": sorted(use.writers)}
            for name, use in sorted(uses.items())]


def run_features(target: str, *, as_json: bool = False) -> int:
    from bretzel.server.feature_audit import describe_features, findings

    features, root = _features(target)
    rows = describe_features(features)
    problems = findings(features, root)
    topics = _topics(root)
    if as_json:
        print(json.dumps({"features": rows, "topics": topics, "to_fix": problems},
                         ensure_ascii=False, indent=2))
        return 0
    pages = sum(len(r["routes"]) for r in rows)
    print(f"{target} — {len(rows)} features, {pages} pages\n")
    for row in sorted(rows, key=lambda r: r["name"]):
        file = Path(row["file"]).resolve()
        where = file.relative_to(root).as_posix() if file.is_relative_to(root) else str(file)
        print(f"{row['name']} · {row['kind']} — {where}")
        if row["summary"]:
            print(f"  {row['summary']}")
        for label, values in (("routes", row["routes"]), ("exposes", row["provides"]),
                              ("imports", row["imports"]), ("used by", row["used_by"])):
            if values:
                print(f"  {label:<8}{', '.join(values)}")
        print()
    if topics:
        print(f"Topics ({len(topics)})")
        for topic in topics:
            print(f"  {topic['topic']}")
            print(f"    read by     {', '.join(topic['reads']) or '(nothing)'}")
            print(f"    written by  {', '.join(topic['writes']) or '(nothing)'}")
        print()
    if problems:
        print(f"To fix ({len(problems)})")
        for line in problems:
            print(f"  - {line}")
    else:
        print("To fix: nothing — the contracts say what the code does.")
    return 0


def run_impact(target: str, files: list[str], *, probes: str | None = None,
               as_json: bool = False) -> int:
    from bretzel.server.feature_audit import impact

    features, root = _features(target)
    probes_dir = Path(probes) if probes else root / "tests" / "probes"
    found = impact(features, [Path(f) for f in files], probes_dir)
    if as_json:
        print(json.dumps({
            "touched": found.touched, "affected": found.affected,
            "routes": [{"route": r, "feature": f} for r, f in found.routes],
            "probes": [{"probe": p, "covers": c} for p, c in found.probes],
            "unowned": found.unowned,
        }, ensure_ascii=False, indent=2))
        return 0
    if found.unowned:
        print(f"Owned by no feature: {', '.join(found.unowned)}")
    if not found.touched:
        print("No feature owns these files: nothing to follow.")
        return 0
    others = [a for a in found.affected if a not in found.touched]
    print(f"{', '.join(found.touched)} — and through the imports: "
          f"{', '.join(others) if others else 'nothing else'}")
    if found.routes:
        print("\nPages")
        for route, feature in found.routes:
            print(f"  {route}  ({feature})")
    if found.probes:
        rel = probes_dir.resolve().relative_to(root).as_posix() \
            if probes_dir.resolve().is_relative_to(root) else str(probes_dir)
        print(f"\nProbes to run ({rel})")
        for probe, covers in found.probes:
            print(f"  {probe}  — {', '.join(covers)}")
    elif probes_dir.is_dir():
        print(f"\nNo probe in {probes_dir} visits these pages.")
    return 0
