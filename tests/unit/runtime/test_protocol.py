"""Unit tests for ``bretzel.runtime.protocol`` and ``bretzel.runtime.version``."""

from __future__ import annotations

import pytest

from bretzel.runtime import protocol, version

# ───────────────────────────────────────────────────────────────────────────
# Constants — naming + uniqueness
# ───────────────────────────────────────────────────────────────────────────


class TestConstants:
    def test_route_prefix_consistent(self) -> None:
        # Every routed constant lives under ROUTE_PREFIX.
        for name in (
            "ROUTE_RUNTIME_JS",
            "ROUTE_THEME_CSS",
            "ROUTE_STYLE_CSS",
            "ROUTE_ACTION",
            "ROUTE_SSE",
            "ROUTE_REFETCH",
        ):
            value = getattr(protocol, name)
            assert value.startswith(protocol.ROUTE_PREFIX), name

    def test_bz_attribute_naming(self) -> None:
        # Static metadata attrs are noun-shaped, ``bz-<noun>``.
        for name in ("BZ_ID_ATTR", "BZ_STATE_ATTR"):
            assert getattr(protocol, name).startswith("bz-")
            assert ":" not in getattr(protocol, name)

        # Argument-taking directives are prefixes (carry an ``:<arg>``
        # suffix at use site — ``bz-on:click``, ``bz-attr:href``).
        for name in ("BZ_ON_PREFIX", "BZ_ATTR_PREFIX"):
            assert getattr(protocol, name).startswith("bz-")
            assert getattr(protocol, name).endswith(":")

    def test_directive_prefixes_complete_and_unique(self) -> None:
        # The 13 V3 directives — spec/V3/03-runtime.md §02_directives.js.
        directive_names = [
            k for k in vars(protocol) if k.startswith("BZ_") and k.endswith("_PREFIX")
        ]
        assert len(directive_names) == 13
        values = [getattr(protocol, n) for n in directive_names]
        assert all(v.startswith("bz-") for v in values)
        assert len(values) == len(set(values)), "Duplicate directive prefixes"

    def test_routes_unique(self) -> None:
        routes = [
            v
            for k, v in vars(protocol).items()
            if k.startswith("ROUTE_") and isinstance(v, str) and v != protocol.ROUTE_PREFIX
        ]
        assert len(routes) == len(set(routes)), "Duplicate route constants"

    def test_attrs_unique(self) -> None:
        attrs = [
            v
            for k, v in vars(protocol).items()
            if (k.startswith("BZ_") and k.endswith("_ATTR"))
            and isinstance(v, str)
        ]
        assert len(attrs) == len(set(attrs))

    def test_envelope_and_patch_tags_distinct(self) -> None:
        # The two wire tags must never collide — the bridge dispatches
        # on tag name (<bz-envelope> = bootstrap, <bz-patch> = delta).
        assert protocol.ENVELOPE_TAG_NAME != protocol.PATCH_TAG_NAME
        # Custom-element naming rule : a dash is mandatory for the
        # browser to treat them as unknown-but-valid elements.
        assert "-" in protocol.ENVELOPE_TAG_NAME
        assert "-" in protocol.PATCH_TAG_NAME

    def test_protocol_version_v_prefixed_semver_ish(self) -> None:
        # Loose check : starts with 'v' followed by digits and a dot.
        v = protocol.PROTOCOL_VERSION
        assert v.startswith("v")
        major = v.split(".", 1)[0]
        assert major[1:].isdigit()


# ───────────────────────────────────────────────────────────────────────────
# Version compatibility
# ───────────────────────────────────────────────────────────────────────────


class TestParseMajor:
    @pytest.mark.parametrize(
        ("v", "expected"),
        [
            ("v1.0", "v1"),
            ("v1.2.3", "v1"),
            ("v42.7", "v42"),
            ("v0", "v0"),  # no dot
        ],
    )
    def test_extracts_major(self, v: str, expected: str) -> None:
        assert version.parse_major(v) == expected

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError):
            version.parse_major("")


class TestCheckCompat:
    def test_same_major_same_minor(self) -> None:
        assert version.check_compat(version.PROTOCOL_VERSION) is True

    def test_same_major_different_minor(self) -> None:
        # v1.0 ↔ v1.5 must remain compatible (additive bumps allowed).
        major = version.parse_major(version.PROTOCOL_VERSION)
        assert version.check_compat(f"{major}.99") is True

    def test_different_major(self) -> None:
        major_int = int(version.parse_major(version.PROTOCOL_VERSION)[1:])
        assert version.check_compat(f"v{major_int + 1}.0") is False

    def test_empty_string(self) -> None:
        assert version.check_compat("") is False

    def test_garbage(self) -> None:
        # ``parse_major("garbage")`` returns ``"garbage"`` (no dot to split),
        # which doesn't match the framework's major.
        assert version.check_compat("garbage") is False
