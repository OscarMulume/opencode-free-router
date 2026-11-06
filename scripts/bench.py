"""Banc d'essai des fournisseurs : disponibilite, delai du 1er token, debit, plafond de contexte.
Usage : python bench.py [--court] [--rapport] [--seulement nom,nom]
Ecrit %LOCALAPPDATA%\\opencode-free-router\\bench.json. Aucune cle n'est ecrite ni affichee."""
import argparse, json, os, re, sys, time, urllib.request, urllib.error
import yaml
from pathlib import Path

ICI = Path(__file__).resolve().parent
SORTIE = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "opencode-free-router" / "bench.json"
SEUIL_LENT_S = 30.0
UA = {"User-Agent": "free-router-bench/1.0"}


def env(nom):
    v = os.environ.get(nom, "").strip()
    if not v and os.name == "nt":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
                v = str(winreg.QueryValueEx(k, nom)[0]).strip()
        except OSError:
            v = ""
    return v


def charge(tokens):
    """Texte de remplissage varie (~4 caracteres / token) + consigne courte."""
    mots = "route modele fichier test erreur lecture ecriture version service client donnee boucle retour".split()
    n = int(tokens * 4 / 6)
    corps = " ".join(mots[(i * 7) % len(mots)] + str(i % 97) for i in range(n))
    return corps + "\n\nIgnore le texte ci-dessus. Reponds seulement : OK."


