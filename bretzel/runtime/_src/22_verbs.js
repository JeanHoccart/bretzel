/* 22_verbs.js — la moitié CLIENT des verbes de `bretzel.runtime.verbs`.
 *
 * Un verbe est une action du NAVIGATEUR déclenchée depuis un `on_*=` :
 *
 *     ui.button("Copier", on_click=bretzel.copy(state.api_key))
 *
 * Il se branche dans le slot qui accepte déjà une CHAÎNE de source
 * client — le même que `dialog.open()` — donc il n'ajoute aucune
 * plomberie : ni requête, ni directive, ni scope.
 *
 * Seul `copy` a besoin de ce fichier. `print` et `fullscreen` tiennent
 * en une expression que Python écrit en toutes lettres ; les mettre ici
 * aurait ajouté une indirection sans rien garder de commun.
 *
 * ⚠️ Pourquoi `copy` n'est PAS un `navigator.clipboard.writeText` nu
 * ---------------------------------------------------------------------
 * L'API Presse-papiers exige un **contexte sécurisé**. `https://` et
 * `http://localhost` en sont ; `http://192.168.1.20:8000` n'en est PAS.
 * Or c'est très exactement la façon dont un outil interne se sert — le
 * public que Bretzel vise. Sur ce chemin-là `navigator.clipboard` vaut
 * `undefined`, et un appel nu lèverait un TypeError : le bouton ne
 * ferait rien, sans un mot.
 *
 * D'où le repli sur `document.execCommand('copy')`. Il est déprécié et
 * il marche partout, y compris hors contexte sécurisé — c'est le seul
 * chemin qui existe là-bas, donc « déprécié » n'est pas un argument
 * contre lui, c'est un argument pour ne pas s'en servir en premier.
 */
(function () {
  "use strict";
  const $bz = (window.$bz = window.$bz || {});

  /* Le repli hors contexte sécurisé.
   *
   * Le `<textarea>` est posé hors écran plutôt que `display:none` : un
   * élément non rendu n'est pas sélectionnable, donc la copie échouerait
   * silencieusement. `readOnly` empêche le clavier virtuel de s'ouvrir
   * sur mobile, et `position:fixed` évite de faire défiler la page vers
   * un champ que personne ne doit voir.
   */
  function viaTextarea(text) {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.cssText = "position:fixed;top:0;left:-9999px;opacity:0";
    document.body.appendChild(ta);
    const selection = document.getSelection();
    const previous = selection && selection.rangeCount > 0
      ? selection.getRangeAt(0) : null;
    ta.select();
    let ok = false;
    try {
      ok = document.execCommand("copy");
    } catch (e) {
      ok = false;
    }
    document.body.removeChild(ta);
    // Rendre la sélection de l'utilisateur : `select()` l'a écrasée, et
    // perdre son surlignage parce qu'on a copié autre chose se voit.
    if (previous && selection) {
      selection.removeAllRanges();
      selection.addRange(previous);
    }
    return ok;
  }

  $bz.verbs = {
    /* Partager — la feuille native, ou le presse-papiers.
     *
     * ⚠️ `navigator.share` est **undefined** sur le Chromium de bureau
     * (mesuré le 2026-09-02 : `typeof navigator.share === "undefined"`).
     * L'absence n'est donc pas un cas limite, c'est le cas NORMAL sur la
     * machine où les utilisateurs de Bretzel développent.
     *
     * Ne rien faire là-dedans donnerait un bouton « Partager » inerte
     * pour la majorité — exactement ce que ce dépôt refuse ailleurs (cf.
     * le refus de `tracks=` sur `ui.audio`, qui aurait promis des
     * sous-titres et livré un attribut). Le repli COPIE donc l'URL : le
     * bouton fait toujours quelque chose d'utile, et c'est un contrat,
     * pas un accident.
     */
    share(data) {
      const charge = data || {};
      if (!charge.url) charge.url = window.location.href;
      if (navigator.share) {
        // Un refus de l'utilisateur (il ferme la feuille) rejette la
        // promesse. Ce n'est pas une erreur de l'app : on ne retombe PAS
        // sur la copie, sinon annuler un partage copierait dans son dos.
        return navigator.share(charge).then(
          function () { return "shared"; },
          function () { return "cancelled"; }
        );
      }
      return $bz.verbs.copy(charge.url).then(function (ok) {
        return ok ? "copied" : "failed";
      });
    },

    /* Vibrer. `navigator.vibrate` EXISTE partout (mesuré : `function`
     * sur le Chromium de bureau) et ne fait rien sans matériel — il n'y a
     * donc aucune absence à gérer, contrairement à `share`.
     */
    vibrate(motif) {
      return navigator.vibrate ? navigator.vibrate(motif) : false;
    },

    /* Copier `value` dans le presse-papiers. Rend une promesse de
     * booléen — jamais une exception : un verbe est appelé depuis un
     * `on_*=`, où personne n'attrape rien, donc une rejection
     * remonterait en `unhandledrejection` dans la console de l'app.
     */
    copy(value) {
      const text = value === null || value === undefined ? "" : String(value);
      if (window.isSecureContext && navigator.clipboard) {
        return navigator.clipboard.writeText(text).then(
          function () { return true; },
          // Un refus reste possible EN contexte sécurisé (permission
          // révoquée, document sans focus). Le repli est alors la
          // dernière chance, pas un chemin mort.
          function () { return viaTextarea(text); }
        );
      }
      return Promise.resolve(viaTextarea(text));
    },
  };
})();
