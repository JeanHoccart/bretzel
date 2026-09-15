"""Unit tests for ``bretzel.render.shell``."""

from __future__ import annotations

import re

from bretzel.core.tree import Element, TextNode
from bretzel.render.shell import (
    DEFAULT_HTMX_URL,
    DEFAULT_ICONIFY_URL,
    DEFAULT_IDIOMORPH_URL,
    _fouc_script,
    default_shell,
)
from bretzel.runtime.protocol import (
    ENVELOPE_TAG_NAME,
    HEADER_PAGE_ID,
    ROUTE_RUNTIME_JS,
    ROUTE_STYLE_CSS,
    ROUTE_THEME_CSS,
    SINK_ELEMENT_ID,
)

# The envelope arrives at the shell already serialised as a complete
# ``<bz-envelope>…</bz-envelope>`` tag (V3) and is interpolated verbatim.
_ENVELOPE_TAG = f"<{ENVELOPE_TAG_NAME}>{{}}</{ENVELOPE_TAG_NAME}>"


def _shell(**kw: object) -> str:
    """Helper that fills in the mandatory positional + uuid args.

    Note the dev/prod switch here is ``debug: bool`` — ``default_shell`` is
    internal plumbing. The public knob is ``Bretzel(mode="dev"|"prod")``
    (or ``$BRETZEL_MODE``), which the app resolves to ``config.debug`` at
    construction (``server/app.py``). Test the internal function with
    ``debug=``, not ``mode=``.
    """
    return default_shell(
        kw.pop("body_html", "<p>hi</p>"),  # type: ignore[arg-type]
        kw.pop("envelope_json", _ENVELOPE_TAG),  # type: ignore[arg-type]
        page_uuid=kw.pop("page_uuid", "abc123"),  # type: ignore[arg-type]
        **kw,  # type: ignore[arg-type]
    )


# ───────────────────────────────────────────────────────────────────────────
# Document skeleton
# ───────────────────────────────────────────────────────────────────────────


class TestSkeleton:
    def test_doctype(self) -> None:
        out = _shell()
        assert out.startswith("<!doctype html>")

    def test_html_lang_default(self) -> None:
        out = _shell()
        assert '<html lang="en">' in out

    def test_html_lang_override(self) -> None:
        out = _shell(lang="fr")
        assert '<html lang="fr">' in out

    def test_charset_default(self) -> None:
        out = _shell()
        assert '<meta charset="utf-8"/>' in out

    def test_viewport_meta_present(self) -> None:
        out = _shell()
        assert 'name="viewport"' in out

    def test_title_default(self) -> None:
        out = _shell()
        assert "<title>Bretzel</title>" in out

    def test_title_escapes(self) -> None:
        out = _shell(title="<script>")
        assert "<script>" not in out.split("</title>")[0]


# ───────────────────────────────────────────────────────────────────────────
# Description / meta tags
# ───────────────────────────────────────────────────────────────────────────


class TestMeta:
    def test_description_present(self) -> None:
        out = _shell(description="A demo page")
        assert 'name="description" content="A demo page"' in out

    def test_no_description_omits_tag(self) -> None:
        out = _shell()
        assert 'name="description"' not in out

    def test_custom_meta_tags(self) -> None:
        out = _shell(
            meta_tags=[
                {"property": "og:title", "content": "Hello"},
                {"name": "robots", "content": "noindex"},
            ]
        )
        assert 'property="og:title"' in out
        assert 'content="Hello"' in out
        assert 'name="robots"' in out

    def test_meta_values_escaped(self) -> None:
        out = _shell(meta_tags=[{"name": "x", "content": '"injected"'}])
        # The injected quotes must not break the attribute boundary.
        assert 'content=""injected""' not in out


# ───────────────────────────────────────────────────────────────────────────
# Default CSS / JS URLs
# ───────────────────────────────────────────────────────────────────────────


