"""features/import_screen — page: the two-step import, and the archives.

EF-J1 to EF-J8, EF-N1 to EF-N3.

**Two steps, and it is intended: one analyses, THEN one validates.**
*"Nothing enters the database before the teacher has seen the list — an
import is the only operation that creates three hundred pupils at
once."* So the screen is in two halves, and the second does not exist
until the first has run.

**Two SEPARATE buttons**, and it is EF-J4: "Ajouter les élèves" and
"Remplacer les photos". *"We above all do not want to create thirty
duplicates while thinking we are refreshing photos."* Merging them into
one "import" button that would guess the intent is exactly the error the
specification names.

⚠️ The drop is a pasted CSV, not a ``ui.file_upload``
-------------------------------------------------------
EF-J2 asks for the file to be dropped IN the page, and ``ui.file_upload``
exists. It is not used here, and it is a debatable choice: the app would
need to READ the file's content server side, which requires an
``upload_url`` and a route to receive it — input/output plumbing that
§ 3.2 of the specification explicitly puts out of scope (*"it measures
the library, not the framework"*). Pasting keeps the two-step gesture,
which is what counts.
"""

from __future__ import annotations

from bretzel import Feature, page, print_page, refreshable, ui
from bretzel.state import PageState, field
from examples.ecole.features.annees import (
    AnneeVue,
    annee_regardee,
    en_consultation,
)
from examples.ecole.features.import_data import (
    ImportRev,
    analyser,
    apparier_photos,
    archive_de,
    classes_archivables,
    photo_datee,
    valider,
)
from examples.ecole.features.shell import shell

PATH = "/import"

#: The example pasted into the empty field: two lines are enough to show
#: the format, and they avoid a format doc beside it.
EXEMPLE = "COURTY;Léane\nVALLOIS;Malo"


class ImportDraft(PageState):
    """What was dropped, and what the analysis said about it.

    ``analyse_faite`` is what makes the screen's SECOND half exist:
    without it, the two write buttons do not appear. It is EF-J1 made
    structural rather than politely requested.
    """

    code: str = field(default="")
    texte: str = field(default="")
    analyse_faite: bool = field(default=False)


def analyser_le_depot(draft: ImportDraft) -> None:
    """The FIRST step. It writes nothing — that is its whole reason to
    exist."""
    draft.analyse_faite = True


def vider(draft: ImportDraft) -> None:
    draft.texte = ""
    draft.analyse_faite = False


def ajouter_les_eleves(draft: ImportDraft) -> None:
    """EF-J1, second step. **The only button that CREATES pupils.**"""
    annee = annee_regardee()
    resultat = analyser(annee["id"], str(draft.code), str(draft.texte))
    if resultat["refus"]:
        ui.notification(resultat["refus"], variant="error", duration_ms=6000)
        return
    ajoutes = valider(annee["id"], resultat["code"], resultat["valides"])
    draft.texte = ""
    draft.analyse_faite = False
    ui.notification(f"{ajoutes} élève(s) ajouté(s) à {resultat['code']}",
                    variant="success", duration_ms=4000)


def remplacer_les_photos(draft: ImportDraft) -> None:
    """EF-J4 — **the separate button.**

    It touches neither the class's composition, nor the marks, nor the
    comments: it matches by NAME (EF-J5) and sets the images. The names
    it does not find are SAID (EF-J7).
    """
    annee = annee_regardee()
    resultat = analyser(annee["id"], str(draft.code), str(draft.texte))
    if resultat["classe"] is None:
        ui.notification(
            f"Aucune classe {resultat['code']} : il n'y a pas de photos à "
            f"remplacer.", variant="warning", duration_ms=5000)
        return
    bilan = apparier_photos(annee["id"], resultat["classe"]["id"],
                            resultat["valides"])
    if bilan["absents"]:
        ui.notification(
            " · ".join(bilan["absents"][:4]),
            title=f"{bilan['poses']} photo(s) posée(s), "
                  f"{len(bilan['absents'])} nom(s) introuvable(s)",
            variant="warning", duration_ms=8000)
        return
    ui.notification(f"{bilan['poses']} photo(s) posée(s)",
                    variant="success", duration_ms=3000)


