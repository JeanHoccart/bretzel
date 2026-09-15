"""features/import_screen — écran 9 : l'import, un vrai enchaînement.

Ce que cet écran met sous contrainte : ``ui.stepper`` + un aperçu en
``ui.datatable``, **enchaînés**. Les 17 apps montent chacun de ces composants
seul ; ici l'état d'un pas décide de ce que le suivant peut faire, et l'écran
ne se lit que dans l'ordre.

⚠️ **``ui.file_upload`` en mode formulaire ne transmet RIEN au serveur**, et
c'est mesuré, pas supposé. Le composant pose bien un ``<input type="file"
name="fichier">`` dans le ``<form>`` parent, mais htmx ne construit un corps
``FormData`` que si le formulaire porte ``hx-encoding="multipart/form-data"``
(ou l'``enctype`` équivalent) — et ``grep -rn "hx-encoding" bretzel/`` rend
**zéro** résultat : ``ui.form`` n'a aucune prop pour le dire et n'émet jamais
l'attribut. Le corps part donc en URL-encodé, où un ``File`` ne survit pas ;
le handler reçoit une chaîne vide. Vérifié au navigateur : déposer un CSV
puis cliquer « Vérifier » affiche « Dépose un fichier ou colle un CSV ».

L'écran ne contourne pas : le collage est le chemin réel, et le dépôt reste
là **désactivé**, avec la raison écrite à côté. C'est le finding 15 du
chantier.

Ce que l'écran fait, en revanche, et qu'aucune app n'avait : **la datatable
en tier LISTE**. L'écran 2 la monte en tier callable sur 50 000 lignes ; ici
les lignes sont en mémoire et le composant filtre, trie et pagine tout seul.
Les deux tiers du même composant, dans la même app, sur deux écrans.
"""

from __future__ import annotations

from bretzel import Feature, page, refreshable, ui
from bretzel.components import DatatableState
from bretzel.state import SessionState, field
from examples.crm.core.domain import (
    IMPORT_COLUMNS,
    IMPORT_EXAMPLE_CSV,
    IMPORT_MAX_ROWS,
)
from examples.crm.features.access import visible_owner
from examples.crm.features.import_data import commit_rows, judge, parse_csv
from examples.crm.features.shell import shell

#: Les trois pas.
STEPS: tuple[tuple[str, str, str], ...] = (
    ("Déposer", "Un CSV de comptes, sept colonnes", "upload"),
    ("Vérifier", "Chaque ligne est jugée avant d'écrire", "list-checks"),
    ("Importer", "Tout ou rien, en une transaction", "database"),
)


class ImportDraft(SessionState):
    """Le brouillon d'import.

    ``SessionState`` et non ``PageState`` : un import se poursuit après un
    rechargement. ``colle`` en fait partie — le texte collé doit SURVIVRE au
    re-rendu que déclenche une erreur d'en-tête, sinon l'utilisateur lit le
    reproche au-dessus d'une zone vidée et doit tout recoller.
    """

    etape: int = field(default=0)
    colle: str = field(default='')
    nom_fichier: str = field(default='')
    erreur: str = field(default='')
    lignes: list = field(default_factory=list)
    importees: int = field(default=0)


class ImportPreview(DatatableState):
    """La requête de l'aperçu. Tier LISTE — le composant détient les lignes."""

    per_page: int = field(default=10)


async def start_import(form: ImportDraft, fichier=None) -> None:
    """Lit le CSV — déposé ou collé — et passe au pas de vérification.

    ``async`` parce que ``UploadFile.read()`` l'est ; les handlers sont bien
    awaités par le socle, contrairement aux zones ``@refreshable`` qui ne le
    sont pas (finding 1 du chantier, lui toujours ouvert).

    ``fichier`` n'est pas déclaré comme un champ d'état : c'est le ``name=``
    du ``ui.file_upload``, et l'injection de signature passe une valeur de
    formulaire au paramètre qui porte son nom. Le fichier l'emporte sur le
    collage — on a déposé quelque chose, c'est ça qu'on veut importer.
    """
    raw, source = str(form.colle), "(collé)"
    if fichier is not None and hasattr(fichier, "read"):
        raw = (await fichier.read()).decode("utf-8", errors="replace")
        source = getattr(fichier, "filename", "") or "(sans nom)"
    if not raw.strip():
        form.erreur = "Dépose un fichier ou colle un CSV."
        return
    rows, header_error = parse_csv(raw)
    form.nom_fichier = source
    form.erreur = header_error
    form.lignes = judge(rows, visible_owner()) if not header_error else []
    form.importees = 0
    if not header_error:
        form.etape = 1


def apply_import() -> None:
    draft = ImportDraft()
    rows = list(draft.lignes)
    bad = [r for r in rows if r["_erreur"]]
    if bad:
        ui.notification(
            f"{len(bad)} ligne(s) en erreur — rien n'a été écrit.",
            variant="error", duration_ms=3500,
        )
        return
    draft.importees = commit_rows(rows, visible_owner())
    draft.etape = 2
    ui.notification(f"{draft.importees} compte(s) importé(s)",
                    variant="success", duration_ms=2500)


def restart() -> None:
    draft = ImportDraft()
    draft.etape, draft.nom_fichier, draft.erreur, draft.colle = 0, "", "", ""
    draft.lignes, draft.importees = [], 0


def line_cell(value, _row):
    return ui.text(str(value), color="muted", size="xs")


def verdict_cell(value, _row):
    if not value:
        return ui.badge("OK", color="success", variant="soft", size="xs")
    return ui.text(value, color="error", size="xs")


