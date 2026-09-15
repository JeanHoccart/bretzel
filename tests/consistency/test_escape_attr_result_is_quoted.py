"""Gate : le résultat d'``escape_attr`` atterrit TOUJOURS entre quotes.

Le mécanisme. ``escape_attr`` échappe pour une valeur d'attribut
**quotée** — c'est la quote qui rend la valeur inerte : le tokenizer HTML
lit jusqu'à la quote fermante, et les deux quotes (``"`` et ``'``) sont
échappées, donc rien à l'intérieur ne peut fermer la valeur en avance ni
introduire un attribut. Un appelant qui émettrait un attribut **nu**
(``data-x={valeur}``, sans quotes) sortirait de ce contrat : un espace
suffirait alors à greffer un second attribut.

Pourquoi cette gate (2026-07-27). ``escape_attr`` échappait aussi ``=``
en ``&#x3D;`` et le backtick en ``&#x60;`` — une défense en profondeur
contre exactement ce cas d'attribut nu. On l'a retirée : mesuré sur le
playground, ``=`` apparaît 5 000 à 7 000 fois par page (variantes
Tailwind ``data-[open=false]:``, ``===`` JS, query strings) et coûtait 6
octets au lieu d'1, soit 6-7 % de CHAQUE réponse, pour protéger un cas
qui n'existe à aucun call-site. Le retrait est légitime — mais il rend la
précondition **porteuse** : elle ne peut plus être seulement écrite dans
une docstring. C'est la forme classique « primitive partagée dont la
sûreté repose sur une convention tenue par N call-sites », la même que
``test_action_wire_attrs.py`` verrouille pour le ``data-bz-ts``.

Deux gardes complémentaires :

1. **SOURCE** (attrape la dérive avant qu'elle rende) : tout call-site de
   ``escape_attr`` dans ``bretzel/`` est soit quoté sur place, soit dans
   l'allowlist ci-dessous avec sa raison. Un nouveau call-site non listé
   fait ROUGE — pas parce qu'il est faux, mais pour forcer la relecture
   « et cette valeur, elle est bien entre quotes ? ».

2. **COMPORTEMENTALE** (teste le symptôme réel) : on pousse des charges
   hostiles à travers ``serialize_attrs`` — le chemin qu'empruntent les
   attributs de tous les composants — et on vérifie qu'aucune ne parvient
   à fermer sa valeur ni à greffer un attribut.
"""

from __future__ import annotations

import pathlib
import re

import pytest

from bretzel.core.escape import escape_attr, serialize_attrs
from tests.consistency._discovery import PACKAGE_FLOOR, ParsedSource, parsed_sources

_BRETZEL_DIR = pathlib.Path("bretzel").resolve()

_CALL = re.compile(r"escape_attr\s*\(")

# Les call-sites qui ne portent pas leur quote sur la même expression.
# Clé : ``chemin::extrait de ligne`` — la raison DOIT dire où la quote est
# posée. Ajouter une entrée ici est un acte délibéré, pas une formalité.
_ALLOWED_UNQUOTED_INLINE = {
    # ``safe_uuid`` est consommé deux fois plus bas, chaque fois entre
    # DOUBLES quotes : ``id="bz-page-{…}"`` et
    # ``data-bretzel-page-id="{…}"``.
    #
    # ⚠️ Il y avait un troisième emploi, ``hx-headers='{"…": "{…}"}'``,
    # entre SIMPLES quotes — inerte tant qu'``escape_attr`` échappait
    # ``'``. Elle ne l'échappe plus (2026-08-28), donc ce site est passé
    # en doubles quotes et échappe son JSON entier. C'était le seul du
    # dépôt : la précondition est maintenant « valeur entre DOUBLES
    # quotes », sans exception.
    "render/shell.py::safe_uuid = escape_attr(page_uuid)": (
        "réutilisée 2× plus bas, entre doubles quotes à chaque emploi"
    ),
    # Le JSON d'``hx-headers`` : échappé ici, posé entre DOUBLES quotes
    # ~55 lignes plus bas (``hx-headers="{hx_headers}"``). Il ne peut pas
    # être quoté sur place — la valeur est réutilisée telle quelle, et la
    # quoter ici mettrait les guillemets DANS la valeur.
    """render/shell.py::hx_headers = escape_attr(f'{{"{HEADER_PAGE_ID}": "{page_uuid}"}}')""": (
        "posée entre doubles quotes au point d'emploi"
    ),
    # Deux appels sur la ligne : ``escape_attr(str(v))`` est bien quoté,
    # ``escape_attr(k)`` échappe un NOM d'attribut — une quote n'a pas de
    # sens là. Le nom vient de ``meta_tags={...}`` fourni par l'app.
    # NOTE : ``_ATTR_EXTRA`` ne contient pas l'espace, donc une clé
    # contenant un espace peut greffer un attribut. Antérieur à cette
    # gate et hors de son périmètre (elle garde les VALEURS) — suivi dans
    # ``todo.md``.
    'render/shell.py::f\'{escape_attr(k)}="{escape_attr(str(v))}"\''
    " for k, v in tag.items()": (
        "escape_attr(k) échappe une clé, pas une valeur"
    ),
}


