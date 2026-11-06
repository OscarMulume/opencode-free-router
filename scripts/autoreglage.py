"""Auto-reglage : banc court, mise a jour de bench.json, journal lisible (autoreglage.json + .log).
Si la composition des groupes change, regenere la config et demande le redemarrage du routeur
(fichier redemarrer.flag + arret de litellm ; run-router.ps1 le relance).
Un fournisseur LENT / EPUISE / KO sort des groupes ; il y revient des qu'un banc le mesure rapide."""
import json, os, subprocess, sys, time
from pathlib import Path

ICI = Path(__file__).resolve().parent
DATA = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "opencode-free-router"
PY = sys.executable
ENV = {**os.environ, "PYTHONUTF8": "1"}


def groupes():
    out = subprocess.run([PY, str(ICI / "render-config.py")], capture_output=True, text=True, env=ENV).stdout
    return "\n".join(l for l in out.splitlines() if l.startswith("free-"))


def main():
    DATA.mkdir(parents=True, exist_ok=True)
    avant = groupes()
    subprocess.run([PY, str(ICI / "bench.py"), "--court"], capture_output=True, text=True, env=ENV)
    data = json.loads((DATA / "bench.json").read_text(encoding="utf-8"))
    apres = groupes()
    etat = {}
    for nom, r in data["fournisseurs"].items():
        t = (r.get("30k") or {}).get("premier_token_s")
        etat[nom] = {"etat": r["etat"], "delai_30k_s": t, "delai_1k_s": (r.get("1k") or {}).get("premier_token_s")}
    changement = avant != apres
    journal = {"heure": time.strftime("%Y-%m-%d %H:%M:%S"), "changement_groupes": changement, "fournisseurs": etat}
    (DATA / "autoreglage.json").write_text(json.dumps(journal, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    with (DATA / "autoreglage.log").open("a", encoding="utf-8", newline="\n") as f:
        f.write(journal["heure"] + " " + " ; ".join(f"{n}={v['etat']}({v['delai_30k_s']}s)" for n, v in etat.items())
                + (" -> groupes modifies, redemarrage" if changement else " -> aucun changement") + "\n")
    if changement:
        (DATA / "redemarrer.flag").write_text("1")
        subprocess.run(["powershell", "-NoProfile", "-Command",
                        "Get-Process litellm -ErrorAction SilentlyContinue | Stop-Process -Force"], capture_output=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
