import subprocess, sys, time, urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright

from tests.probes._serve import free_port

# Ce script s'EXÉCUTE au chargement — serveur, Chromium, puis ``sys.exit``.
# Les 48 autres probes gardent leur corps sous ``if __name__ ==
# "__main__"`` ; celui-ci non. Tant que c'est le cas, l'importer doit
# échouer bruyamment plutôt que lancer un navigateur (et tuer le process
# appelant sur le ``sys.exit`` final) dans le dos d'un outil qui balaie le
# dépôt. Cf. ``tests/consistency/test_probes_still_resolve.py``.
if __name__ != "__main__":
    raise RuntimeError(
        "probe_tipiso est un script : lance-le "
        "(`py tests/probes/probe_tipiso.py`), ne l'importe pas."
    )

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE=Path(__file__).parent; PORT=free_port()
BASE=f"http://127.0.0.1:{PORT}"; FAIL=[]
def wait():
    for _ in range(60):
        try: urllib.request.urlopen(BASE+"/",timeout=1); return
        except OSError: time.sleep(0.3)
def tip(p): return p.evaluate("()=>{const e=[...document.querySelectorAll('[role=tooltip]')].find(x=>(x.textContent||'').includes('ICONTIP'));return !e?'absent':(getComputedStyle(e).display!=='none'?'shown':'hidden');}")
def chk(n,c,d=""):
    print(f"  [{'PASS' if c else 'FAIL'}] {n}"+(f" — {d}" if d else "")); 
    if not c: FAIL.append(n)
srv=subprocess.Popen([sys.executable,str(HERE/"bench_tipiso.py"), str(PORT)],cwd=HERE.parent.parent,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
try:
    wait()
    with sync_playwright() as pw:
        b=pw.chromium.launch(); p=b.new_page(); p.goto(BASE+"/"); p.wait_for_function("document.documentElement.classList.contains('bz-ready')"); p.wait_for_timeout(300)
        ICON="button:has(iconify-icon[icon='lucide:home'])"; blur="()=>document.activeElement&&document.activeElement.blur()"
        rid=lambda: p.evaluate("()=>{const r=[...document.querySelectorAll('[bz-ref=\"bzroot\"]')].find(x=>x.querySelector('iconify-icon[icon=\"lucide:home\"]'));return r&&r.getAttribute('bz-id');}")
        print("boot bz-id:", rid())
        p.focus(ICON); p.wait_for_timeout(600); chk("boot: shows on focus", tip(p)=="shown", tip(p))
        p.evaluate(blur); p.wait_for_timeout(300)
        p.click("#refresh"); p.wait_for_timeout(500); print("after-refresh bz-id:", rid())
        p.focus(ICON); p.wait_for_timeout(600); chk("after refresh: shows on focus", tip(p)=="shown", tip(p))
        p.evaluate(blur); p.wait_for_timeout(400); chk("after refresh: hides on blur", tip(p)=="hidden", tip(p))
        b.close()
finally:
    srv.terminate(); srv.wait(timeout=10)
print("RESULT:", "PASS" if not FAIL else f"FAIL {FAIL}")
sys.exit(1 if FAIL else 0)