def _source_files() -> list[ParsedSource]:
    return [
        s for s in parsed_sources(_BRETZEL_DIR, floor=PACKAGE_FLOOR)
        # ``escape.py`` définit la fonction et la documente : ses
        # occurrences ne sont pas des call-sites.
        if s.path.name != "escape.py"
    ]


def _call_sites() -> list[tuple[str, str]]:
    """``(chemin relatif, ligne strippée)`` pour chaque appel."""
    out: list[tuple[str, str]] = []
    for source in _source_files():
        rel = source.path.relative_to(_BRETZEL_DIR).as_posix()
        for line in source.text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if _CALL.search(stripped):
                out.append((rel, stripped))
    return out


def _is_quoted_inline(line: str) -> bool:
    """TOUS les appels de la ligne sont-ils collés derrière une quote ?

    Par OCCURRENCE, pas par ligne : ``shell.py:497`` en porte deux, dont
    un seul est quoté (l'autre échappe une clé). Un test par ligne
    laisserait l'appel quoté couvrir l'appel nu.

    La forme canonique est ``…="{escape_attr(x)}"`` dans une f-string :
    le texte qui précède l'appel finit par ``="{``.

    ⚠️ La SIMPLE quote était acceptée ici jusqu'au 2026-08-28. Elle ne
    l'est plus : ``escape_attr`` n'échappe plus ``'``, donc une valeur
    posée entre simples quotes peut refermer son attribut. Le seul
    call-site qui le faisait (``hx-headers``) est passé en doubles.
    """
    opener = re.compile(r'="\{$')
    return all(
        opener.search(line[:m.start()]) is not None
        for m in _CALL.finditer(line)
    )


class TestSourceGuard:
    def test_at_least_one_call_site_is_seen(self) -> None:
        # Anti-pourrissement : si le nom de la fonction change ou que le
        # scan casse, la gate passerait à vide sans rien garder.
        assert _call_sites(), (
            "aucun appel à escape_attr trouvé dans bretzel/ — le scan de "
            "cette gate est cassé, elle ne garde plus rien."
        )

    def test_every_call_site_is_quoted_or_justified(self) -> None:
        offenders = []
        for rel, line in _call_sites():
            if _is_quoted_inline(line):
                continue
            if f"{rel}::{line}" in _ALLOWED_UNQUOTED_INLINE:
                continue
            offenders.append(f"  {rel}\n    {line}")
        assert not offenders, (
            "Call-site(s) d'escape_attr dont la valeur n'est pas quotée "
            "sur place :\n" + "\n".join(offenders) + "\n\n"
            "escape_attr échappe pour une valeur ENTRE QUOTES (cf. sa "
            "docstring). Émettre un attribut nu (data-x={valeur}) laisse "
            "un espace greffer un second attribut. Soit tu quotes, soit "
            "tu ajoutes une entrée à _ALLOWED_UNQUOTED_INLINE en disant "
            "où la quote est posée."
        )

    def test_allowlist_has_no_stale_entry(self) -> None:
        live = {f"{rel}::{line}" for rel, line in _call_sites()}
        stale = sorted(set(_ALLOWED_UNQUOTED_INLINE) - live)
        assert not stale, (
            "Entrée(s) d'allowlist qui ne correspondent plus à aucun "
            f"call-site — à retirer : {stale}"
        )


