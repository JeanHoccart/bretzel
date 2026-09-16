"""Create, run, describe, check, and probe a Bretzel application.

Le scaffold ne prétend pas décider de l'architecture d'une grande application :
il fige seulement le plus petit trajet public et documenté, ``main`` + une
feature. C'est précisément le trajet que l'installation et la CI exercent.

Les commandes répondent chacune à une question concrète :

- ``bretzel new`` — crée la plus petite application complète, sans jamais
  fusionner avec un dossier existant.
- ``bretzel dev`` — importe une app et la relance à chaque modification.

- ``bretzel describe`` — l'index de toute la surface, ou la fiche d'un
  symbole : un composant, un module, ou n'importe quel nom public
  (``page``, ``PageState``, ``ClientBinding``, ``ROUTE_ACTION``).
  Sortie texte par défaut, ``--json`` pour un consommateur.
- ``bretzel check`` — passe les règles sur du code applicatif. Code de
  sortie 1 s'il y a un constat, pour qu'un pre-commit ou une CI puisse
  s'en servir.
- ``bretzel probe`` — pilote une app EN MARCHE dans un vrai navigateur
  et rend un bloc de verdict unique. Les deux premières lisent du
  texte ; celle-ci est la seule qui regarde ce que l'utilisateur voit.
  Demande l'extra ``bretzel[probe]``.

``argparse`` et non une dépendance : le CLI ne justifie pas d'élargir la
surface d'installation du framework pour trois sous-commandes.
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
        # Avant tout le reste : `--theme` répond à une AUTRE question que
        # la fiche, et sans un nom il n'a personne à interroger.
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
    """La fiche d'un symbole en JSON — la MÊME résolution que le texte.

    « Même » au sens propre : les deux appellent
    :func:`~bretzel.introspect.resolve`. Une seconde échelle de
    résolution écrite ici avait déjà divergé — elle ignorait l'étage
    module, donc ``describe bretzel.core --json`` levait et
    ``describe bretzel.state --json`` répondait la fiche d'un autre
    symbole.

    Le payload porte sa version : sans elle, un consommateur qui lit
    cette sortie n'a aucun moyen de savoir que la forme a bougé, ce qui
    est précisément ce que :data:`~bretzel.introspect.SCHEMA_VERSION`
    existe pour dire.
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
    """Piloter une app en marche et rendre un seul bloc de verdict.

    Sans scénario, on ne lance que le **balayage** — c'est possible
    uniquement parce que le framework connaît les routes de l'app, et
    c'est le gain concret du « natif ».
    """
    try:
        from bretzel.probe import ProbeFailedError, probe
    except ImportError as exc:  # pragma: no cover — dépend de l'extra
        print(
            "`bretzel probe` requires the optional dependency: "
            "pip install bretzel[probe]\n"
            f"({exc})",
            file=sys.stderr,
        )
        return 2

    # ⚠️ UN probe PAR ROUTE, et pas une boucle de navigations dans un
    # seul. Le balayage tourne à la sortie du ``with`` et mesure la page
    # où chaque fenêtre se trouve ALORS : une boucle interne chargeait
    # donc trois routes pour n'en mesurer qu'une, la dernière. Un drapeau
    # qui fait payer trois navigations pour un verdict ment sur ce qu'il
    # fait.
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
    """``1280x700`` → ``(1280, 700)``. Passé en ``type=`` à argparse.

    C'est argparse qui doit lever : il transforme une ``ValueError`` de
    ``type=`` en message d'usage, là où un appel à la main la laisse
    remonter en pile complète.
    """
    width, _, height = raw.lower().partition("x")
    if not width.isdigit() or not height.isdigit():
        raise ValueError(f"invalid size: {raw!r} — expected '1280x700'")
    return int(width), int(height)


def _force_utf8_output() -> None:
    """Écrire en UTF-8 quelle que soit la console.

    Sans ceci, ``bretzel describe button`` **échouait** sur une console
    Windows : la sortie par défaut y est en ``cp1252``, et la fiche
    d'un composant porte une flèche ``→`` dans son titre. Toutes les
    fiches étant construites autour de cette flèche, la commande la plus
    utile du CLI ne rendait rien sur la plateforme de dev principale du
    projet — sans que rien ne le dise, l'erreur étant rattrapée en
    « code de sortie 2 ».

    ``errors="replace"`` en second temps : sur une console vraiment
    incapable d'UTF-8, une fiche avec quelques ``?`` vaut mieux qu'une
    exception d'encodage.
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


if __name__ == "__main__":  # pragma: no cover — point d'entrée
    raise SystemExit(main())
