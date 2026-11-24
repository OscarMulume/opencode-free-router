"""Orchestrateur « un seul agent » — classement des demandes.

Objectif : exposer UN seul interlocuteur. L'appelant parle à un seul « modèle »
(l'agent), et l'orchestrateur choisit tout seul le bon groupe LiteLLM derrière
(free-auto, free-fast, free-code, free-question, free-check). L'appelant n'a pas
à savoir qu'il y a plusieurs modèles : il voit un agent avec ses capacités.

Ce module ne fait AUCUN appel réseau : il décide seulement quel groupe utiliser.
Le groupe choisi est ensuite appelé sur le proxy LiteLLM local (127.0.0.1:4000),
qui gère la mesure, la bascule et le cooldown (voir README).
"""

# Groupes générés par scripts/render-config.py (voir README).
import re

GROUPES = ("free-auto", "free-fast", "free-code", "free-question", "free-check")
GROUPE_DEFAUT = "free-fast"

# Seuil (en tokens estimés) au-delà duquel une demande est « grosse ».
SEUIL_GROS_TOKENS = 6000

MOTS_CODE = (
    "code", "fonction", "function", "bug", "refactor", "refactoris", "classe",
    "fichier", "compile", "stack trace", "exception", "test", "implément",
    "implement", "déploie", "deploy", "api", "endpoint", "sql", "migration",
)
MOTS_VERIF = (
    "vérifie", "verifie", "revois", "revue", "review", "relis", "relecture",
    "contrôle", "controle", "audit", "corrige les erreurs", "double-check", "valide",
)


def _contient(texte, mots):
    """Vrai si l'un des mots apparaît en DÉBUT de mot dans le texte.

    On ancre au début de mot (\\b) pour éviter les faux positifs en sous-chaîne
    (« api » dans « capitale », « test » dans « contexte »...), tout en acceptant
    les formes fléchies (« refactoris » → « refactorisation »).
    """
    return any(re.search(r"\b" + re.escape(mot), texte) for mot in mots)


def estimer_tokens(messages):
    """Estimation simple : ~4 caractères par token sur tout le texte des messages."""
    total = 0
    for m in messages or []:
        contenu = m.get("content", "") if isinstance(m, dict) else str(m)
        if isinstance(contenu, list):  # format OpenAI « parts »
            contenu = " ".join(
                p.get("text", "") for p in contenu if isinstance(p, dict)
            )
        total += len(contenu or "")
    return total // 4


def _dernier_message_utilisateur(messages):
    for m in reversed(messages or []):
        if isinstance(m, dict) and m.get("role") == "user":
            c = m.get("content", "")
            if isinstance(c, list):
                c = " ".join(p.get("text", "") for p in c if isinstance(p, dict))
            return (c or "").lower()
    return ""


def choisir_groupe(messages, indice=None):
    """Choisit le groupe LiteLLM pour une demande.

    @param messages : liste de messages façon OpenAI ([{role, content}, ...]).
    @param indice   : groupe imposé explicitement (facultatif). S'il est valide,
                      il est respecté tel quel.
    @returns str : un nom de groupe de GROUPES.
    """
    if indice in GROUPES:
        return indice

    texte = _dernier_message_utilisateur(messages)
    tokens = estimer_tokens(messages)

    # 1) Relecture / vérification → modèle DIFFÉRENT (free-check).
    if _contient(texte, MOTS_VERIF):
        return "free-check"

    # 2) Grosse demande d'agent (gros contexte) → free-auto (rapides only, local exclu).
    if tokens >= SEUIL_GROS_TOKENS:
        return "free-auto"

    # 3) Travail de code (petit) → free-code (meilleure qualité d'abord).
    if _contient(texte, MOTS_CODE):
        return "free-code"

    # 4) Petite question → free-question.
    if texte.strip().endswith("?") or len(texte) < 400:
        return "free-question"

    # 5) Par défaut : petites requêtes rapides.
    return GROUPE_DEFAUT
