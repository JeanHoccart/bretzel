"""Rule: an **assembled** Tailwind class only exists in dev.

The repository's most vicious failure mode, and the only one producing
**identical** HTML on both sides. The production Tailwind compiler scans
the *sources*: a class that appears nowhere in full is never generated.
In dev, the browser compiler scans the *DOM*, where the class is already
resolved — so everything works.

``classes=f"bg-{color}-500"`` produces a correct ``class="bg-tomato-500"``
in both cases. In dev it is styled. In production the CSS rule does not
exist, and nothing — not the HTML, not the console, not a render test —
says so.

⚠️ **The rule does not PROVE a breakage, it reports an invisible
dependency.** Its six occurrences in ``examples/``, measured on
2026-08-16, produced classes (``bg-primary/15``, ``font-medium``…) that
existed elsewhere in the sources — so they were generated, by
coincidence. The coincidence was the safelist's colour closure; phase 5
of the token project dropped it, and they stopped existing. That is what
the rule makes visible: the call site is no longer enough to know whether
the style will exist. All six are rewritten, ``examples/`` has held
**zero** since 2026-09-05 (frozen by
``test_lint_baseline_on_examples``).

**The criterion is precise, so as not to shout wrongly.** We only report
when a literal piece **completes** a class, that is to say when it
precedes an interpolation with no space:

- ``f"bg-{c}-500"`` → literal ``"bg-"``, no trailing space → **reported**;
- ``f"p-4 {extra}"`` → the literal ends with a space, ``extra`` brings
  its own whole classes → ignored;
- ``f"{base} p-4"`` → nothing precedes the interpolation → ignored.

The framework itself is allowed to write templates (``ring-{c}/40``):
they go through ``resolve_slot`` and are harvested into the safelist by
``dynamic_color_shapes``. **An app does not have that bridge** — hence a
stricter rule here than the ``test_safelist_covers_theme_shapes`` gate.
"""

from __future__ import annotations

import ast

from bretzel.lint.corpus import Module
from bretzel.lint.report import Finding

RULE = "assembled-tailwind-class"

#: The kwargs whose value lands in a ``class`` attribute.
_CLASS_KWARGS = frozenset({"classes", "class_"})


#: The class prefixes Bretzel GENERATES itself, and which one is
#: therefore allowed to assemble.
#:
#: ``bz-c-<colour>`` is a BRIDGE class: its rule is written by
#: ``theme/bridges.py``, not compiled from the sources. The Tailwind
#: compiler has nothing to do with it, so this rule's whole argument —
#: "the final class appears in full nowhere" — does not apply.
#:
#: ⚠️ It is even the RECOMMENDED idiom since the steps: the remedy for
#: the ``f"bg-{color}/10"`` this rule catches is precisely
#: ``bg-(--bz-bg)`` plus ``f"bz-c-{color}"``. Without this exemption, the
#: rule would refuse its own solution — measured on 2026-08-30 on the
#: playground's ``/theme-studio`` page.
_GENERATED_PREFIXES = ("bz-c-",)


def _completes_a_class(node: ast.JoinedStr) -> bool:
    """Does a literal abut an interpolation, with no space?"""
    for literal, following in zip(node.values, node.values[1:], strict=False):
        if not (
            isinstance(literal, ast.Constant)
            and isinstance(literal.value, str)
            and isinstance(following, ast.FormattedValue)
        ):
            continue
        text = literal.value
        if not text or text.endswith((" ", "\t", "\n")):
            continue
        if text.rsplit(" ", 1)[-1].startswith(_GENERATED_PREFIXES):
            continue
        return True
    return False


def check(module: Module) -> list[Finding]:
    findings: list[Finding] = []
    for node in ast.walk(module.tree):
        if not isinstance(node, ast.Call):
            continue
        for keyword in node.keywords:
            if keyword.arg not in _CLASS_KWARGS:
                continue
            if not isinstance(keyword.value, ast.JoinedStr):
                continue
            if not _completes_a_class(keyword.value):
                continue
            findings.append(
                Finding(
                    rule=RULE,
                    path=module.path,
                    line=keyword.value.lineno,
                    message=(
                        f"`{keyword.arg}=` receives an f-string that "
                        f"COMPLETES a class: the final class appears in full "
                        f"nowhere here. It will only be styled in production "
                        f"if ANOTHER source happens to contain it — and if it "
                        f"does not, nothing will say so: the HTML is identical "
                        f"in dev, where the compiler scans the already "
                        f"resolved DOM."
                    ),
                    hint=(
                        "Write whole classes and pick one "
                        "(`'bg-red-500' if danger else 'bg-green-500'`), or "
                        "put the scalar in the safelist."
                    ),
                )
            )
    return findings
