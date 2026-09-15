# -*- coding: utf-8 -*-
"""Playwright probe — le navigateur CHARGE-t-il vraiment les pistes ?

Ce que le rendu serveur prouve, et ou il s'arrete
--------------------------------------------------
Un test de rendu voit ``<track kind="captions" src=... srclang=...
label=... default>`` dans le HTML et s'arrete la. Il ne dit RIEN de ce
qui compte :

- le navigateur a-t-il analyse le WebVTT, ou l'a-t-il refuse en silence ?
  Un fichier mal forme ne leve pas : ``textTracks`` existe, et
  ``cues`` reste vide. C'est le mode de panne dominant d'une piste, et
  il est invisible partout sauf ici.
- ``default`` a-t-il bien active UNE piste ? C'est un attribut booleen :
  le rendre en ``default="false"`` l'active quand meme. Le HTML serait
  parfaitement plausible a la lecture, et la mauvaise piste s'afficherait.
- l'ordre declare est-il l'ordre du menu ? Le navigateur choisit selon
  l'ordre du document, donc une piste qui remonte change ce que voit
  quelqu'un qui n'a pas choisi.

D'ou trois lectures, toutes sur ``HTMLMediaElement.textTracks``, l'objet
que le navigateur construit APRES avoir analyse les fichiers.

⚠️ Le controle qui mord vraiment sur la LIVRAISON est celui des
``cues`` : une piste presente mais vide est exactement ce qu'on aurait
livre en se fiant au HTML. Il demande de REVEILLER les pistes d'abord —
un navigateur ne telecharge une piste que lorsqu'elle sort de
``disabled``, donc au repos seule celle marquee ``default`` est analysee.
La premiere version de ce probe l'ignorait et rougissait a tort ; le
detail est reste en commentaire au point ou il se joue.

Run :  py tests/probes/probe_video_tracks.py
"""
from __future__ import annotations

import sys

#: Les pistes sont LUES dans la page, jamais recopiees ici. Deux listes
#: divergent, et c'est la copie manuelle qui a tue quatre probes le
#: 2026-08-30.
from examples.playground.features.video import CAPTION_TRACKS

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

FAILURES: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}"
          + (f" — {detail}" if detail else ""))
    if not cond:
        FAILURES.append(f"{name}: {detail}")


#: Le ``<video>`` de la carte A11y — le SEUL de la page qui porte des
#: pistes. On le retrouve par ca plutot que par un index : un banc gagne
#: des cartes, et un ``nth(6)`` pourrit sans bruit.
SELECTOR = "video:has(track)"

READ_TRACKS = """() => {
    const v = document.querySelector('video:has(track)');
    if (!v) return null;
    return [...v.textTracks].map(t => ({
        kind: t.kind, label: t.label, lang: t.language, mode: t.mode,
        cues: t.cues ? t.cues.length : 0,
    }));
}"""


def main() -> int:
    from tests.audit.harness import audit_server, browser_context

    attendu = [
        {"kind": t.kind, "label": t.label, "lang": t.srclang,
         "default": t.default}
        for t in CAPTION_TRACKS
    ]

    with audit_server() as base:
        with browser_context() as ctx:
            page = ctx.new_page()
            errs: list[str] = []
            page.on("console", lambda m: errs.append(m.text)
                    if m.type == "error" else None)
            page.goto(f"{base}/video", wait_until="networkidle")
            page.wait_for_function(
                "document.documentElement.classList.contains('bz-ready')"
            )

            print("\nLa page /video porte un <video> a pistes")
            check("il y en a exactement un",
                  page.locator(SELECTOR).count() == 1,
                  f"{page.locator(SELECTOR).count()} trouve(s)")

            # L'etat AU REPOS, avant de toucher a quoi que ce soit :
            # c'est la seule lecture qui dise ce que voit quelqu'un qui
            # n'a rien choisi.
            repos = page.evaluate(READ_TRACKS) or []

            # Puis on REVEILLE les pistes. Un navigateur ne telecharge
            # une piste que lorsqu'elle sort de ``disabled`` : au repos,
            # seule celle marquee ``default`` est analysee, et les deux
            # autres restent legitimement a zero cue. Croire l'inverse a
            # fait rougir ce probe a tort en l'ecrivant — garde ici,
            # parce que c'est la lecture naive qu'on refait.
            #
            # ``hidden`` plutot que ``showing`` : ca charge et analyse le
            # fichier sans peindre de sous-titres par-dessus la capture.
            page.evaluate(
                """() => { for (const t of
                     document.querySelector('video:has(track)').textTracks)
                     { if (t.mode === 'disabled') t.mode = 'hidden'; } }"""
            )
            try:
                page.wait_for_function(
                    """() => {
                        const v = document.querySelector('video:has(track)');
                        return v && [...v.textTracks]
                            .every(t => t.cues && t.cues.length > 0);
                    }""",
                    timeout=5000,
                )
                analysees = True
            except Exception:
                analysees = False

            pistes = page.evaluate(READ_TRACKS) or []

            print("\nLes pistes declarees sont celles que le navigateur voit")
            check(f"{len(attendu)} pistes",
                  len(pistes) == len(attendu),
                  f"{len(pistes)} lue(s) : {pistes}")
            check("kind / label / langue, dans l'ordre declare",
                  [(p["kind"], p["label"], p["lang"]) for p in pistes]
                  == [(a["kind"], a["label"], a["lang"]) for a in attendu],
                  str(pistes))

            print("\nChaque WebVTT est ANALYSE — pas seulement telecharge")
            check("chaque piste a au moins une cue une fois reveillee",
                  analysees,
                  f"cues par piste : {[p['cues'] for p in pistes]}")

            # Sur ``repos``, pas sur ``pistes`` : c'est l'etat AVANT
            # qu'on reveille quoi que ce soit. Lu apres, les deux autres
            # pistes sont passees a ``hidden`` de notre fait, et le
            # controle ne dirait plus rien de ce que ``default=`` decide.
            print("\ndefault= active UNE piste et une seule, AU REPOS")
            actives = [p["label"] for p in repos if p["mode"] == "showing"]
            voulue = [a["label"] for a in attendu if a["default"]]
            check("la piste marquee default est celle qui s'affiche",
                  actives == voulue, f"active(s) : {actives}, "
                  f"attendu(s) : {voulue}")

            check("aucune erreur console", not errs, "; ".join(errs[:5]))

            page.screenshot(path="tests/probes/video_tracks_screenshot.png")

    print()
    if FAILURES:
        print(f"VIDEO TRACKS PROBE FAILED — {len(FAILURES)} rouge(s) :")
        for f in FAILURES:
            print("  -", f)
        return 1
    print("VIDEO TRACKS PROBE PASSED.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