#: Pas de ``filter=`` sur le verdict : un filtre de colonne compare par
#: ÉGALITÉ de chaîne (``Query.matches_filters``), et les verdicts sont des
#: phrases construites ligne par ligne. Une option « erreur » n'aurait
#: jamais rien matché — un filtre qui vide toujours le tableau est pire
#: qu'un filtre absent.
PREVIEW_COLUMNS = [
    ui.column("_ligne", label="Ligne", width="4rem", render=line_cell),
    *[ui.column(key, label=key, sortable=True) for key in IMPORT_COLUMNS],
    ui.column("_erreur", label="Verdict", render=verdict_cell),
]


def step_drop(draft: ImportDraft) -> None:
    with ui.form(on_submit=start_import):
        with ui.vstack(gap="md"):
            with ui.grid(cols={"base": 1, "lg": 2}, gap="lg"):
                with ui.vstack(gap="sm"):
                    ui.heading("Coller le contenu", level=3, size="sm")
                    ui.textarea(value=draft.colle, rows=8,
                                placeholder=IMPORT_EXAMPLE_CSV)
                with ui.vstack(gap="sm"):
                    ui.heading("Déposer un fichier", level=3, size="sm")
                    # Aucun ``upload_url=`` : le mode formulaire suffit. Le
                    # ``<form>`` voit le fichier et s'encode en multipart
                    # tout seul, et ``start_import`` le reçoit par son
                    # ``name=``.
                    ui.file_upload(
                        variant="dropzone", list="chips", accept=[".csv"],
                        max_files=1, max_size_mb=2, name="fichier",
                        label="Un CSV de comptes",
                    )
                    ui.text(
                        "Le fichier l'emporte sur le texte collé.",
                        color="muted", size="xs",
                    )
            if draft.erreur:
                ui.alert(draft.erreur, color="error", icon="triangle-alert")
            with ui.hstack(justify="between", align="center"):
                ui.text(f"Sept colonnes, {IMPORT_MAX_ROWS} lignes au plus : "
                        f"{', '.join(IMPORT_COLUMNS)}", color="muted",
                        size="xs")
                ui.button("Vérifier", type="submit", color="primary",
                          icon_left="arrow-right")


def step_check(draft: ImportDraft) -> None:
    rows = list(draft.lignes)
    bad = [r for r in rows if r["_erreur"]]
    with ui.vstack(gap="md"):
        with ui.hstack(justify="between", align="center", wrap=True):
            with ui.hstack(gap="sm", align="center"):
                ui.text(draft.nom_fichier, weight="medium", size="sm")
                ui.badge(f"{len(rows)} lignes", variant="soft", color="muted",
                         size="xs")
                if bad:
                    ui.badge(f"{len(bad)} en erreur", variant="soft",
                             color="error", size="xs")
            with ui.hstack(gap="sm"):
                ui.button("Recommencer", variant="ghost",
                          icon_left="rotate-ccw", on_click=restart)
                ui.button("Importer", color="primary", icon_left="database",
                          disabled=bool(bad) or not rows,
                          on_click=apply_import)
        if rows:
            # Tier LISTE : le composant détient les lignes et fait tout en
            # Python. C'est l'inverse exact de l'écran 2, où il ne détient
            # rien et traduit chaque geste en SQL.
            ui.datatable(state=ImportPreview, columns=PREVIEW_COLUMNS,
                         rows=rows, row_key="_ligne", size="sm",
                         search_placeholder="Chercher dans l'aperçu…")
        else:
            ui.empty_state("Aucune ligne lisible", icon="file-x")


def step_done(draft: ImportDraft) -> None:
    with ui.vstack(gap="md"):
        ui.empty_state(
            f"{draft.importees} compte(s) importé(s)",
            icon="circle-check",
            description="Ils sont dans la table Comptes, avec la date du "
                        "jour comme date de création.",
        )
        with ui.hstack(justify="center", gap="sm"):
            ui.link("Voir les comptes", href="/comptes", variant="underline",
                    color="primary")
            ui.button("Nouvel import", variant="soft", icon_left="upload",
                      on_click=restart)


@refreshable(deps=[ImportDraft, ImportPreview])
def wizard() -> None:
    """UNE seule zone pour les trois pas.

    Trois zones imbriquées dans une quatrième, toutes dépendant du même état,
    faisaient partir CHAQUE panneau deux fois : une fois rendu par le parent,
    une fois en fragment hors-bande. Mesuré sur un collage de 200 lignes —
    118 Ko de réponse, l'aperçu sérialisé deux fois, la moitié jetée par le
    morph.
    """
    draft = ImportDraft()
    # ``draft.etape`` NU, sans ``int()`` : le cast rend un entier Python
    # ordinaire, donc le composant ne peut plus voir que la valeur vient
    # du serveur — et il n'émet pas ``_serverSync``. Le panneau affiché
    # se fige alors sur son PREMIER rendu : mesuré, il fallait un F5 pour
    # que le stepper suive, et « Recommencer » laissait l'écran sur le
    # dernier pas pendant que l'état était revenu à zéro.
    with ui.stepper(value=draft.etape, clickable=False):
        for index, (label, description, icon) in enumerate(STEPS):
            ui.step(label=label, description=description, icon=icon,
                    status="complete" if index < int(draft.etape) else None)
        with ui.step_panel():
            step_drop(draft)
        with ui.step_panel():
            step_check(draft)
        with ui.step_panel():
            step_done(draft)


@page("/import", layout=shell, title="Import")
def import_page() -> None:
    with ui.vstack(gap="lg"):
        ui.heading("Import de comptes", level=1, size="2xl")
        with ui.card(padding="md"):
            wizard()


feature = Feature(
    name="import_screen",
    kind="page",
    provides=[import_page, ImportDraft, ImportPreview],
    uses=["import_data", "access"],
)
