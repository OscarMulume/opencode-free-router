"""Agent « un seul interlocuteur » devant le routeur free-router.

Assemble le tout :
  1. classe la demande  → choisit le groupe LiteLLM (classeur.choisir_groupe) ;
  2. charge les compétences pertinentes → les injecte en message système (competences) ;
  3. renvoie une requête OpenAI prête à envoyer au proxy LiteLLM local (127.0.0.1:4000).

L'appelant ne voit qu'un seul agent. Le choix du modèle et l'injection des compétences
sont transparents. `preparer_requete` est pur (pas de réseau) et testable ; l'envoi
réel passe par le proxy LiteLLM (voir README) via `appeler` (nécessite le proxy lancé).
"""
import json
import os
import urllib.request

from classeur import choisir_groupe
from competences import charger_competences, selectionner, construire_prompt_systeme

PROXY_DEFAUT = os.environ.get("FREE_ROUTER_URL", "http://127.0.0.1:4000/v1/chat/completions")
PERSONA_DEFAUT = (
    "Tu es l'agent M-SEC : un assistant de développement unique. "
    "Réponds en français, de façon précise et vérifiable."
)


def preparer_requete(payload, dossier_competences=None, persona=PERSONA_DEFAUT, indice=None):
    """Transforme une requête OpenAI « brute » en requête routée + enrichie.

    @param payload : dict façon OpenAI ({"messages": [...], ...}).
    @param dossier_competences : dossier de compétences à charger (facultatif).
    @param persona : préambule système de l'agent.
    @param indice  : groupe imposé (facultatif).
    @returns dict : nouveau payload avec `model` = groupe choisi et un message système en tête.
    """
    messages = list(payload.get("messages", []))
    groupe = choisir_groupe(messages, indice=indice)

    requete_txt = ""
    for m in reversed(messages):
        if isinstance(m, dict) and m.get("role") == "user":
            requete_txt = m.get("content", "") if isinstance(m.get("content"), str) else ""
            break

    competences = []
    if dossier_competences:
        competences = selectionner(charger_competences(dossier_competences), requete_txt)
    systeme = construire_prompt_systeme(competences, base=persona)

    # Remplace/insère le message système en tête.
    sans_systeme = [m for m in messages if not (isinstance(m, dict) and m.get("role") == "system")]
    nouveaux = [{"role": "system", "content": systeme}] + sans_systeme

    sortie = dict(payload)
    sortie["model"] = groupe
    sortie["messages"] = nouveaux
    return sortie


def appeler(payload, url=PROXY_DEFAUT, timeout=120):
    """Envoie la requête préparée au proxy LiteLLM local. Nécessite le proxy lancé."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 (proxy local de confiance)
        return json.loads(r.read().decode("utf-8"))


if __name__ == "__main__":  # CLI : lit un payload JSON sur stdin, écrit le payload préparé.
    import sys
    entree = json.load(sys.stdin)
    dossier = os.environ.get("FREE_ROUTER_COMPETENCES")
    print(json.dumps(preparer_requete(entree, dossier_competences=dossier), ensure_ascii=False, indent=2))
