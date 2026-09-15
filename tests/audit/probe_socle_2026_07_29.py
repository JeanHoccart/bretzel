"""Probe navigateur — les 3 questions que l'audit du socle n'a pas pu trancher.

L'audit du 2026-07-29 est statique + rendu SSR. Trois de ses questions
ouvertes demandent un vrai navigateur, et deux sont des **bugs
potentiellement vivants**, pas du sédiment :

P1  Calendar appelle ``anchored_dismiss_init`` sans émettre
    ``bz-ref="bzpanel"`` (``grep bzpanel calendar.py`` → 0). Le runtime
    résout ``$refs`` par chaîne de prototypes (``03_scope.js``), donc un
    calendar EMBARQUÉ dans un date_picker hériterait du ``bzpanel`` du
    picker → son dropdown mois ne se fermerait jamais au clic dehors.
    Structurellement certain, jamais reproduit.

P2  ``ui.calendar().focus()`` est-il un no-op silencieux ? La root rendue
    est ``<bz-calendar id=…>`` sans ``tabindex``, aucun ``delegatesFocus``
    dans les slabs. ``HTMLElement.focus()`` sur un hôte non focusable ne
    fait rien, sans erreur.

P3  Un ``(x).toString()`` qui lève tue-t-il l'effet ``bz-attr`` seul, ou
    plus large ? Lecture du runtime (faite) : **aucun try/catch** dans
    ``02_directives.js``, ``effect()`` utilise ``try/finally`` sans
    ``catch``, et ni ``bindEl``, ni ``scan``, ni la boucle de flush
    n'attrapent. Donc en théorie un throw emporte le reste du sous-arbre
    au bind, et le reste du BATCH d'effets au flush — page entière.
    Reste à savoir si les 13 sites peuvent réellement recevoir ``null``.

Lancer :  py -m tests.audit.probe_socle_2026_07_29
Le serveur monte sur un port LIBRE et se referme — il ne touche pas au
serveur de dev de l'utilisateur.
"""

from __future__ import annotations

import sys

from tests.audit.harness import audit_server, browser_page

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def _title(text: str) -> None:
    print(f"\n{'=' * 72}\n{text}\n{'=' * 72}")


# ── P3 ────────────────────────────────────────────────────────────────
def probe_p3_tostring_blast_radius(page) -> None:
    _title("P3 — un throw dans un bz-attr emporte quoi ?")

    # On construit un cas minimal DANS la page : deux éléments frères sous
    # un scope, le premier avec un bz-attr qui lève, le second sain. Si le
    # second reste non lié, le rayon dépasse l'élément fautif.
    result = page.evaluate(
        """
        () => {
          const host = document.createElement('div');
          host.setAttribute('bz-data', '{ok: true, missing: null}');
          host.innerHTML = `
            <div id="zz-thrower" bz-attr:data-a="(missing).toString()"
                 bz-attr:data-b="'reste-du-meme-element'"
                 bz-text="'texte-du-meme-element'"></div>
            <div id="zz-sibling" bz-attr:data-c="'element-suivant'"></div>
          `;
          document.body.appendChild(host);
          let threw = null;
          // ``$bz._scan`` — avec l'underscore. ``$bz.scan`` n'existe pas,
          // et l'appeler faisait échouer la probe AVANT toute liaison :
          // elle concluait alors « le frère n'est pas lié » sur une page
          // où rien n'avait été lié du tout. Piège de probe classique.
          try { $bz._scan(host); } catch (e) { threw = String(e); }
          const t = document.getElementById('zz-thrower');
          const s = document.getElementById('zz-sibling');
          return {
            scanThrew: threw,
            thrower_a: t.getAttribute('data-a'),
            thrower_b: t.getAttribute('data-b'),
            thrower_text: t.textContent,
            sibling_c: s.getAttribute('data-c'),
          };
        }
        """
    )
    print(f"  scan() a levé          : {result['scanThrew']}")
    print(f"  même élément, attr suivant (data-b) : {result['thrower_b']!r}")
    print(f"  même élément, bz-text              : {result['thrower_text']!r}")
    print(f"  ÉLÉMENT SUIVANT (data-c)           : {result['sibling_c']!r}")
    if result["sibling_c"] is None:
        print("  → RAYON : dépasse l'élément fautif, le frère n'est PAS lié.")
    elif result["thrower_b"] is None:
        print("  → RAYON : limité à l'élément fautif (directives suivantes mortes).")
    else:
        print("  → RAYON : limité à l'attribut fautif.")