@refreshable(deps=[AnneeVue, ImportDraft, ImportRev])
def panneau_import() -> None:
    annee = annee_regardee()
    draft = ImportDraft()
    fige = en_consultation()
    analyse = (analyser(annee["id"], str(draft.code), str(draft.texte))
               if draft.analyse_faite else None)

    with ui.vstack(gap="lg"):
        with ui.card(padding="lg"), ui.vstack(gap="md"):
            ui.heading("1 · On analyse", level=2, size="lg")
            ui.text(
                "Rien n'entre en base à cette étape. Un import est la seule "
                "opération qui crée trois cents élèves d'un coup : on "
                "regarde d'abord.",
                color="muted",
            )
            with ui.form(on_submit=analyser_le_depot), ui.vstack(gap="md"):
                with ui.grid(cols={"base": 1, "md": 3}, gap="md"), ui.form_field(
                    label="Classe",
                    hint="Une classe créée vide par l'emploi du temps "
                         "est retrouvée par son code.",
                ):
                    ui.input(value=draft.code, placeholder="4e1",
                             disabled=fige)
                with ui.form_field(
                    label="La liste",
                    hint=f"Une ligne par élève : NOM;Prénom. "
                         f"Par exemple « {EXEMPLE.splitlines()[0]} ».",
                ):
                    ui.textarea(value=draft.texte, rows=6, disabled=fige,
                                placeholder=EXEMPLE)
                with ui.hstack(gap="md", justify="end"):
                    ui.button("Vider", variant="ghost", on_click=vider)
                    ui.button("Analyser", type="submit", color="primary",
                              icon_left="search", disabled=fige)

        if analyse is not None:
            panneau_analyse(analyse, fige)


def panneau_analyse(analyse: dict, fige: bool) -> None:
    """The second step — and it only shows after the first."""
    with ui.card(padding="lg"), ui.vstack(gap="md"):
        ui.heading("2 · On valide", level=2, size="lg")
        if analyse["refus"]:
            ui.banner(message=analyse["refus"], icon="octagon-x",
                      color="error", size="lg")
        ui.text(
            f"{len(analyse['valides'])} ligne(s) lisible(s), "
            f"{len(analyse['erreurs'])} en erreur.",
            color="muted",
        )
        for ligne in ui.each(analyse["lignes"][:60], key="ligne"):
            with ui.hstack(gap="md", align="center", wrap=True):
                ui.text(f"{ligne['nom'].upper()} {ligne['prenom']}"
                        if ligne["nom"] else ligne["brut"])
                if ligne["erreur"]:
                    # EF-J7: what is not recognised is SAID, not
                    # guessed — it is the teacher who decides.
                    ui.badge(label=ligne["erreur"], color="error",
                             variant="soft", size="xl")
                elif ligne.get("connu"):
                    ui.badge(label=f"déjà en {ligne['connu']}", color="warning",
                             variant="soft", size="xl")
        with ui.hstack(gap="md", justify="end", wrap=True):
            # EF-J4: TWO buttons, and they do not do the same thing.
            ui.button(
                "Remplacer les photos", variant="outline",
                icon_left="image", disabled=fige or bool(analyse["refus"]),
                tooltip="Ne touche ni à la composition de la classe, ni aux "
                        "notes, ni aux appréciations.",
                on_click=remplacer_les_photos)
            ui.button(
                "Ajouter les élèves", color="primary", icon_left="user-plus",
                disabled=fige or bool(analyse["refus"]),
                on_click=ajouter_les_eleves)


# ── The archives (EF-N) ──────────────────────────────────────────────

class VueArchive(PageState, addressable=True):
    """The class archived — the address keeps it, to print it."""

    classe_id: int = field(default=0, url="classe")


