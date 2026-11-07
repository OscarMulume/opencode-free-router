"""Banc de QUALITE (pas seulement de vitesse), 15 taches types d'agent de code.

Chaque tache est notee automatiquement (code execute ou reponse verifiee).
Sortie : %LOCALAPPDATA%\\opencode-free-router\\qualite.json
Un modele est retenu pour free-auto s'il est RAPIDE (chaque reponse < 30 s) et FIABLE
(score >= 60 %). Aucune cle n'est ecrite ni affichee.

Usage :
  python qualite.py                       # tous les modeles annonces avec cle
  python qualite.py --seulement gemini-3.5-flash-lite,groq
  python qualite.py --rapport             # affiche le dernier qualite.json
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import bench

ICI = Path(__file__).resolve().parent
SORTIE = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "opencode-free-router" / "qualite.json"
SEUIL_SECONDES = 30.0
SEUIL_SCORE = 0.6
UA = {"User-Agent": "free-router-quality/1.0"}


def _python(texte):
    blocs = re.findall(r"```(?:[a-zA-Z0-9_+-]+)?\s*\n(.*?)```", texte, re.S)
    return (blocs[-1] if blocs else texte).strip()


def _executer(code, tests, timeout=8):
    script = code + "\n\n" + tests + "\nprint('OK')\n"
    try:
        r = subprocess.run([sys.executable, "-I", "-"], input=script, capture_output=True,
                           text=True, timeout=timeout, encoding="utf-8", errors="replace")
    except Exception:
        return False
    return r.returncode == 0 and "OK" in (r.stdout or "")


def _json(texte):
    brut = _python(texte)
    try:
        return json.loads(brut)
    except Exception:
        m = re.search(r"\{.*\}", brut, re.S)
        if not m:
            return None
        try:
            return json.loads(m.group(0))
        except Exception:
            return None


def _yaml(texte):
    import yaml
    brut = _python(texte)
    try:
        return yaml.safe_load(brut)
    except Exception:
        return None


def _contient(texte, *mots):
    bas = texte.lower()
    return all(m.lower() in bas for m in mots)


def verif_somme(texte):
    return _executer(_python(texte), "assert somme([1,2,3]) == 6\nassert somme([]) == 0\nassert somme([5]) == 5")


def verif_double(texte):
    code = _python(texte).replace(" ", "")
    return bool(re.search(r"returnn\*2", code)) or bool(re.search(r"n\s*\*\s*2", _python(texte)))


def verif_test_pair(texte):
    bas = texte.lower()
    return "def test_" in bas and "assert" in bas and "est_pair" in bas


def verif_test_unittest(texte):
    bas = texte.lower()
    return ("unittest" in bas or "testcase" in bas) and "assert" in bas and "ajoute" in bas


def verif_keyerror(texte):
    return _contient(texte, "KeyError") and ("clé" in texte.lower() or "cle" in texte.lower() or "key" in texte.lower()) \
        and ("get" in texte.lower() or " in " in texte.lower() or "vérifi" in texte.lower() or "verifi" in texte.lower())


def verif_typeerror(texte):
    bas = texte.lower()
    return "str" in bas and "int" in bas and ("convert" in bas or "str(" in bas or "int(" in bas or "transformer" in bas)


def verif_yaml(texte):
    d = _yaml(texte)
    return isinstance(d, dict) and d.get("debug") is True and d.get("nom") == "demo"


def verif_json(texte):
    d = _json(texte)
    return isinstance(d, dict) and d.get("port") == 8080 and d.get("nom") == "demo"


def verif_div(texte):
    return _executer(_python(texte), "assert div(6,3) == 2\nassert div(1,0) is None")


def verif_join(texte):
    return _executer(_python(texte), "assert f() == '123'") if "def f" in _python(texte) \
        else ("str(" in _python(texte) and "join" in _python(texte))


def verif_pytest_raises(texte):
    bas = texte.lower()
    return "pytest.raises" in bas and "valueerror" in bas and "def test_" in bas


def verif_http(texte):
    bas = texte.lower()
    return "404" in bas and "500" in bas and ("client" in bas or "serveur" in bas) and ("introuvable" in bas or "erreur" in bas)


def verif_renomme(texte):
    code = _python(texte)
    return "resultat" in code and not re.search(r"\btmp\b", code)


def verif_compte_mots(texte):
    return _executer(_python(texte),
                     "assert compte_mots('bonjour le monde') == 3\nassert compte_mots('') == 0\n"
                     "assert compte_mots('  un   deux  ') == 2")


def verif_palindrome(texte):
    return _executer(_python(texte),
                     "assert est_palindrome('Laval') is True\nassert est_palindrome('radar') is True\n"
                     "assert est_palindrome('bonjour') is False\nassert est_palindrome('une etape') is False")


TACHES = [
    ("bug-somme", "code",
     "Corrige cette fonction Python : elle oublie le dernier element.\n\n"
     "```python\ndef somme(a):\n    total = 0\n    for i in range(len(a) - 1):\n        total += a[i]\n    return total\n```\n\n"
     "Reponds uniquement avec le code corrige dans un bloc ```python```.", verif_somme),
    ("bug-double", "code",
     "Corrige cette fonction JavaScript : elle doit doubler n.\n\n```javascript\nfunction double(n) { return n + 2; }\n```\n\n"
     "Reponds uniquement avec le code corrige dans un bloc ```javascript```.", verif_double),
    ("test-pair", "test",
     "Ecris un test pytest pour cette fonction, avec au moins un cas vrai et un cas faux.\n\n"
     "```python\ndef est_pair(n):\n    return n % 2 == 0\n```\n\n"
     "Reponds uniquement avec le test dans un bloc ```python```.", verif_test_pair),
    ("test-unittest", "test",
     "Ecris un test unittest pour cette fonction, avec la classe et la methode de test.\n\n"
     "```python\ndef ajoute(a, b):\n    return a + b\n```\n\n"
     "Reponds uniquement avec le test dans un bloc ```python```.", verif_test_unittest),
    ("explique-keyerror", "explique",
     "Explique en francais, en trois phrases maximum, l'erreur Python `KeyError: 'x'` et comment l'eviter.", verif_keyerror),
    ("explique-typeerror", "explique",
     "Explique en francais, en trois phrases maximum, l'erreur Python : "
     "`TypeError: can only concatenate str (not \"int\") to str`.", verif_typeerror),
    ("modifie-yaml", "modifie",
     "Dans ce fichier YAML, mets debug a true sans changer le nom.\n\n```yaml\nnom: demo\ndebug: false\nport: 8000\n```\n\n"
     "Reponds uniquement avec le YAML dans un bloc ```yaml```.", verif_yaml),
    ("modifie-json", "modifie",
     "Dans ce JSON, remplace le port 8000 par 8080 sans changer le nom.\n\n```json\n{\"nom\": \"demo\", \"port\": 8000}\n```\n\n"
     "Reponds uniquement avec le JSON dans un bloc ```json```.", verif_json),
    ("bug-division", "code",
     "Corrige cette fonction : elle doit renvoyer None quand b vaut 0, sinon a / b.\n\n"
     "```python\ndef div(a, b):\n    return a / b\n```\n\n"
     "Reponds uniquement avec le code corrige dans un bloc ```python```.", verif_div),
    ("bug-join", "code",
     "Corrige cette ligne pour qu'elle renvoie la chaine '123' : `''.join([1, 2, 3])`.\n\n"
     "Reponds uniquement avec le code corrige dans un bloc ```python```.", verif_join),
    ("test-raises", "test",
     "Ecris un test pytest qui verifie que div(1, 0) leve ValueError, avec pytest.raises.\n\n"
     "```python\ndef div(a, b):\n    if b == 0:\n        raise ValueError('division par zero')\n    return a / b\n```\n\n"
     "Reponds uniquement avec le test dans un bloc ```python```.", verif_pytest_raises),
    ("explique-http", "explique",
     "Explique en francais, en trois phrases maximum, la difference entre une erreur HTTP 404 et une erreur 500.",
     verif_http),
    ("modifie-renomme", "modifie",
     "Renomme la variable `tmp` en `resultat` dans ce code, sans changer le comportement.\n\n"
     "```python\ndef total(a):\n    tmp = sum(a)\n    return tmp * 2\n```\n\n"
     "Reponds uniquement avec le code dans un bloc ```python```.", verif_renomme),
    ("code-compte-mots", "code",
     "Ecris une fonction Python `compte_mots(texte)` qui renvoie le nombre de mots (les espaces multiples ne comptent pas).\n\n"
     "Reponds uniquement avec le code dans un bloc ```python```.", verif_compte_mots),
    ("code-palindrome", "code",
     "Ecris une fonction Python `est_palindrome(s)` qui ignore la casse et les espaces.\n\n"
     "Reponds uniquement avec le code dans un bloc ```python```.", verif_palindrome),
]


def candidats(filtre):
    reg = json.loads((ICI / "providers.json").read_text(encoding="utf-8"))["fournisseurs"]
    out = []
    for f in reg:
        if f.get("necessite_carte") or f.get("retire") or f.get("local"):
            continue
        vals = {k: bench.env(k) for k in f["cles"]}
        if f["cles"] and not all(vals.values()):
            continue
        base = f["base"].format(**vals)
        cle = vals[f["cles"][0]] if f["cles"] else "ollama"
        for m in f["modeles"]:
            out.append((f["nom"], m, base, cle))
    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3) as r:
            installees = [m["name"] for m in json.loads(r.read())["models"]]
    except Exception:
        installees = []
    for m in ["qwen2.5-coder:3b", "qwen2.5-coder:7b"]:
        if m in installees:
            out.append(("ollama", m, "http://localhost:11434/v1", "ollama"))
            break
    if filtre:
        noms = {x.strip() for x in filtre.split(",")}
        out = [c for c in out if c[0] in noms or c[1] in noms]
    return out


def appel(base, cle, modele, prompt, timeout=SEUIL_SECONDES):
    corps = json.dumps({"model": modele, "max_tokens": 700, "temperature": 0.2,
                        "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request(base + "/chat/completions", data=corps, method="POST",
                                 headers={**UA, "Authorization": f"Bearer {cle}", "Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read().decode("utf-8"))
        texte = d["choices"][0]["message"].get("content") or ""
        return {"ok": True, "texte": texte, "duree_s": round(time.time() - t0, 1)}
    except urllib.error.HTTPError as e:
        return {"ok": False, "http": e.code, "erreur": e.read().decode("utf-8", "ignore")[:160],
                "duree_s": round(time.time() - t0, 1)}
    except Exception as e:
        return {"ok": False, "erreur": type(e).__name__ + ": " + str(e)[:100],
                "duree_s": round(time.time() - t0, 1)}


def tester_modele(nom, modele, base, cle):
    detail, ok, erreurs_api, durees = [], 0, 0, []
    for tid, typ, prompt, verif in TACHES:
        r = appel(base, cle, modele, prompt)
        if not r["ok"] and r.get("http") in (429, 503):
            time.sleep(15)
            r = appel(base, cle, modele, prompt)
        if r["ok"]:
            try:
                reussi = bool(verif(r["texte"]))
            except Exception:
                reussi = False
            durees.append(r["duree_s"])
        else:
            reussi = False
            erreurs_api += 1
        ok += int(reussi)
        detail.append({"id": tid, "type": typ, "ok": reussi, "duree_s": r["duree_s"],
                       "erreur": None if r.get("ok") else r.get("erreur")})
        print(f"  {tid:<18} {'OK ' if reussi else 'ECHEC'} {r['duree_s']:>5} s", flush=True)
        time.sleep(1.2)
    duree_max = max(durees) if durees else None
    score = ok / len(TACHES)
    rapide = duree_max is not None and duree_max < SEUIL_SECONDES
    fiable = score >= SEUIL_SCORE and erreurs_api <= 2
    return {"fournisseur": nom, "modele": modele, "score": ok, "total": len(TACHES),
            "note": round(score, 2), "duree_max_s": duree_max,
            "duree_mediane_s": sorted(durees)[len(durees) // 2] if durees else None,
            "erreurs_api": erreurs_api, "rapide": rapide, "fiable": fiable,
            "retenu_free_auto": bool(rapide and fiable), "detail": detail}


def rapport(data):
    lignes = ["| Fournisseur | Modele | Score | Note | Duree max | Erreurs API | Rapide | Fiable | free-auto |",
              "|---|---|---|---|---|---|---|---|---|"]
    for cle, r in data["fournisseurs"].items():
        lignes.append(f"| {r['fournisseur']} | {r['modele']} | {r['score']}/{r['total']} | {r['note']:.0%} | "
                      f"{r['duree_max_s'] or '-'} s | {r['erreurs_api']} | {'oui' if r['rapide'] else 'non'} | "
                      f"{'oui' if r['fiable'] else 'non'} | {'oui' if r['retenu_free_auto'] else 'non'} |")
    return "\n".join(lignes)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seulement", help="fournisseurs ou modeles separes par des virgules")
    ap.add_argument("--rapport", action="store_true")
    ap.add_argument("--taches", type=int, default=15)
    a = ap.parse_args()
    if a.rapport:
        print(rapport(json.loads(SORTIE.read_text(encoding="utf-8"))))
        return 0

    global TACHES
    TACHES = TACHES[:a.taches]
    data = {"date": time.strftime("%Y-%m-%d %H:%M:%S"), "total_taches": len(TACHES), "fournisseurs": {}}
    if SORTIE.exists():
        try:
            data["fournisseurs"] = json.loads(SORTIE.read_text(encoding="utf-8"))["fournisseurs"]
        except Exception:
            pass
    for nom, modele, base, cle in candidats(a.seulement):
        print(f"... {nom} / {modele}", flush=True)
        data["fournisseurs"][f"{nom}::{modele}"] = tester_modele(nom, modele, base, cle)
        SORTIE.parent.mkdir(parents=True, exist_ok=True)
        SORTIE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    print(rapport(data))
    return 0


if __name__ == "__main__":
    sys.exit(main())