def http_json(url, cle, timeout=20):
    req = urllib.request.Request(url, headers={**UA, "Authorization": f"Bearer {cle}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def modeles_annonces(f, cle):
    if not f.get("liste"):
        return None
    try:
        d = http_json(f["liste"], cle)
        items = d.get("data", d) if isinstance(d, dict) else d
        pre = f.get("prefixe_liste", "")
        ids = []
        for it in items:
            i = it.get("id") or it.get("name") or ""
            ids.append(i[len(pre):] if pre and i.startswith(pre) else i)
        return ids
    except Exception:
        return None


def choisir_modele(f, cle):
    ids = modeles_annonces(f, cle)
    if f.get("filtre"):
        cand = [i for i in (ids or []) if re.search(f["filtre"], i)]
        return cand[0] if cand else None
    for m in f["modeles"]:
        if ids is None or m in ids:
            return m
    return None


def appel(base, cle, modele, tokens, timeout=60):
    corps = json.dumps({"model": modele, "stream": True, "max_tokens": 40,
                        "messages": [{"role": "user", "content": charge(tokens)}]}).encode()
    req = urllib.request.Request(base + "/chat/completions", data=corps, method="POST",
                                 headers={**UA, "Authorization": f"Bearer {cle}", "Content-Type": "application/json"})
    t0 = time.time(); premier = None; n = 0
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            for ligne in r:
                ligne = ligne.decode("utf-8", "ignore").strip()
                if not ligne.startswith("data:") or ligne.endswith("[DONE]"):
                    continue
                try:
                    delta = json.loads(ligne[5:])["choices"][0].get("delta", {})
                except Exception:
                    continue
                if delta.get("content") or delta.get("reasoning_content") or delta.get("reasoning"):
                    if premier is None:
                        premier = time.time() - t0
                    n += 1
        fin = time.time() - t0
        if premier is None:
            return {"ok": False, "erreur": "reponse vide", "duree_s": round(fin, 1)}
        debit = n / (fin - premier) if fin - premier > 0.2 and n > 1 else None
        return {"ok": True, "premier_token_s": round(premier, 2), "debit_tps": round(debit, 1) if debit else None}
    except urllib.error.HTTPError as e:
        corps_err = e.read().decode("utf-8", "ignore")[:160].replace("\n", " ")
        return {"ok": False, "http": e.code, "erreur": corps_err, "duree_s": round(time.time() - t0, 1)}
    except Exception as e:
        return {"ok": False, "erreur": type(e).__name__ + ": " + str(e)[:100], "duree_s": round(time.time() - t0, 1)}


def etat_de(res):
    p = res.get("30k") or {}
    if p.get("ok"):
        return "OK" if p["premier_token_s"] < SEUIL_LENT_S else "LENT"
    if (res.get("1k") or {}).get("ok") and (res.get("30k") or {}).get("http") == 413:
        return "PETIT"  # accepte les petites requetes, refuse les grosses (contexte trop court)
    codes = {v.get("http") for v in res.values() if isinstance(v, dict)}
    if 429 in codes:
        return "EPUISE"
    return "KO"


def tester(f, court):
    vals = {k: env(k) for k in f["cles"]}
    if not all(vals.values()):
        return {"etat": "SANS CLE", "manque": [k for k, v in vals.items() if not v]}
    base = f["base"].format(**vals)
    cle = vals[f["cles"][0]]
    modele = choisir_modele(f, cle)
    if not modele:
        return {"etat": "KO", "erreur": "aucun modele attendu dans la liste du fournisseur"}
    res = {"modele": modele}
    tailles = [("1k", 1000), ("30k", 30000)] if court else [("1k", 1000), ("8k", 8000), ("30k", 30000), ("60k", 60000)]
    plafond = 0
    for nom, t in tailles:
        r = appel(base, cle, modele, t)
        res[nom] = r
        if r["ok"]:
            plafond = t
        elif nom == "1k":
            break
        time.sleep(1.5)
    res["plafond_contexte_tokens"] = plafond
    res["etat"] = etat_de(res)
    return res


def rapport(data):
    lignes = ["| Fournisseur | Modele | Etat | 1K 1er token | 30K 1er token | Debit (tok/s) | Contexte max teste | Erreurs |",
              "|---|---|---|---|---|---|---|---|"]
    for nom, r in data["fournisseurs"].items():
        if r["etat"] == "SANS CLE":
            lignes.append(f"| {nom} | - | SANS CLE | - | - | - | - | {', '.join(r['manque'])} |")
            continue
        a, b = r.get("1k") or {}, r.get("30k") or {}
        errs = "; ".join(f"{k}: {v.get('http', '')} {v.get('erreur', '')}"[:70] for k, v in r.items()
                         if isinstance(v, dict) and v.get("ok") is False) or r.get("erreur", "")
        lignes.append(f"| {nom} | {r.get('modele', '-')} | {r['etat']} | {a.get('premier_token_s', '-')} s | "
                      f"{b.get('premier_token_s', '-')} s | {b.get('debit_tps') or a.get('debit_tps') or '-'} | "
                      f"{r.get('plafond_contexte_tokens', 0)} | {errs} |")
    return "\n".join(lignes)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--court", action="store_true")
    ap.add_argument("--rapport", action="store_true", help="affiche le dernier bench.json en tableau")
    ap.add_argument("--seulement")
    a = ap.parse_args()
    if a.rapport:
        print(rapport(json.loads(SORTIE.read_text(encoding="utf-8")))); return 0
    reg = yaml.safe_load((ICI / "providers.yaml").read_text(encoding="utf-8"))["fournisseurs"]
    reg = [f for f in reg if not f.get("necessite_carte")]  # inscription avec carte : jamais testes
    if a.seulement:
        reg = [f for f in reg if f["nom"] in a.seulement.split(",")]
    data = {"date": time.strftime("%Y-%m-%d %H:%M:%S"), "court": a.court, "fournisseurs": {}}
    if a.seulement and SORTIE.exists():  # --seulement : on fusionne avec les mesures existantes
        try:
            data["fournisseurs"] = json.loads(SORTIE.read_text(encoding="utf-8"))["fournisseurs"]
        except Exception:
            pass
    for f in reg:
        print(f"... {f['nom']}", flush=True)
        data["fournisseurs"][f["nom"]] = tester(f, a.court)
    SORTIE.parent.mkdir(parents=True, exist_ok=True)
    SORTIE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    print(rapport(data))
    return 0


if __name__ == "__main__":
    sys.exit(main())