def choisir_archive(vue: VueArchive) -> None:
    """Empty: the mutation alone re-renders the ``deps=[VueArchive]``
    zone."""


@refreshable(deps=[AnneeVue, VueArchive])
def panneau_archives() -> None:
    """EF-N1, EF-N2 — *"an archive, not a report card"*.

    *"It must be re-readable in ten years without the program that
    produced it. Printable and complete."* Hence the production date at
    the head, and all the content on ONE page — three tabs would be
    cleaner on screen and would lose at printing time.
    """
    annee = annee_regardee()
    vue = VueArchive()
    classes = classes_archivables(annee["id"])
    if not classes:
        ui.empty_state(title="Aucune classe à archiver", icon="archive")
        return
    if int(vue.classe_id) not in {c["id"] for c in classes}:
        vue.classe_id = classes[0]["id"]
    archive = archive_de(int(vue.classe_id))
    if not archive:
        return

    moyennes: dict[int, list] = {}
    for note in archive["notes"]:
        if not note["absent"] and note["valeur"] is not None:
            moyennes.setdefault(note["eleve_id"], []).append(
                (note["valeur"], note["bareme"], note["coefficient"]))

    with ui.vstack(gap="md"):
        with ui.hstack(gap="md", justify="between", align="center",
                       wrap=True):
            with ui.hstack(gap="md", align="center", wrap=True):
                ui.text("Classe", color="muted")
                ui.select(value=vue.classe_id,
                          options=[(c["id"], c["code"]) for c in classes],
                          on_change=choisir_archive)
            ui.button("Imprimer cette archive", variant="outline",
                      icon_left="printer", on_click=print_page())
        with ui.card(padding="lg"), ui.vstack(gap="md"):
            ui.heading(
                f"{archive['classe']['code']} · {archive['classe']['annee']}",
                level=2, size="xl")
            ui.text(
                f"{archive['classe']['libelle']} · professeur principal : "
                f"{archive['classe']['prof_principal'] or '—'} · archive "
                f"fabriquée le {photo_datee()}",
                color="muted",
            )
            ui.divider(label=f"Trombinoscope · {len(archive['eleves'])} élèves")
            with ui.grid(min_col="12rem", gap="md"):
                for eleve in ui.each(archive["eleves"], key="id"):
                    fiche_archivee(eleve, moyennes, archive)


def fiche_archivee(eleve: dict, moyennes: dict, archive: dict) -> None:
    from examples.ecole.core.domain import moyenne_de

    appreciations = [
        a for a in archive["appreciations"] if a["eleve_id"] == eleve["id"]]
    generale = moyenne_de(moyennes.get(eleve["id"], []))
    with ui.card(padding="sm"), ui.vstack(gap="sm"):
        with ui.hstack(gap="md", align="center"):
            ui.avatar(name=f"{eleve['prenom']} {eleve['nom']}", size="lg",
                      shape="circle")
            with ui.vstack(gap="none"):
                ui.text(eleve["nom"].upper(), weight="semibold")
                ui.text(eleve["prenom"], color="muted")
        ui.text(f"Moyenne générale : {generale:.2f} / 20"
                if generale is not None else "Aucune note",
                color="muted")
        for appreciation in ui.each(appreciations, key="trimestre"):
            ui.text(f"T{appreciation['trimestre']} — "
                    f"{appreciation['appreciation']}")


@page(PATH, layout=shell, title="Import et archives")
def import_page() -> None:
    with ui.vstack(gap="lg"):
        ui.heading("Import et archives", level=1, size="2xl")
        with ui.tabs(value="import", url="vue"):
            ui.tab("import", label="Importer une liste", icon="upload")
            ui.tab("archives", label="Archives", icon="archive")
            with ui.tab_panel(tab="import"):
                panneau_import()
            with ui.tab_panel(tab="archives"):
                panneau_archives()


feature = Feature(
    name="import_screen",
    kind="page",
    provides=[import_page, ImportDraft, VueArchive],
    uses=["import_data", "annees", "shell"],
)
