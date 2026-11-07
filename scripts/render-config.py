"""Genere %LOCALAPPDATA%\\opencode-free-router\\litellm-config.yaml a partir de litellm/config.yaml (reglages),
scripts/providers.yaml (registre) et bench.json (mesures du banc).

Groupes :
- free-auto  : grosses requetes d'agent. Seulement les fournisseurs mesures < 30 s au 1er token sur 30K,
               du plus rapide au plus lent. Ollama EXCLU.
- free-fast: petites requetes (< 6K). Les plus rapides, puis Ollama (3b si installe, sinon 7b) en dernier.
- free-code  : code lourd (Q4). Memes modeles que free-auto, du meilleur score qualite au moins bon.
- free-question : petite question (Q4). Les plus rapides, Ollama en dernier.
- free-check : verification (Q4). Un modele DIFFERENT du meilleur de free-code quand il en reste un autre.
- free-exhausted: message immediat avec heure de reprise (scripts/epuise.py, port 4010) quand tout est epuise ;
               mock statique en second recours.
Sans bench.json (premier demarrage) : tous les fournisseurs dont la cle existe, dans l'ordre du registre.
Aucune cle n'est ecrite : api_key = os.environ/NOM."""
import json
import os
import shutil
import urllib.request
from pathlib import Path

import yaml

SEUIL_S = 30.0
MSG_EPUISE = ("Quotas gratuits epuises : tous les fournisseurs rapides sont en pause (reprise dans environ 5 minutes, "
              "voir status.ps1). Poussez votre travail, puis reessayez plus tard ou utilisez un autre outil.")


def presente(nom):
    if os.environ.get(nom, "").strip():
        return True
    if os.environ.get("FREE_ROUTER_NO_REGISTRY") == "1":  # tests: ignore the Windows user environment
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
            v = str(winreg.QueryValueEx(k, nom)[0]).strip()
        if v:
            os.environ[nom] = v
            return True
    except Exception:
        pass
    return False


def ollama_modele():
    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3) as r:
            noms = [m["name"] for m in json.loads(r.read())["models"]]
    except Exception:
        return "qwen2.5-coder:7b"
    return "qwen2.5-coder:3b" if "qwen2.5-coder:3b" in noms else "qwen2.5-coder:7b"