class TestDefaultAssets:
    def test_style_css_linked_in_prod(self) -> None:
        # Prod default : only the compiled ``style.css`` is linked ;
        # ``theme.css`` is the build source, not browser-loadable as-is.
        out = _shell()
        assert ROUTE_STYLE_CSS in out
        # Theme source is never linked from the page (dev inlines it,
        # prod compiles it into style.css).
        assert f'href="{ROUTE_THEME_CSS}"' not in out

    def test_browser_pipeline_inlines_the_compiler(self) -> None:
        from bretzel.render import vendor

        # ``browser_css`` vient de ``config.css_pipeline``, PAS du mode :
        # c'est le seul réglage qui change ce qui est rendu, il devait
        # cesser d'être une implication de ``mode=``.
        out = _shell(browser_css=True, theme_css_content="@theme { --x: 1 }")
        # ⚠️ L'URL RÉSOLUE, pas la constante : le compilateur est rapatriable
        # depuis le 2026-09-13 (``python -m bretzel.render.vendor``), donc
        # elle vaut une route locale sur une machine qui l'a fait et le CDN
        # sur une autre. Comparer à la constante rendait ce test vert ici et
        # rouge ailleurs, ce qui est pire que faux.
        assert vendor.url_for(vendor.browser_css_asset()) in out
        assert '<style type="text/tailwindcss">' in out
        assert "@theme { --x: 1 }" in out
        # Ce pipeline n'émet aucun <link> — le compilateur navigateur
        # est le seul chemin.
        assert ROUTE_STYLE_CSS not in out

    def test_runtime_js_linked(self) -> None:
        out = _shell()
        assert ROUTE_RUNTIME_JS in out

    def test_third_party_libs_linked(self) -> None:
        # Les trois scripts tiers sortent du CDN **ou** de
        # ``/_bretzel/vendor/`` selon que ``.bretzel/vendor/`` a été
        # rempli. Le test lit donc l'URL RÉSOLUE : coder le CDN en dur ici
        # rendrait rouge un dépôt qui a lancé le rapatriement, c'est-à-dire
        # le cas rapide (DCL 644 → 110 ms, mesuré le 2026-08-27).
        from bretzel.render import vendor

        out = _shell()
        for asset in vendor.vendored_assets():
            assert vendor.url_for(asset) in out, asset.filename
        # Idiomorph 0.7+ ships as an htmx-2 extension — registered on
        # ``<body hx-ext="morph">`` so every swap preserves DOM
        # identity by id instead of doing an outerHTML replace.
        assert 'hx-ext="morph"' in out

    def test_the_shell_falls_back_to_the_cdn_without_a_local_copy(
        self, tmp_path, monkeypatch
    ) -> None:
        """Le repli est la règle de départ, pas une panne.

        Un dépôt fraîchement cloné n'a pas ``.bretzel/vendor/`` — la page
        doit alors charger les trois scripts depuis leur origine, sinon
        elle demande trois fichiers qui n'existent pas.
        """
        monkeypatch.chdir(tmp_path)
        out = _shell()
        for url in (DEFAULT_HTMX_URL, DEFAULT_IDIOMORPH_URL, DEFAULT_ICONIFY_URL):
            assert url in out, url

    def test_no_alpine_in_v3(self) -> None:
        # V3 drops Alpine entirely — the bz-* directives engine in
        # runtime.js replaces it. No CDN script, no ``x-data="{}"``
        # bootstrap on <body>.
        out = _shell()
        assert "alpinejs" not in out
        body_open = out[out.index("<body") : out.index(">", out.index("<body"))]
        assert "x-data" not in body_open

    def test_js_loaded_with_defer(self) -> None:
        from bretzel.render import vendor

        out = _shell()
        # Each <script src=...> must carry ``defer`` so DOM is ready.
        urls = [vendor.url_for(a) for a in vendor.vendored_assets()]
        urls.append(ROUTE_RUNTIME_JS)
        for url in urls:
            assert f'<script defer src="{url}' in out

    def test_css_urls_overridable(self) -> None:
        out = _shell(css_urls=["/custom/theme.css", "/custom/app.css"])
        assert ROUTE_THEME_CSS not in out
        assert "/custom/theme.css" in out
        assert "/custom/app.css" in out

    def test_js_urls_overridable(self) -> None:
        out = _shell(js_urls=["/custom/bundle.js"])
        assert DEFAULT_HTMX_URL not in out
        assert "/custom/bundle.js" in out

    def test_cache_bust_appended_to_framework_assets(self) -> None:
        out = _shell(cache_bust="abc1234")
        for url in (ROUTE_STYLE_CSS, ROUTE_RUNTIME_JS):
            assert f"{url}?h=abc1234" in out


