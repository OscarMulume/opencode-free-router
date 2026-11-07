"""Reduction de contexte avant appel (Q3).

LiteLLM appelle async_pre_call_hook avant de choisir un deploiement. On estime les tokens
(environ 4 caracteres par token), on lit %LOCALAPPDATA%\\opencode-free-router\\limites.json (genere par
render-config.py), puis on reduit si necessaire :
1. troncature des anciennes sorties d'outils ;
2. resume extractif des anciens messages (debut + fin) ;
3. suppression des plus anciens blocs en gardant le systeme et les 8 derniers messages.
Les chaines assistant(tool_calls) -> tool sont preservees. Aucun contenu n'est journalise.
"""
import json
import os
import time
from pathlib import Path

from litellm.integrations.custom_logger import CustomLogger

DEFAUT = 32000
MARGE = 0.8
LOG = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "opencode-free-router" / "contexte.log"


def _texte(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        morceaux = []
        for p in content:
            if isinstance(p, dict):
                morceaux.append(str(p.get("text") or p.get("content") or ""))
            else:
                morceaux.append(str(p))
        return "".join(morceaux)
    if content is None:
        return ""
    return str(content)


def estimer(messages):
    return sum(4 + len(_texte(m.get("content"))) // 4 for m in messages)


def _tronquer(texte, maxi):
    if len(texte) <= maxi:
        return texte
    return texte[:maxi] + "\n[... tronque pour tenir dans la fenetre]"


def _resume(texte, maxi=500):
    if len(texte) <= maxi:
        return texte
    return texte[:300] + "\n[...] \n" + texte[-150:]


def reduire(messages, limite):
    seuil = int(limite * MARGE)
    actions = []
    messages = [dict(m) for m in messages]
    avant = estimer(messages)
    if avant <= seuil:
        return messages, avant, actions

    outils = [i for i, m in enumerate(messages) if m.get("role") == "tool"]
    for i in outils[:-2]:
        t = _texte(messages[i].get("content"))
        if len(t) > 200:
            messages[i]["content"] = _tronquer(t, 200)
            actions.append("outil_tronque")
    if estimer(messages) <= seuil:
        return messages, estimer(messages), actions

    debut = max(1, len(messages) - 8)
    for i in range(1, debut):
        if messages[i].get("role") == "system":
            continue
        t = _texte(messages[i].get("content"))
        if len(t) > 500:
            messages[i]["content"] = _resume(t)
            actions.append("message_resume")
    if estimer(messages) <= seuil:
        return messages, estimer(messages), actions

    systeme = [m for m in messages if m.get("role") == "system"]
    queue = messages[-8:]
    while queue and queue[0].get("role") == "tool":
        queue = queue[1:]
    omis = len(messages) - len(systeme) - len(queue)
    note = {"role": "system", "content": f"[{omis} anciens messages omis pour tenir dans la fenetre de contexte]"}
    messages = systeme + [note] + queue
    actions.append("anciens_omis")

    if estimer(messages) > seuil:
        for m in messages:
            if m.get("role") == "tool":
                m["content"] = _tronquer(_texte(m.get("content")), 800)
        for m in messages:
            if m.get("role") == "system":
                continue
            t = _texte(m.get("content"))
            if len(t) > 2000:
                m["content"] = _tronquer(t, 2000)
                actions.append("dernier_tronque")
    return messages, estimer(messages), actions


def charger_limites():
    chemin = Path(os.environ.get("FREE_ROUTER_LIMITS") or
                  Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "opencode-free-router" / "limites.json")
    try:
        return json.loads(chemin.read_text(encoding="utf-8"))
    except Exception:
        return {}


def limite_pour(model, limites):
    for cle in (model, "opencode-free-router/" + model, model.split("/")[-1]):
        if cle in (limites.get("groupes") or {}):
            return int(limites["groupes"][cle])
    for cle in (model, "opencode-free-router/" + model):
        if cle in (limites.get("modeles") or {}):
            return int(limites["modeles"][cle])
    return DEFAUT


def _journaliser(row):
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        pass


class RouterContext(CustomLogger):
    async def async_pre_call_hook(self, user_api_key_dict, cache, data, call_type):
        if os.environ.get("FREE_ROUTER_CONTEXT", "1") == "0":
            return data
        messages = data.get("messages") or []
        if not messages:
            return data
        model = str(data.get("model") or "")
        limites = charger_limites()
        limite = limite_pour(model, limites)
        avant = estimer(messages)
        if limite <= 0 or avant <= int(limite * MARGE):
            return data
        nouveaux, apres, actions = reduire(messages, limite)
        data["messages"] = nouveaux
        _journaliser({"heure": time.strftime("%Y-%m-%d %H:%M:%S"), "groupe": model,
                      "limite": limite, "avant_est": avant, "apres_est": apres,
                      "actions": sorted(set(actions))})
        return data


proxy_handler_instance = RouterContext()
