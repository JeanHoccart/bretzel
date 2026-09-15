"""Toute lecture ou écriture d'une table POSSÉDÉE déclare son cadrage.

⚠️ **Pourquoi une gate d'APP vit parmi les gates de framework.**
`examples/crm` n'est pas une démo : c'est l'instrument avec lequel on
mesure Bretzel, et sa politique d'accès — « un commercial ne voit que
son portefeuille » — est portée par une convention à trente call-sites,
pas par un mécanisme. La règle 8 du charter dit qu'un invariant réparé
sans gate redérive ; celui-ci a dérivé **à l'intérieur du diff qui
l'introduisait** : vingt-trois lectures avaient été cadrées et zéro
écriture, et deux zones lisaient le cadrage sans le déclarer en `deps=`.

La gate est en AST pur : elle ne construit rien, n'ouvre pas la base de
262 000 lignes, et tourne dans la suite rapide.

**Ce qu'elle affirme**, en deux temps :

1. toute fonction de `examples/crm/features/*_data.py` qui touche une
   table possédée (`accounts`, `contacts`, `deals`, `activities`,
   `notes`) déclare un paramètre de cadrage — sauf celles d'une
   **liste blanche nommée**, dont l'autorisation vient de leur appelant ;
2. toute zone `@refreshable` qui appelle `visible_owner()` déclare
   `ViewerPrefs` dans ses `deps=` — sinon changer de portefeuille laisse
   la zone sur la donnée du précédent.

**La liste blanche est le livrable**, pas une échappatoire : elle
transforme « je ne peux pas dire si celle-là a été oubliée » en
« quelqu'un a signé pour celle-là ». Y ajouter une ligne est un geste
délibéré ; l'oublier rougit.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from tests.consistency._discovery import REPO_ROOT, parsed_sources

CRM_DIR = REPO_ROOT / "examples" / "crm"

#: 34 fichiers Python dans `examples/crm` le 2026-08-20. Le plancher lit
#: la découverte de CETTE gate (cf. `gates.md`) — pas un `rglob` frais,
#: qui resterait vert si le balayage était débranché.
CRM_FLOOR = 25

#: Les tables dont une ligne APPARTIENT à un propriétaire. `users` et
#: `meta` n'en sont pas : la première EST la table des propriétaires, la
#: seconde porte la version du semis.
OWNED_TABLES = ("accounts", "contacts", "deals", "activities", "notes")

#: Les noms de paramètre qui valent déclaration de cadrage. Deux, parce
#: que `add_activity` en porte réellement deux sens distincts : `owner`
#: est celui qu'on ÉCRIT sur la ligne, `scope` celui qui a le DROIT
#: d'écrire — et pour une direction ils diffèrent.
SCOPE_PARAMS = frozenset({"owner", "scope"})

#: Les fonctions autorisées à ne PAS déclarer de cadrage, et la raison.
#: Chacune est atteinte uniquement APRÈS une lecture cadrée qui a déjà
#: refusé la fiche — leur appelant a payé le contrôle.
#:
#: ⚠️ Ajouter une ligne ici, c'est signer. Ce n'est pas « faire taire la
#: gate » : c'est déclarer qu'on a vérifié l'appelant.
SCOPE_EXEMPT: dict[str, str] = {
    "accounts_data.account_totals":
        "appelée après get_account(id, owner), qui a déjà rendu 404",
    "contacts_data.account_contacts":
        "sous-table d'une fiche compte déjà cadrée",
    "contacts_data.contact_activities":
        "sous-table d'une fiche contact déjà cadrée",
    "contacts_data.contact_notes":
        "sous-table d'une fiche contact déjà cadrée",
    "deals_data.account_deals":
        "sous-table d'une fiche compte déjà cadrée",
    "deals_data.renumber_stage":
        "réétale des rangs, ne lit ni ne rend aucune ligne d'un tiers",
    "deals_data.horizon_date":
        "arithmétique de dates, aucune table",
    "auth_data.find_by_login":
        "table users — c'est la table des propriétaires, pas une donnée possédée",
    "auth_data.find_by_id": "idem",
    "auth_data.all_users": "idem",
    "auth_data.authenticate": "idem",
}

#: Le mot SQL qui trahit une table possédée dans une chaîne littérale.
_TABLE_WORD = re.compile(
    r"\b(?:FROM|JOIN|INTO|UPDATE)\s+(" + "|".join(OWNED_TABLES) + r")\b",
    re.IGNORECASE,
)


def _crm_sources() -> list:
    return parsed_sources(CRM_DIR, floor=CRM_FLOOR)


def _data_modules() -> list:
    return [s for s in _crm_sources()
            if s.path.parent.name == "features"
            and s.path.name.endswith("_data.py")]


def _literal_sql(node: ast.AST) -> str:
    """Toutes les chaînes littérales du sous-arbre, concaténées.

    Les requêtes du CRM sont écrites en morceaux (implicite, f-strings),
    donc chercher un appel `query("…")` avec un seul argument texte
    raterait la moitié du corpus. On lit le sous-arbre entier.
    """
    return " ".join(
        n.value for n in ast.walk(node)
        if isinstance(n, ast.Constant) and isinstance(n.value, str)
    )


def touches_owned_table(fn: ast.FunctionDef) -> str | None:
    """Le nom de la première table possédée que la fonction nomme."""
    match = _TABLE_WORD.search(_literal_sql(fn))
    return match.group(1).lower() if match else None


def declares_scope(fn: ast.FunctionDef) -> bool:
    args = fn.args
    names = {a.arg for a in (*args.posonlyargs, *args.args, *args.kwonlyargs)}
    return bool(names & SCOPE_PARAMS)


def unscoped_functions() -> list[str]:
    """Les fonctions qui touchent une table possédée sans cadrage."""
    out: list[str] = []
    for source in _data_modules():
        module = source.path.stem
        for node in ast.walk(source.tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            qualified = f"{module}.{node.name}"
            if qualified in SCOPE_EXEMPT:
                continue
            if touches_owned_table(node) and not declares_scope(node):
                out.append(f"{qualified} ({source.path.name}:{node.lineno})")
    return sorted(out)


def _decorator_deps(node: ast.FunctionDef) -> list[str] | None:
    """Les noms listés dans ``@refreshable(deps=[…])``, ou ``None``."""
    for deco in node.decorator_list:
        if not isinstance(deco, ast.Call):
            continue
        name = deco.func.id if isinstance(deco.func, ast.Name) else getattr(
            deco.func, "attr", "")
        if name != "refreshable":
            continue
        for kw in deco.keywords:
            if kw.arg == "deps" and isinstance(kw.value, (ast.List, ast.Tuple)):
                return [e.id for e in kw.value.elts if isinstance(e, ast.Name)]
        return []
    return None


#: Les zones qui lisent le cadrage SANS déclarer ``ViewerPrefs``, et qui
#: ont une raison. ``broadcast=True`` en est une : ses ``deps`` sont ce
#: sur quoi elle DIFFUSE à tous les clients, donc y mettre une
#: préférence personnelle pousserait un refetch au monde entier
#: (finding 23 du chantier).
DEPS_EXEMPT: dict[str, str] = {
    "realtime.board_pulse": "broadcast=True — deps = ce sur quoi elle diffuse",
    "realtime.recent_moves": "broadcast=True — idem",
}


def zones_missing_viewer_prefs() -> list[str]:
    out: list[str] = []
    for source in _crm_sources():
        if source.path.parent.name != "features":
            continue
        module = source.path.stem
        for node in ast.walk(source.tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            qualified = f"{module}.{node.name}"
            if qualified in DEPS_EXEMPT:
                continue
            deps = _decorator_deps(node)
            if deps is None:
                continue
            calls = {n.func.id for n in ast.walk(node)
                     if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
            if "visible_owner" in calls and "ViewerPrefs" not in deps:
                out.append(f"{qualified} ({source.path.name}:{node.lineno})")
    return sorted(out)


# ── ① les planchers ──────────────────────────────────────────────────


def test_the_crm_sweep_is_not_vacuous() -> None:
    assert len(_crm_sources()) >= CRM_FLOOR


def test_the_data_modules_are_found() -> None:
    """Le plancher qui compte vraiment : la gate ne juge que les
    ``*_data.py``, donc c'est CE sous-ensemble qui peut devenir vide
    sans que le précédent bronche."""
    modules = _data_modules()
    assert len(modules) >= 7, (
        f"seulement {len(modules)} modules ``*_data.py`` trouvés — "
        f"l'interdiction ci-dessous s'affirmerait sur presque rien."
    )


def test_the_sweep_actually_finds_owned_tables() -> None:
    """Troisième plancher, et le seul qui prouve que le DÉTECTEUR voit
    quelque chose : un ``_TABLE_WORD`` cassé rendrait zéro contrevenant
    ET zéro fonction cadrée, donc les deux tests suivants passeraient."""
    touching = [
        node.name
        for source in _data_modules()
        for node in ast.walk(source.tree)
        if isinstance(node, ast.FunctionDef) and touches_owned_table(node)
    ]
    assert len(touching) >= 20, (
        f"seulement {len(touching)} fonctions touchent une table possédée "
        f"— le détecteur de table ne mord plus."
    )


# ── ② les interdictions ──────────────────────────────────────────────


def test_every_owned_access_declares_its_scope() -> None:
    offenders = unscoped_functions()
    assert not offenders, (
        "ces fonctions touchent une table possédée sans déclarer de "
        "cadrage :\n  " + "\n  ".join(offenders)
        + "\n\nAjoute un paramètre ``owner: str | None`` et pose-le dans "
          "le ``WHERE`` — ou inscris la fonction dans ``SCOPE_EXEMPT`` "
          "avec la raison, si son appelant a déjà payé le contrôle."
    )


def test_every_scoped_zone_declares_viewer_prefs() -> None:
    offenders = zones_missing_viewer_prefs()
    assert not offenders, (
        "ces zones lisent ``visible_owner()`` sans ``ViewerPrefs`` dans "
        "leurs ``deps=`` :\n  " + "\n  ".join(offenders)
        + "\n\nChanger de portefeuille les laisserait sur la donnée du "
          "précédent."
    )


def test_the_exemption_lists_stay_honest() -> None:
    """Une exemption qui ne désigne plus rien est un aveu périmé.

    Sans ce test, ``SCOPE_EXEMPT`` grossit et ne rétrécit jamais : on
    cadre une fonction, on oublie de retirer sa ligne, et la gate cesse
    de la surveiller sans que personne le voie.
    """
    known = {
        f"{source.path.stem}.{node.name}"
        for source in _crm_sources()
        for node in ast.walk(source.tree)
        if isinstance(node, ast.FunctionDef)
    }
    stale = sorted((set(SCOPE_EXEMPT) | set(DEPS_EXEMPT)) - known)
    assert not stale, (
        f"ces exemptions ne désignent plus aucune fonction : {stale}"
    )
    still_needed = sorted(
        name for name in SCOPE_EXEMPT
        if name.split(".")[0].endswith("_data")
        and any(
            f"{s.path.stem}.{n.name}" == name and declares_scope(n)
            for s in _data_modules() for n in ast.walk(s.tree)
            if isinstance(n, ast.FunctionDef)
        )
    )
    assert not still_needed, (
        f"ces fonctions déclarent maintenant leur cadrage : retire-les de "
        f"SCOPE_EXEMPT pour que la gate les surveille — {still_needed}"
    )


# ── ③ la mutation, dans les DEUX sens ────────────────────────────────


def test_the_table_detector_still_bites() -> None:
    assert _TABLE_WORD.search("SELECT * FROM accounts WHERE id = ?")
    assert _TABLE_WORD.search("UPDATE contacts SET x = ?")
    assert _TABLE_WORD.search("JOIN deals d ON d.id = ?")
    assert _TABLE_WORD.search("INSERT INTO notes (a) VALUES (?)")
    # … et le versant LICITE : ce qui NE doit pas être pris pour une
    # table possédée. ``users`` et ``meta`` en sont, et « accounts »
    # dans un mot plus long aussi.
    assert not _TABLE_WORD.search("SELECT * FROM users WHERE login = ?")
    assert not _TABLE_WORD.search("SELECT value FROM meta WHERE key = ?")
    assert not _TABLE_WORD.search("SELECT * FROM accounts_archive")
    assert not _TABLE_WORD.search("le mot accounts dans une phrase")


def test_the_scope_detector_still_bites() -> None:
    scoped = ast.parse("def f(q, owner): pass").body[0]
    kwonly = ast.parse("def f(q, *, scope=None): pass").body[0]
    bare = ast.parse("def f(q): pass").body[0]
    lookalike = ast.parse("def f(q, owner_of): pass").body[0]
    assert declares_scope(scoped)
    assert declares_scope(kwonly)
    assert not declares_scope(bare)
    # ``owner_of`` est un DICT du semis, pas un cadrage : le détecteur ne
    # doit pas se laisser prendre par un préfixe.
    assert not declares_scope(lookalike)


def test_the_deps_reader_still_bites() -> None:
    zone = ast.parse(
        "@refreshable(deps=[A, B])\ndef f(): pass"
    ).body[0]
    plain = ast.parse("def f(): pass").body[0]
    no_deps = ast.parse("@refreshable\ndef f(): pass").body[0]
    assert _decorator_deps(zone) == ["A", "B"]
    assert _decorator_deps(plain) is None
    # Un ``@refreshable`` nu n'est pas une zone SANS deps : c'est une
    # zone qu'on ne sait pas lire. Elle doit ressortir comme « pas de
    # deps déclarées », donc surveillée.
    assert _decorator_deps(no_deps) is None


def test_the_gate_would_catch_a_real_regression() -> None:
    """La preuve par le corpus : on retire une exemption et la gate
    rougit sur la fonction qu'elle couvrait.

    C'est le seul versant qui prouve que le balayage atteint vraiment
    ``features/*_data.py`` — les trois précédents ne testent que les
    détecteurs, sur du texte fabriqué.
    """
    victim = "accounts_data.account_totals"
    assert victim in SCOPE_EXEMPT
    saved = SCOPE_EXEMPT.pop(victim)
    try:
        assert any(o.startswith(victim) for o in unscoped_functions()), (
            "retirer une exemption ne fait pas rougir la gate : elle ne "
            "balaie pas le corpus qu'elle prétend juger."
        )
    finally:
        SCOPE_EXEMPT[victim] = saved
    # … et elle redevient verte une fois l'exemption remise.
    assert not unscoped_functions()


def test_the_documented_data_modules_exist() -> None:
    """Les chemins nommés dans ``SCOPE_EXEMPT`` sont de vrais modules."""
    for name in SCOPE_EXEMPT:
        module = name.split(".")[0]
        path = CRM_DIR / "features" / f"{module}.py"
        assert path.is_file(), f"{path} n'existe plus"
        assert isinstance(path, Path)