# ───────────────────────────────────────────────────────────────────────────
# FOUC inline script
# ───────────────────────────────────────────────────────────────────────────


class TestFouc:
    def test_script_present(self) -> None:
        out = _shell()
        assert _fouc_script() in out

    def test_script_before_stylesheets(self) -> None:
        out = _shell()
        fouc_idx = out.index(_fouc_script())
        css_idx = out.index(ROUTE_STYLE_CSS)
        # Adding `.dark` synchronously before the CSS load means the
        # first paint already has the right palette.
        assert fouc_idx < css_idx

    def test_script_reads_bz_prefixed_storage_key(self) -> None:
        # The FOUC script reads the SAME localStorage key the runtime's
        # persistence layer writes for ``bretzel.theme.ColorScheme``
        # (``$bz:`` adapter prefix + ``ClassName.<key>`` wire key).
        script = _fouc_script()
        assert "localStorage.getItem('$bz:ColorScheme.default')" in script

    def test_script_supports_system_mode(self) -> None:
        # ``mode === 'system'`` (canonical) and ``'auto'`` (legacy alias)
        # both defer to the OS preference via ``prefers-color-scheme`` —
        # not just an explicit dark choice. Must match the runtime effect
        # in ``runtime/_src/00_index.js``.
        script = _fouc_script()
        assert "'system'" in script
        assert "'auto'" in script
        assert "prefers-color-scheme: dark" in script


# ───────────────────────────────────────────────────────────────────────────
# Screen viewport boot script (writes the ``bz_screen`` cookie pre-paint)
# ───────────────────────────────────────────────────────────────────────────


class TestScreenBoot:
    def test_script_present_with_default_breakpoint(self) -> None:
        out = _shell()
        # matchMedia the width against the app's mobile_breakpoint (768 default)
        assert "(max-width: 768px)" in out
        assert "(pointer: coarse)" in out

    def test_breakpoint_is_interpolated_from_config(self) -> None:
        out = _shell(mobile_breakpoint=640)
        assert "(max-width: 640px)" in out
        assert "(max-width: 768px)" not in out

    def test_writes_bz_screen_cookie(self) -> None:
        out = _shell()
        # Cookie is the one client->server channel the render reads (Screen).
        assert "bz_screen=" in out
        # Functional cookie : path-wide, long-lived, Lax ; JS-writable
        # (NOT HttpOnly, the boot script sets it) so the runtime can update
        # it on resize.
        assert "SameSite=Lax" in out
        assert "HttpOnly" not in out

    def test_runs_before_stylesheets(self) -> None:
        out = _shell()
        assert out.index("(max-width: 768px)") < out.index(ROUTE_STYLE_CSS)

    def test_stale_paint_is_corrected_by_a_pre_paint_reload(self) -> None:
        # The only correction is a pre-paint reload when the cookie the server
        # rendered from doesn't match the real viewport. NO live resize
        # listener. The reload is bounded by a sessionStorage flag so it can
        # never loop.
        #
        # This asserts the script REACHES the shell — the only thing this file
        # adds over calling _screen_boot_script() directly. The flag's own
        # properties (consumed before any exit, armed only on the reloading
        # path, polarity) belong to
        # tests/consistency/test_screen_sync_guard_is_consumed.py, which proves
        # them far more strongly ; restating a substring of them here would
        # stay green under any regression that keeps the call and moves it.
        out = _shell()
        assert "location.reload()" in out
        assert "bz:screen-synced" in out


