"""Audit driver — run every applicable probe against a single component
and return a structured report.

Usage from a subagent / CLI :

.. code-block:: bash

    py -m tests.audit.driver button
    py -m tests.audit.driver tier_2          # whole tier
    py -m tests.audit.driver --all

The driver does NOT auto-fix. It REPORTS. Fixes are reviewed and applied
by the main agent so the user can audit the diff.
"""

from __future__ import annotations

import dataclasses
import json
import sys
from dataclasses import dataclass, field

from tests.audit.checklist import (
    COMPONENT_SPECS,
    ComponentSpec,
    all_specs,
)
from tests.audit.harness import audit_server, browser_page
from tests.audit.interaction import (
    probe_client_binding_lands_on_carrier,
    probe_client_switches_drive_carrier,
    probe_server_props_drive_dom,
)
from tests.audit.probes import (
    ProbeResult,
    probe_color_distinctness,
    probe_no_body_overflow,
    probe_no_clip,
    probe_size_distinctness,
    probe_tab_order,
    probe_theme_color_at_rest,
)


@dataclass
class ComponentReport:
    name: str
    route: str
    passed: list[str] = field(default_factory=list)
    failed: list[dict] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    error: str = ""

    def record(self, result: ProbeResult) -> None:
        if result.passed:
            self.passed.append(result.name)
        else:
            self.failed.append({"name": result.name, "detail": result.detail})

    def skip(self, name: str, reason: str) -> None:
        self.skipped.append(f"{name} : {reason}")

    @property
    def is_clean(self) -> bool:
        return not self.failed and not self.error


def run_audit(spec: ComponentSpec, base_url: str) -> ComponentReport:
    """Run every applicable probe against ``spec``. Returns a structured
    report (no exceptions raised even if probes throw — they're
    captured)."""
    report = ComponentReport(name=spec.name, route=spec.route)
    try:
        with browser_page(base_url, spec.route) as page:
            # ── Layout ─────────────────────────────────────────────
            report.record(probe_no_body_overflow(page))

            # ── Clipping (only meaningful if the component renders) ──
            try:
                report.record(probe_no_clip(
                    page, selector=spec.root_selector,
                ))
            except Exception as e:
                report.failed.append({
                    "name": "no_clip", "detail": f"probe threw : {e}",
                })

            # ── Color distinctness ────────────────────────────────
            if spec.has_color_axis and spec.color_at_rest:
                # The Reference card lays out N color swatches in a
                # row ; we sample the first N components matching the
                # root selector. ``expected_color_count`` defaults to
                # 7 but Alert / Banner override.
                report.record(probe_color_distinctness(
                    page,
                    selector=spec.color_sample_selector or spec.root_selector,
                    expected_count=spec.expected_color_count,
                    inner_role=spec.inner_role,
                ))
            elif spec.has_color_axis and not spec.color_at_rest:
                # Input-like : color is intentionally focus/checked-only.
                # The probe would FAIL by design. Skip it.
                report.skip(
                    "color_distinctness",
                    "input-like component : color= takes effect on "
                    "focus / checked only by design (Tailwind / Linear "
                    "/ Notion convention)",
                )
            else:
                report.skip("color_distinctness",
                            "component has no color= axis")

            # ── Size distinctness ──────────────────────────────────
            if spec.has_size_axis:
                report.record(probe_size_distinctness(
                    page, selector=spec.root_selector,
                    expected_count=spec.expected_size_count,
                    inner_role=spec.inner_role,
                ))
            else:
                report.skip("size_distinctness",
                            "component has no size= axis")

            # ── Tab order ─────────────────────────────────────────
            if spec.is_interactive:
                report.record(probe_tab_order(
                    page, component_selector=spec.root_selector,
                ))
            else:
                report.skip("tab_order",
                            "component is not interactive")

            # ── Carrier landing : ClientBinding lands on an element
            #    where the bound HTML attribute actually does work.
            #    Static check, no interaction needed — runs everywhere.
            report.record(probe_client_binding_lands_on_carrier(page))

            # ── Client-playground switches actually propagate to the
            #    component subtree (catches the wrapper-vs-carrier
            #    bug class from a behavioural angle). Only run when
            #    the playground exposes a Client playground card —
            #    not every component has one.
            has_client_panel = bool(page.evaluate(
                """() => {
                    const hs = [...document.querySelectorAll('h2')];
                    return hs.some(h =>
                        h.textContent.includes('Client playground'));
                }"""
            ))
            if has_client_panel:
                report.record(probe_client_switches_drive_carrier(
                    page, component_root_selector=spec.root_selector,
                    skip_props=spec.skip_dynamic_props,
                ))
            else:
                report.skip("client_switches_drive_carrier",
                            "no Client playground card on this page")

            # ── Server-playground props drive the preview DOM
            #    (catches morph traps : when the server returns new
            #    HTML but the swap fails to apply, or when a render
            #    branch silently ignores a kwarg). Only run when the
            #    page exposes a Server playground card.
            has_server_panel = bool(page.evaluate(
                """() => {
                    const hs = [...document.querySelectorAll('h2')];
                    return hs.some(h =>
                        h.textContent.includes('Server playground'));
                }"""
            ))
            if has_server_panel:
                report.record(probe_server_props_drive_dom(
                    page, preview_selector=spec.root_selector,
                    skip_props=spec.skip_dynamic_props,
                ))
            else:
                report.skip("server_props_drive_dom",
                            "no Server playground card on this page")

    except Exception as e:
        report.error = f"{type(e).__name__}: {e}"

    return report


def run_for(target: str) -> list[ComponentReport]:
    """``target`` is a component name (``"button"``) OR a tier id
    (``"tier_2"``) OR ``"all"``."""
    if target == "all":
        specs = all_specs()
    elif target in COMPONENT_SPECS:
        specs = COMPONENT_SPECS[target]
    else:
        flat = all_specs()
        matched = [s for s in flat if s.name == target]
        if not matched:
            print(f"unknown target : {target!r}", file=sys.stderr)
            sys.exit(2)
        specs = matched

    reports: list[ComponentReport] = []
    with audit_server() as base_url:
        print(f"audit server : {base_url}", file=sys.stderr)
        for spec in specs:
            print(f"  auditing {spec.name} ({spec.route})…",
                  file=sys.stderr)
            reports.append(run_audit(spec, base_url))
    return reports


def _pretty_print(reports: list[ComponentReport]) -> None:
    clean = sum(1 for r in reports if r.is_clean)
    print()
    print(f"=== Audit summary : {clean}/{len(reports)} clean ===")
    for r in reports:
        status = "PASS" if r.is_clean else "FAIL"
        print(f"[{status}] {r.name} ({r.route})")
        if r.error:
            print(f"    error : {r.error}")
        for f in r.failed:
            # Keep detail under 200 chars per line for readability.
            detail = f["detail"][:300]
            print(f"    - {f['name']} : {detail}")


def main() -> None:
    args = sys.argv[1:]
    if not args:
        print("Usage : py -m tests.audit.driver <component|tier|all>")
        sys.exit(1)
    if args[0] == "--all":
        target = "all"
    else:
        target = args[0]
    json_mode = "--json" in args[1:]

    reports = run_for(target)
    if json_mode:
        print(json.dumps(
            [dataclasses.asdict(r) for r in reports], indent=2,
        ))
    else:
        _pretty_print(reports)
    # Exit non-zero if any audit failed — subagents can shell out.
    if any(not r.is_clean for r in reports):
        sys.exit(1)


if __name__ == "__main__":
    main()
