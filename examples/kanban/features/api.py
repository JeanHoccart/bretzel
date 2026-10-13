"""kanban/api — the board, for a program: list, create, move.

Plain FastAPI routes, mounted on ``app.fastapi`` by ``main.py``. They
call the handlers' own functions — :func:`~examples.kanban.features.logic.
ajouter`, :func:`~examples.kanban.features.logic.modifier`, ``pleine`` —
so a card created by ``curl`` is journaled, counted against the
work-in-progress limit and seen by the open windows exactly like one
created by hand. Bretzel saves the state a route writes, as it does after
a click.

**Whose board?** The visitor's. The banner's API dialog shows a key minted
by ``auth.session_key()``; a request carrying it as
``Authorization: Bearer`` runs in the visitor's session — the same
``Tableau``, and the windows they have open follow, live. Without the
key, a request opens a session of its own, with a fresh board.

``/docs`` lists these routes and tries them (``api_docs=True``).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from examples.kanban.core.i18n import tr
from examples.kanban.features.donnees import (
    CLES,
    LIMITES,
    carte_par_id,
    colonne_de,
    libelles,
    pleine,
    rang_en_tete,
)
from examples.kanban.features.logic import ajouter, modifier

router = APIRouter(prefix="/api", tags=["cards"])


class Carte(BaseModel):
    """A card, as the API shows it."""

    id: str
    colonne: str
    titre: str
    qui: str
    etiquettes: list[str]
    echeance: str
    points: int


class NouvelleCarte(BaseModel):
    titre: str = Field(min_length=1, max_length=120, examples=["Hello from curl"])
    colonne: str = Field(default="a_faire", examples=list(CLES))


class Deplacement(BaseModel):
    colonne: str = Field(examples=list(CLES))


def vue(carte: dict[str, Any]) -> Carte:
    return Carte(**{nom: carte[nom] for nom in Carte.model_fields})


def colonne_ouverte(cle: str) -> str:
    """``cle`` if a card may enter it — else the HTTP refusal.

    The limit is the board's rule, the same one a drop meets: 409, and
    nothing written.
    """
    if cle not in CLES:
        raise HTTPException(422, f"Unknown column {cle!r}: one of {', '.join(CLES)}.")
    if pleine(cle):
        raise HTTPException(409, f"“{libelles()[cle]}” is at its limit of {LIMITES[cle]} cards.")
    return cle


@router.get("/cartes", response_model=list[Carte])
def lister() -> list[Carte]:
    """Every card, column by column, in board order."""
    return [vue(carte) for cle in CLES for carte in colonne_de(cle)]


@router.post("/cartes", response_model=Carte, status_code=201)
def creer_carte(nouvelle: NouvelleCarte) -> Carte:
    """A new card at the head of its column."""
    titre = nouvelle.titre.strip()
    ident = ajouter(
        titre,
        colonne_ouverte(nouvelle.colonne),
        tr(f"created “{titre}” through the API", f"a créé « {titre} » par l'API"),
    )
    return vue(carte_par_id(ident))


@router.patch("/cartes/{ident}", response_model=Carte)
def deplacer(ident: str, deplacement: Deplacement) -> Carte:
    """Move a card to the head of another column."""
    carte = carte_par_id(ident)
    if carte is None:
        raise HTTPException(404, f"No card {ident!r} on this board.")
    if deplacement.colonne != carte["colonne"]:
        colonne = colonne_ouverte(deplacement.colonne)
        modifier(
            carte,
            tr(
                f"moved “{carte['titre']}” to {libelles()[colonne]} through the API",
                f"a déplacé « {carte['titre']} » vers {libelles()[colonne]} par l'API",
            ),
            colonne=colonne,
            rang=rang_en_tete(colonne),
        )
    return vue(carte_par_id(ident))