def probe_p3_real_sites(page, base_url: str) -> None:
    _title("P3 bis — les 13 sites réels peuvent-ils recevoir null ?")
    for path, label in [("/dropdown", "dropdown"), ("/popover", "popover"),
                        ("/sidebar", "sidebar"), ("/toggle_group", "toggle_group"),
                        ("/tabs", "tabs")]:
        try:
            page.goto(base_url + path, wait_until="networkidle")
            page.wait_for_timeout(400)
        except Exception as exc:  # page absente du playground
            print(f"  {label:14} page indisponible ({type(exc).__name__})")
            continue
        info = page.evaluate(
            """
            () => {
              const els = document.querySelectorAll('[bz-attr\\\\:aria-expanded],'
                        + '[bz-attr\\\\:data-selected],[bz-attr\\\\:aria-pressed]');
              const out = [];
              for (const el of els) {
                for (const a of el.attributes) {
                  if (!a.name.startsWith('bz-attr:')) continue;
                  const rendered = el.getAttribute(a.name.slice(8));
                  out.push({expr: a.value, attr: a.name.slice(8), rendered});
                }
              }
              return out.slice(0, 4);
            }
            """
        )
        # (Un listener ``pageerror`` traînait ici, collectant dans une liste
        # jamais lue — du bruit qui donnait l'illusion d'une vérification.
        # ``browser_page`` imprime déjà les pageerror.)
        print(f"  {label:14} {len(info)} directive(s) échantillonnées")
        for d in info:
            ok = d["rendered"] in ("true", "false")
            flag = "OK " if ok else "!! "
            print(f"     {flag}{d['attr']:16} = {d['rendered']!r:8} ← {d['expr'][:44]}")


# ── P2 ────────────────────────────────────────────────────────────────
def probe_p2_calendar_focus(page, base_url: str) -> None:
    _title("P2 — ui.calendar().focus() est-il un no-op ?")
    page.goto(base_url + "/calendar", wait_until="networkidle")
    page.wait_for_timeout(500)
    result = page.evaluate(
        """
        () => {
          const cal = document.querySelector('bz-calendar');
          if (!cal) return {found: false};
          const before = document.activeElement ? document.activeElement.tagName : null;
          cal.focus();
          const after = document.activeElement ? document.activeElement.tagName : null;
          return {
            found: true,
            tag: cal.tagName,
            tabindex: cal.getAttribute('tabindex'),
            hasShadow: !!cal.shadowRoot,
            delegatesFocus: cal.shadowRoot ? cal.shadowRoot.delegatesFocus : null,
            activeBefore: before,
            activeAfter: after,
            movedFocus: before !== after,
            focusableInside: cal.querySelectorAll(
              'button,[href],input,select,textarea,[tabindex]:not([tabindex="-1"])'
            ).length,
          };
        }
        """
    )
    if not result.get("found"):
        print("  <bz-calendar> absent de /calendar — probe non concluante")
        return
    for k in ("tag", "tabindex", "hasShadow", "delegatesFocus",
              "activeBefore", "activeAfter", "movedFocus", "focusableInside"):
        print(f"  {k:16} : {result[k]!r}")
    print("  → " + ("focus() DÉPLACE le focus" if result["movedFocus"]
                    else "focus() est un NO-OP SILENCIEUX"))