class TestAntiFlashStyle:
    """V3 anti-flash : SSR pre-stamps every directive's initial state,
    so the only flash risk is ``bz-data`` scopes — hidden until
    ``00_index.js`` flips ``.bz-ready`` on <html>. The data tags
    (``<bz-envelope>`` / ``<bz-patch>``) are never displayed."""

    def test_bz_data_hidden_until_ready(self) -> None:
        out = _shell()
        compact = out.replace(" ", "")
        assert "html:not(.bz-ready)[bz-data]{visibility:hidden}" in compact

    def test_nothing_re_declares_visibility_visible(self) -> None:
        """La règle MASQUE avant le boot ; elle ne RELÈVE jamais après.

        ``visibility`` est la seule des deux propriétés de masquage qu'un
        descendant peut reprendre. Une règle qui écrit ``visible`` sur un
        sélecteur large affranchit donc ses cibles de tout ancêtre
        masqué — et un ``ui.dialog`` fermé se cache précisément en
        ``visibility:hidden``. C'est le défaut mesuré le 2026-09-07 :
        un dépôt de fichier joignable au clavier dans un dialogue fermé
        (``tests/runtime_js/test_a_closed_overlay_is_out_of_the_tab_order``).
        """
        compact = _shell().replace(" ", "")
        assert "visibility:visible" not in compact

    def test_envelope_and_patch_tags_display_none(self) -> None:
        out = _shell()
        compact = out.replace(" ", "")
        assert "bz-envelope,bz-patch{display:none}" in compact

    def test_anti_flash_rule_before_stylesheets(self) -> None:
        # Same ordering rationale as the FOUC script — must paint
        # before the first stylesheet so the rule already applies
        # when the first frame composites.
        out = _shell()
        flash_idx = out.index("[bz-data]")
        css_idx = out.index(ROUTE_STYLE_CSS)
        assert flash_idx < css_idx


# ───────────────────────────────────────────────────────────────────────────
# Envelope tag
# ───────────────────────────────────────────────────────────────────────────


class TestEnvelope:
    def test_envelope_tag_interpolated_verbatim(self) -> None:
        tag = (
            f'<{ENVELOPE_TAG_NAME}>{{"version":"v1.0"}}'
            f"</{ENVELOPE_TAG_NAME}>"
        )
        out = _shell(envelope_json=tag)
        # ``serialize_envelope`` produced the complete tag — the shell
        # must embed it untouched (no extra <script> wrapper).
        assert tag in out

    def test_envelope_inside_head(self) -> None:
        out = _shell()
        head = out[out.index("<head>") : out.index("</head>")]
        assert f"<{ENVELOPE_TAG_NAME}>" in head


# ───────────────────────────────────────────────────────────────────────────
# Body wrapper — bz-page-<uuid> (CR-3)
# ───────────────────────────────────────────────────────────────────────────


class TestBodyWrapper:
    def test_wrapper_id_uses_uuid(self) -> None:
        out = _shell(page_uuid="abc123")
        assert 'id="bz-page-abc123"' in out

    def test_data_attribute_mirrors_uuid(self) -> None:
        out = _shell(page_uuid="abc123")
        assert 'data-bretzel-page-id="abc123"' in out

    def test_hx_headers_carries_page_id(self) -> None:
        out = _shell(page_uuid="abc123")
        # The HX-Headers JSON must mention the page id under the
        # documented header name.
        assert HEADER_PAGE_ID in out
        assert "abc123" in out

    def test_body_html_inserted_inside_wrapper(self) -> None:
        out = _shell(body_html="<p>HELLO</p>")
        # Wrapper opens, body HTML appears, wrapper closes.
        wrapper_open = re.search(r'<div id="bz-page-[^"]+"[^>]*>', out)
        assert wrapper_open is not None
        # Body text follows the wrapper open and precedes </div>.
        after_wrapper = out[wrapper_open.end() :]
        assert "<p>HELLO</p>" in after_wrapper
        assert after_wrapper.index("<p>HELLO</p>") < after_wrapper.index(
            "</div>"
        )

    def test_permanent_sink_element_present(self) -> None:
        # Actions target ``#bz-sink`` (``hx-target``) so the non-OOB
        # response body — where <bz-patch> rides — lands in the DOM
        # instead of being discarded by ``hx-swap="none"``.
        out = _shell()
        assert f'<div id="{SINK_ELEMENT_ID}" hidden></div>' in out

    def test_unique_uuid_distinguishes_pages(self) -> None:
        a = _shell(page_uuid="page-a")
        b = _shell(page_uuid="page-b")
        # Two distinct UUIDs → idiomorph sees the wrappers as different
        # elements → destroys old / creates new (no stale bindings).
        assert "bz-page-page-a" in a
        assert "bz-page-page-b" in b
        assert "bz-page-page-a" not in b