def deploiement(groupe, f, modele, ordre):
    p = {"order": ordre, "timeout": 12 if f["nom"].startswith("gemini") else 20, "num_retries": 0}
    if f.get("openai_compat"):
        base = f["base"].format(**{k: os.environ.get(k, "") for k in f["cles"]})
        p.update({"model": "openai/" + modele, "api_base": base, "api_key": "os.environ/" + f["cles"][0]})
    else:
        p.update({"model": f["litellm"].format(m=modele), "api_key": "os.environ/" + f["cles"][0]})
    if f["nom"] == "groq":
        p["model_info"] = {"max_input_tokens": 8000}
    return {"model_name": groupe, "litellm_params": p}


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    dest_dir = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "opencode-free-router"
    dest = dest_dir / "litellm-config.yaml"
    config = yaml.safe_load((root / "litellm" / "config.yaml").read_text(encoding="utf-8"))
    registre = yaml.safe_load((root / "scripts" / "providers.yaml").read_text(encoding="utf-8"))["fournisseurs"]
    bench_f = dest_dir / "bench.json"
    bench = json.loads(bench_f.read_text(encoding="utf-8"))["fournisseurs"] if bench_f.exists() else None
    qualite_f = dest_dir / "qualite.json"
    qualite = json.loads(qualite_f.read_text(encoding="utf-8"))["fournisseurs"] if qualite_f.exists() else None

    def retenu_auto(f, m):
        """Banc de qualite (Q1) : un modele entre dans free-auto seulement s'il est rapide ET fiable.
        Sans mesure de qualite pour ce modele, on garde l'ancien critere (banc de vitesse)."""
        if not qualite:
            return True
        q = qualite.get(f["nom"] + "::" + m)
        return True if q is None else bool(q.get("retenu_free_auto"))

    actifs, ignores = [], []
    for f in registre:
        if f.get("necessite_carte"):
            ignores.append(f["nom"] + " (carte)")
            continue
        if f.get("retire"):
            ignores.append(f["nom"] + " (retire)")
            continue
        if f.get("local"):
            continue
        if not all(presente(k) for k in f["cles"]):
            ignores.append(f["nom"] + " (cle absente)")
            continue
        if bench is None:
            if f.get("desactive_si_lent"):
                continue
            actifs.append((f, f["modeles"][0], 0.0, 0.0))
            continue
        r = bench.get(f["nom"])
        if not r or r.get("etat") == "SANS CLE":
            continue
        t1 = (r.get("1k") or {}).get("premier_token_s")
        t30 = (r.get("30k") or {}).get("premier_token_s")
        if t1 is None:
            continue
        actifs.append((f, r["modele"], t1, t30 if t30 is not None else 1e9))

    gros = sorted([a for a in actifs if a[3] < SEUIL_S and retenu_auto(a[0], a[1])], key=lambda a: a[3]) if bench else actifs
    petits = sorted(actifs, key=lambda a: a[2]) if bench else actifs

    def score(a):
        q = (qualite or {}).get(a[0]["nom"] + "::" + a[1]) or {}
        return float(q.get("note") or 0.0)

    code = sorted(gros, key=lambda a: (-score(a), a[3]))
    verif = [a for a in gros if code and a is not code[0]] or list(gros)

    ml = []
    for i, (f, m, _, _) in enumerate(gros, 1):
        ml.append(deploiement("free-auto", f, m, i))
    for i, (f, m, _, _) in enumerate(code, 1):
        ml.append(deploiement("free-code", f, m, i))
    for i, (f, m, _, _) in enumerate(verif, 1):
        ml.append(deploiement("free-check", f, m, i))
    for groupe in ("free-fast", "free-question"):
        for i, (f, m, _, _) in enumerate(petits, 1):
            ml.append(deploiement(groupe, f, m, i))
    ollama = {"model": "ollama_chat/" + ollama_modele(), "order": 99, "api_base": "http://localhost:11434",
              "num_ctx": 32768, "keep_alive": "30m", "num_retries": 0,
              "model_info": {"supports_function_calling": True, "max_input_tokens": 32768}}
    ml.append({"model_name": "free-fast", "litellm_params": ollama})
    ml.append({"model_name": "free-question", "litellm_params": dict(ollama)})
    ml.append({"model_name": "free-exhausted", "litellm_params": {
        "model": "openai/free-exhausted", "api_base": "http://127.0.0.1:4010/v1", "api_key": "x",
        "order": 1, "timeout": 5, "num_retries": 0}})
    ml.append({"model_name": "free-exhausted", "litellm_params": {
        "model": "openai/free-exhausted", "api_key": "x", "order": 2, "mock_response": MSG_EPUISE}})
    config["model_list"] = ml

    def plafond(f):
        return int(f.get("plafond_entree") or 0)

    limites = {"groupes": {}, "modeles": {}}
    for f, m, _, _ in gros:
        limites["modeles"][f["litellm"].format(m=m)] = plafond(f)
    for f, m, _, _ in petits:
        limites["modeles"][f["litellm"].format(m=m)] = plafond(f)
    limites["modeles"]["ollama_chat/" + ollama_modele()] = 32768
    if gros:
        limites["groupes"]["free-auto"] = min(plafond(a[0]) for a in gros)
        limites["groupes"]["free-check"] = min(plafond(a[0]) for a in verif)
        limites["groupes"]["free-code"] = limites["groupes"]["free-auto"]
    if petits:
        limites["groupes"]["free-fast"] = min([plafond(a[0]) for a in petits] + [32768])
        limites["groupes"]["free-question"] = limites["groupes"]["free-fast"]
    limites["groupes"]["free-exhausted"] = 32000
    rs = config.setdefault("router_settings", {})
    rs["fallbacks"] = [{g: ["free-exhausted"]} for g in
                       ("free-auto", "free-code", "free-check", "free-fast", "free-question")]

    dest_dir.mkdir(parents=True, exist_ok=True)
    with dest.open("w", encoding="utf-8", newline="\n") as handle:
        yaml.safe_dump(config, handle, sort_keys=False, allow_unicode=True)
    shutil.copyfile(root / "litellm" / "router_log.py", dest_dir / "router_log.py")
    shutil.copyfile(root / "litellm" / "router_contexte.py", dest_dir / "router_contexte.py")
    with (dest_dir / "limites.json").open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(limites, handle, ensure_ascii=False, indent=2)
    print(f"config: {dest}")
    print("free-auto : " + (" > ".join(a[0]["nom"] for a in gros) or "AUCUN"))
    print("free-code : " + (" > ".join(a[0]["nom"] for a in code) or "AUCUN"))
    print("free-check : " + (" > ".join(a[0]["nom"] for a in verif) or "AUCUN"))
    print("free-fast : " + (" > ".join(a[0]["nom"] for a in petits) or "AUCUN") + " > ollama")
    print("limites contexte : auto={} rapide={} verif={}".format(
        limites["groupes"].get("free-auto", 32000), limites["groupes"].get("free-fast", 32000),
        limites["groupes"].get("free-check", 32000)))
    print("ignores (cle absente): " + (", ".join(ignores) or "aucun"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