# ── P1 ────────────────────────────────────────────────────────────────
def probe_p1_calendar_bzpanel(page, base_url: str) -> None:
    _title("P1 — Calendar hérite-t-il le bzpanel de son date_picker ?")
    page.goto(base_url + "/date_picker", wait_until="networkidle")
    page.wait_for_timeout(500)

    structural = page.evaluate(
        """
        () => {
          const cal = document.querySelector('bz-calendar');
          if (!cal) return {found: false};
          // Le scope du calendar, et ce que $refs.bzpanel y résout.
          const scope = $bz._scopeFor(cal);
          let resolved = null, ownRef = null;
          try {
            const p = scope && scope.refs ? scope.refs.bzpanel : undefined;
            resolved = p ? (p.id || p.tagName) : String(p);
            ownRef = Object.prototype.hasOwnProperty.call(
              scope.refs || {}, 'bzpanel');
          } catch (e) { resolved = 'ERR ' + e; }
          return {
            found: true,
            calendarEmitsBzpanel:
              !!document.querySelector('bz-calendar [bz-ref="bzpanel"]'),
            resolvedBzpanel: resolved,
            isOwnProperty: ownRef,
          };
        }
        """
    )
    if not structural.get("found"):
        print("  <bz-calendar> absent de /date_picker — probe non concluante")
        return
    for k, v in structural.items():
        print(f"  {k:22} : {v!r}")
    if structural["resolvedBzpanel"] not in (None, "undefined", "null") \
            and not structural["isOwnProperty"]:
        print("  → HÉRITAGE CONFIRMÉ (structurel) : le calendar résout un")
        print("    bzpanel qui n'est pas le sien — chaîne de prototypes.")
    else:
        print("  → pas d'héritage : le dismiss du calendar vise sa propre cible")
        return

    # ── La CONSÉQUENCE, qui est la vraie question ────────────────────
    # L'héritage structurel ne prouve pas le bug. Ce qui le prouverait :
    # ouvrir le picker, ouvrir le dropdown mois DU CALENDAR, cliquer
    # dans le panneau du picker (donc « dedans » pour le picker, mais
    # « dehors » pour le dropdown mois) et regarder s'il se ferme.
    print("\n  --- conséquence comportementale ---")
    behaviour = page.evaluate(
        """
        () => {
          const trigger = document.querySelector(
            '[bz-ref="bztrigger"], .bz-date-picker button');
          if (!trigger) return {step: 'trigger introuvable'};
          trigger.click();
          return {step: 'picker ouvert'};
        }
        """
    )
    print(f"  {behaviour['step']}")
    page.wait_for_timeout(350)

    state = page.evaluate(
        """
        () => {
          const cal = document.querySelector('bz-calendar');
          if (!cal) return {ok: false, why: 'calendar absent apres ouverture'};
          // Le dropdown mois du calendar : un bouton qui ouvre une liste.
          const monthBtn = cal.querySelector(
            '[data-month-trigger], [aria-haspopup], button');
          if (!monthBtn) return {ok: false, why: 'pas de trigger mois'};
          monthBtn.click();
          return {ok: true, monthBtnLabel: (monthBtn.textContent || '').trim().slice(0, 24)};
        }
        """
    )
    if not state.get("ok"):
        print(f"  probe non concluante : {state.get('why')}")
        return
    print(f"  dropdown mois ouvert via : {state['monthBtnLabel']!r}")
    page.wait_for_timeout(300)

    verdict = page.evaluate(
        """
        () => {
          const cal = document.querySelector('bz-calendar');
          const openCount = () => cal.querySelectorAll(
            '[aria-expanded="true"], [data-open="true"]').length;
          const before = openCount();
          // Un clic DANS le panneau du picker, mais HORS du dropdown mois.
          const panel = document.querySelector('[bz-ref="bzpanel"]');
          if (panel) panel.click();
          return {before, panelFound: !!panel};
        }
        """
    )
    page.wait_for_timeout(350)
    after = page.evaluate(
        """() => {
             const cal = document.querySelector('bz-calendar');
             return cal.querySelectorAll(
               '[aria-expanded="true"], [data-open="true"]').length;
           }"""
    )
    print(f"  panneau du picker trouvé      : {verdict['panelFound']}")
    print(f"  sous-menus ouverts AVANT clic : {verdict['before']}")
    print(f"  sous-menus ouverts APRÈS clic : {after}")
    if verdict["before"] > 0 and after >= verdict["before"]:
        print("  → BUG REPRODUIT : le dropdown mois ne se ferme pas sur un")
        print("    clic dans le panneau du picker.")
    elif verdict["before"] > 0:
        print("  → pas de bug : le dropdown se ferme correctement.")
    else:
        print("  → indéterminé : aucun sous-menu n'était ouvert au départ.")


def main() -> None:
    with audit_server() as base_url, browser_page(base_url, "/dropdown") as page:
        probe_p3_tostring_blast_radius(page)
        probe_p3_real_sites(page, base_url)
        probe_p2_calendar_focus(page, base_url)
        probe_p1_calendar_bzpanel(page, base_url)
    print("\nProbe terminée.")


if __name__ == "__main__":
    main()