# ───────────────────────────────────────────────────────────────────────────
# Head extras — pre-built Nodes from ui.title() / ui.meta()
# ───────────────────────────────────────────────────────────────────────────


class TestHeadExtras:
    def test_extras_serialised_into_head(self) -> None:
        custom = Element("link", {"rel": "icon", "href": "/favicon.ico"})
        out = _shell(head_extras=[custom])
        head = out[out.index("<head>") : out.index("</head>")]
        assert '<link rel="icon" href="/favicon.ico"/>' in head

    def test_text_extra_escaped(self) -> None:
        # TextNode nodes go through the standard escape — no HTML injection
        # via head_extras.
        out = _shell(head_extras=[TextNode("<dangerous>")])
        head = out[out.index("<head>") : out.index("</head>")]
        assert "<dangerous>" not in head
        assert "&lt;dangerous&gt;" in head


# ───────────────────────────────────────────────────────────────────────────
# Sanity — overall well-formedness (skeleton present)
# ───────────────────────────────────────────────────────────────────────────


def test_well_formed_skeleton() -> None:
    out = _shell()
    # The pieces appear in the expected order.
    indices = [
        out.index("<!doctype html>"),
        out.index("<html"),
        out.index("<head>"),
        out.index("</head>"),
        out.index("<body"),
        out.index("</body>"),
        out.rindex("</html>"),
    ]
    assert indices == sorted(indices), out


# ───────────────────────────────────────────────────────────────────────────
# Barre de progression de navigation
# ───────────────────────────────────────────────────────────────────────────


class TestNavProgress:
    """La barre est allumée par défaut et n'a AUCUN mécanisme à elle.

    Ce qu'on garde ici, c'est ce que le shell émet. Le comportement — le
    seuil, les deux formes de navigation, le retour au repos — n'est
    mesurable qu'au navigateur : ``tests/probes/probe_nav_progress.py``.
    """

    def test_on_by_default(self) -> None:
        out = _shell()
        assert 'id="bz-nav-progress"' in out
        assert "bz-nav-slide" in out, "la keyframe part avec la barre"

    def test_off_drops_both_the_bar_and_its_keyframe(self) -> None:
        out = _shell(nav_progress=False)
        assert "bz-nav-progress" not in out
        assert "bz-nav-slide" not in out, (
            "la keyframe reste alors que plus rien ne la porte — des "
            "octets morts sur chaque page"
        )

    def test_it_reads_the_reserved_pending_key(self) -> None:
        """Pas un second mécanisme : le signal de ``ui.pending()``."""
        from bretzel.runtime.protocol import NAV_PENDING_KEY

        assert f"$bz.pending('{NAV_PENDING_KEY}'" in _shell()

    def test_pre_hidden_server_side(self) -> None:
        """Aucune requête n'est en vol quand le serveur rend.

        Sans ce ``display:none`` dans les octets, la barre se peint à
        chaque chargement puis se cache — un clignotement sur le
        mécanisme fait pour les éviter.
        """
        out = _shell()
        bar = out[out.index('id="bz-nav-progress"') :][:400]
        assert 'style="display:none"' in bar
