"""Create, run, describe, check, and probe a Bretzel application.

The scaffold does not claim to decide a large application's
architecture: it only fixes the smallest public, documented path,
``main`` plus one feature. That is precisely the path installation and
CI exercise.

Each command answers a concrete question:

- ``bretzel new`` — creates the smallest complete application, never
  merging with an existing folder.
- ``bretzel dev`` — imports an app and restarts it on every change.

- ``bretzel describe`` — the index of the whole surface, or one symbol's
  card: a component, a module, or any public name (``page``,
  ``PageState``, ``ClientBinding``, ``ROUTE_ACTION``). Text output by
  default, ``--json`` for a consumer.
- ``bretzel check`` — runs the rules over application code. Exit code 1
  when there is a finding, so a pre-commit hook or a CI can use it.
- ``bretzel probe`` — drives a RUNNING app in a real browser and returns
  a single verdict block. The first two read text; this one is the only
  one that looks at what the user sees. Requires the ``bretzel[probe]``
  extra.

``argparse`` and not a dependency: the CLI does not justify widening the
framework's installation surface for three subcommands.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path


def _new(args: argparse.Namespace) -> int:
    from bretzel.cli.commands.project import create_project

    destination = Path(args.directory or args.name)
    create_project(destination, display_name=args.name)
    print(f"Application created in {destination.resolve()}")
    print(f"  cd {destination}")
    print("  python -m pip install -e .")
    print("  bretzel dev")
    return 0


def _dev(args: argparse.Namespace) -> int:
    from bretzel.cli.commands.project import run_project

    run_project(
        args.target,
        host=args.host,
        port=args.port,
        reload=not args.no_reload,
        watch_dir=Path.cwd(),
    )
    return 0


def _describe(args: argparse.Namespace) -> int:
    from bretzel.introspect import describe, index

    if args.theme:
        # Before anything else: `--theme` answers a DIFFERENT question
        # from the card, and without a name it has nobody to ask.
        if args.symbol is None:
            print(
                "`--theme` requires a component: `describe button --theme`.",
                file=sys.stderr,
            )
            return 2
        from bretzel.introspect import theme_sheet

        try:
            print(theme_sheet(args.symbol))
        except KeyError as exc:
            print(str(exc).strip("\"'"), file=sys.stderr)
            return 2
        return 0

    if args.symbol is None:
        if args.json:
            from bretzel.introspect import SCHEMA_VERSION, describe_components

            payload = {
                "schema_version": SCHEMA_VERSION,
                "symbols": [dataclasses.asdict(i) for i in describe_components()],
            }
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(index())
        return 0

    try:
        if args.json:
            print(json.dumps(_as_dict(args.symbol), ensure_ascii=False, indent=2))
        else:
            print(describe(args.symbol))
    except (KeyError, AttributeError) as exc:
        print(str(exc).strip("\"'"), file=sys.stderr)
        return 2
    return 0


def _as_dict(name: str) -> dict:
    """A symbol's card in JSON — the SAME resolution as the text.

    "Same" in the literal sense: both call
    :func:`~bretzel.introspect.resolve`. A second resolution ladder
    written here had already diverged — it ignored the module tier, so
    ``describe bretzel.core --json`` raised and
    ``describe bretzel.state --json`` answered another symbol's card.

    The payload carries its version: without it, a consumer reading this
    output has no way of knowing the shape has moved, which is precisely
    what :data:`~bretzel.introspect.SCHEMA_VERSION` exists to say.
    """
    from bretzel.introspect import SCHEMA_VERSION, resolve

    found = resolve(name)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": type(found).__name__,
        "symbol": dataclasses.asdict(found),
    }


def _check(args: argparse.Namespace) -> int:
    from bretzel.lint import available_rules, run, run_deep

    if args.deep:
        target = args.paths[0] if args.paths else ""
        report = run_deep(target)
        print(report.format(root=Path.cwd()))
        return report.exit_code

    if "?" in args.rule:
        for name in available_rules():
            print(name)
        return 0

    paths = [Path(p) for p in args.paths] or [Path.cwd()]
    missing = [p for p in paths if not p.exists()]
    if missing:
        print(
            f"path(s) not found: {', '.join(p.as_posix() for p in missing)}",
            file=sys.stderr,
        )
        return 2

    report = run(paths, rules=tuple(args.rule) or None)
    print(report.format(root=Path.cwd()))
    return report.exit_code


def _probe(args: argparse.Namespace) -> int:
    """Drive a running app and return a single verdict block.

    With no scenario, only the **sweep** runs — which is possible only
    because the framework knows the app's routes, and that is the
    concrete gain of being "native".
    """
    try:
        from bretzel.probe import ProbeFailedError, probe
    except ImportError as exc:  # pragma: no cover — needs the extra
        print(
            "`bretzel probe` requires the optional dependency: "
            "pip install bretzel[probe]\n"
            f"({exc})",
            file=sys.stderr,
        )
        return 2

    # ⚠️ ONE probe PER ROUTE, and not a loop of navigations in a single
    # one. The sweep runs when the ``with`` exits and measures the page
    # each window is on AT THAT POINT: an inner loop therefore loaded
    # three routes to measure only one, the last. A flag that makes you
    # pay for three navigations for one verdict lies about what it does.
    worst = 0
    for route in args.route or ["/"]:
        try:
            with probe(
                args.target,
                windows=args.windows,
                size=args.size,
                headed=args.headed,
                out=args.out,
                serve="subprocess" if args.subprocess else "thread",
            ) as p:
                for window in p.windows:
                    window.goto(route)
        except ProbeFailedError:
            worst = 1
    return worst


def _parse_size(raw: str) -> tuple[int, int]:
    """``1280x700`` → ``(1280, 700)``. Passed as ``type=`` to argparse.

    It is argparse that must raise: it turns a ``ValueError`` from
    ``type=`` into a usage message, where a hand-written call would let
    it surface as a full traceback.
    """
    width, _, height = raw.lower().partition("x")
    if not width.isdigit() or not height.isdigit():
        raise ValueError(f"invalid size: {raw!r} — expected '1280x700'")
    return int(width), int(height)


def _force_utf8_output() -> None:
    """Write UTF-8 whatever the console.

    Without this, ``bretzel describe button`` **failed** on a Windows
    console: the default output there is ``cp1252``, and a component's
    card carries an arrow ``→`` in its title. Every card being built
    around that arrow, the CLI's most useful command returned nothing on
    the project's main development platform — with nothing saying so,
    the error being caught as "exit code 2".

    ``errors="replace"`` as a second step: on a console genuinely
    incapable of UTF-8, a card with a few ``?`` is better than an
    encoding exception.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bretzel",
        description="Bretzel — a self-describing framework with built-in application checks.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    new = sub.add_parser("new", help="create a small application ready to run")
    new.add_argument("name", help="application display name")
    new.add_argument(
        "--directory", "-d", default=None,
        help="directory to create (default: the application name)",
    )
    new.set_defaults(func=_new)

    dev = sub.add_parser("dev", help="run an application with automatic reload")
    dev.add_argument(
        "target", nargs="?", default="app.main:app",
        help="ASGI target (default: app.main:app)",
    )
    dev.add_argument("--host", default="127.0.0.1")
    dev.add_argument("--port", type=int, default=8000)
    dev.add_argument(
        "--no-reload", action="store_true",
        help="run a single process without watching files",
    )
    dev.set_defaults(func=_dev)

    desc = sub.add_parser(
        "describe",
        help="show the public API or describe a symbol",
        description=(
            "Without an argument, show a compact one-line-per-symbol index. "
            "With a name, show the complete symbol description."
        ),
    )
    desc.add_argument(
        "symbol",
        nargs="?",
        help="a component (`button`), symbol (`page`, `PageState`, "
        "`ROUTE_ACTION`), or module (`bretzel.state`)",
    )
    desc.add_argument("--json", action="store_true", help="machine-readable output")
    desc.add_argument(
        "--theme",
        action="store_true",
        help="show the component theme table: each tier's shape, the complete "
        "default tier, and the names of the other tiers",
    )
    desc.set_defaults(func=_describe)

    chk = sub.add_parser(
        "check",
        help="check application code against Bretzel's rules",
        description=(
            "Static by default: only the AST is inspected and no application "
            "code is executed. `--deep` imports the app to inspect its route "
            "map and therefore executes application code."
        ),
    )
    chk.add_argument("paths", nargs="*", help="files or directories (default: .)")
    chk.add_argument(
        "--rule",
        action="append",
        default=[],
        metavar="NAME",
        help="run only this rule (repeatable); `--rule ?` lists available rules",
    )
    chk.add_argument(
        "--deep",
        action="store_true",
        help="inspect the route map of a loaded app (`module:attribute`); executes its code",
    )
    chk.set_defaults(func=_check)

    prb = sub.add_parser(
        "probe",
        help="probe a running app in a real browser",
        description=(
            "Serve the app on a free port, open one or more browser windows, "
            "scan for overflow, keyboard navigation, JavaScript errors, failed "
            "requests, a second viewport size, and both themes, then print one "
            "verdict block. Returns a non-zero status if any check fails. "
            "Requires: pip install bretzel[probe]"
        ),
    )
    prb.add_argument("target", help="application to probe (`module:attribute`)")
    prb.add_argument(
        "--route",
        action="append",
        default=[],
        metavar="PATH",
        help="route to visit (repeatable; default: /)",
    )
    prb.add_argument(
        "--windows", type=int, default=1,
        help="number of windows (separate browser contexts and sessions)",
    )
    prb.add_argument(
        "--size", default=(1280, 700), type=_parse_size,
        help="viewport size (default: 1280x700, the smallest plausible size)",
    )
    prb.add_argument("--headed", action="store_true", help="show the browser window")
    prb.add_argument("--out", default=None, metavar="DIRECTORY", help="screenshot directory")
    prb.add_argument(
        "--subprocess",
        action="store_true",
        help="serve the app in another process (live state inspection is unavailable)",
    )
    prb.set_defaults(func=_probe)
    return parser


def main(argv: list[str] | None = None) -> int:
    _force_utf8_output()
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except (NotImplementedError, KeyError, ValueError, ImportError) as exc:
        print(str(exc).strip("\"'"), file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover — entry point
    raise SystemExit(main())
