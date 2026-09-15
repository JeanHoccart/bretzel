import subprocess, sys, time, urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright

from tests.probes._serve import free_port

# S'EXÉCUTE au chargement (serveur + Chromium, puis ``sys.exit``), sans
# garde ``__main__`` contrairement aux 48 autres probes. Refuser l'import
# évite qu'un balayage du dépôt démarre un navigateur.
# Cf. ``tests/consistency/test_probes_still_resolve.py``.
if __name__ != "__main__":
    raise RuntimeError(
        "probe_combobox_width est un script : lance-le "
        "(`py tests/probes/probe_combobox_width.py`), ne l'importe pas."
    )

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = Path(__file__).parent
PORT = free_port()
BASE = f"http://127.0.0.1:{PORT}"
srv = subprocess.Popen([sys.executable, str(HERE/"bench_combobox_width.py"), str(PORT)], cwd=str(HERE.parent.parent), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
def wait():
    for _ in range(60):
        try: urllib.request.urlopen(BASE + "/", timeout=1); return
        except OSError: time.sleep(0.3)
fail=[]
try:
    wait()
    with sync_playwright() as pw:
        b=pw.chromium.launch(); pg=b.new_page(viewport={"width":1200,"height":800})
        pg.goto(BASE + "/"); pg.wait_for_selector("html.bz-ready")
        pg.click("#cb [role=combobox]"); pg.wait_for_timeout(200)
        m = pg.evaluate("""() => {
            const root=document.querySelector('#cb');
            const trig=root.querySelector('[role=combobox]');
            const panel=root.querySelector('[role=listbox]');
            const t=trig.getBoundingClientRect(), p=panel.getBoundingClientRect();
            return {tw:t.width, pw:p.width, pleft:p.left, tleft:t.left, vw:window.innerWidth};
        }""")
        print(f"trigger width={m['tw']:.0f} | panel width={m['pw']:.0f} | panel.left={m['pleft']:.0f} trigger.left={m['tleft']:.0f} | vw={m['vw']}")
        ok1 = abs(m['pw']-m['tw'])<=6
        ok2 = abs(m['pleft']-m['tleft'])<=6
        ok3 = m['pw'] < m['vw']*0.5
        print("  [%s] panel width == trigger width" % ("PASS" if ok1 else "FAIL"))
        print("  [%s] panel left-aligned with trigger" % ("PASS" if ok2 else "FAIL"))
        print("  [%s] panel NOT viewport-wide" % ("PASS" if ok3 else "FAIL"))
        if not(ok1 and ok2 and ok3): fail.append("stretch")
        pg.screenshot(path=str(HERE/"combobox_width_screenshot.png"))
        b.close()
finally:
    srv.terminate(); srv.wait(timeout=10)
print("PROBE", "FAILED" if fail else "PASSED")
sys.exit(1 if fail else 0)