class TestBehaviour:
    """Le symptôme réel, quel que soit le mécanisme."""

    HOSTILE = (
        '" onload=alert(1) x="',
        "' onload=alert(1) x='",
        '"><script>alert(1)</script>',
        "x\" onmouseover=alert(1) y=\"",
        "a b",                      # espace nu : greffe un attribut si non quoté
        "a=b",                      # ``=`` n'est plus échappé — doit rester inerte
        "a`b",
        "a\tb\nc\rd",
    )

    @pytest.mark.parametrize("payload", HOSTILE)
    def test_serialize_attrs_keeps_the_value_inside_its_quotes(
        self, payload: str
    ) -> None:
        out = serialize_attrs({"title": payload})
        # ``serialize_attrs`` émet `` title="…"`` : exactement deux ``"``,
        # celles qu'il a écrites. Une de plus = la valeur s'est refermée.
        assert out.count('"') == 2, f"valeur échappée hors de ses quotes : {out!r}"
        assert out.startswith(' title="') and out.endswith('"')

    @pytest.mark.parametrize("payload", HOSTILE)
    def test_no_extra_attribute_can_be_grafted(self, payload: str) -> None:
        body = serialize_attrs({"title": payload})[len(' title="'):-1]
        assert "=" not in body.replace("&#x3D;", "") or '"' not in body
        # Le vrai invariant : le tag rendu ne porte qu'UN attribut.
        tag = f"<div{serialize_attrs({'title': payload})}>"
        assert tag.count("=") == 1 + payload.count("="), (
            f"un attribut a pu être greffé : {tag!r}"
        )

    def test_only_the_double_quote_is_safe_now(self) -> None:
        """Le contrat s'est RÉTRÉCI le 2026-08-28, et c'est le point.

        ``escape_attr`` n'échappe plus ``'`` : mesuré sur le playground,
        l'apostrophe coûtait 6 octets au lieu d'1 et apparaît des
        milliers de fois par page — les expressions ``bz-*`` en sont
        faites (``? 'true' : 'false'``, les listes de classes de
        ``bz-class``). ~4 % de chaque réponse, jusqu'à 8 % après gzip
        sur /combobox. Même arbitrage que ``=`` et le backtick le
        2026-07-27, même famille de mesure.

        Le prix est ici : une valeur hostile placée entre SIMPLES quotes
        s'échappe désormais de son attribut. Ce test le constate au lieu
        de le taire — c'est ce qui rend la garde SOURCE au-dessus
        obligatoire, et non plus une simple hygiène.
        """
        payload = "\" onload=alert(1) x='"
        escaped = escape_attr(payload)

        assert f'<div title="{escaped}">'.count('"') == 2, (
            "la double quote est le contrat : une valeur ne doit JAMAIS "
            "pouvoir refermer son attribut"
        )
        assert f"<div title='{escaped}'>".count("'") != 2, (
            "``'`` est de nouveau échappée — soit quelqu'un l'a "
            "réintroduite dans _ATTR_ESCAPES, soit ce test ne mesure "
            "plus rien. Si c'est délibéré, dis pourquoi ici : le gain "
            "mesuré était de ~4 % de chaque page."
        )

    def test_the_apostrophe_survives_intact(self) -> None:
        """Le versant LICITE : ce qu'on a gagné, pas seulement ce qu'on
        a perdu. Une expression ``bz-*`` doit traverser telle quelle."""
        expr = "picked ? 'true' : 'false'"
        assert escape_attr(expr) == expr, (
            "l'apostrophe est ré-échappée : chaque occurrence repasse de "
            "1 à 6 octets, sur des pages qui en portent des milliers"
        )
