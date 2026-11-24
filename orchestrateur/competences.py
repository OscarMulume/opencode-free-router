"""Pont de « compétences » (skills) portables.

Une compétence = un dossier contenant un fichier SKILL.md :

    ---
    nom: revue-securite
    description: Relire du code pour les failles OWASP courantes.
    ---
    (corps : instructions détaillées...)

Ce module charge ces compétences et assemble un préambule de prompt système.
Comme il s'agit de simple texte injecté en message « system », il fonctionne avec
N'IMPORTE QUEL agent compatible OpenAI (OpenCode, Codex, Continue, Aider, Claude via
proxy, Gemini via proxy...). Les compétences sont donc portables d'un agent à l'autre.

Aucun appel réseau, aucune exécution de code tiers : on ne lit que du texte.
"""
import re
from pathlib import Path

_FRONTMATTER = re.compile(r"^\s*---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)


def _parser_frontmatter(texte):
    """Extrait un frontmatter clé: valeur minimal (sans dépendance YAML) + le corps."""
    m = _FRONTMATTER.match(texte)
    if not m:
        return {}, texte.strip()
    entete_brut, corps = m.group(1), m.group(2)
    entete = {}
    for ligne in entete_brut.splitlines():
        if ":" in ligne:
            cle, _, val = ligne.partition(":")
            entete[cle.strip().lower()] = val.strip()
    return entete, corps.strip()


def charger_competences(dossier):
    """Charge toutes les compétences d'un dossier (chaque sous-dossier avec SKILL.md).

    @returns list[dict] : [{nom, description, corps, chemin}], trié par nom.
    """
    base = Path(dossier)
    competences = []
    if not base.is_dir():
        return competences
    for skill in sorted(base.rglob("SKILL.md")):
        entete, corps = _parser_frontmatter(skill.read_text(encoding="utf-8"))
        nom = entete.get("nom") or entete.get("name") or skill.parent.name
        competences.append({
            "nom": nom,
            "description": entete.get("description", ""),
            "corps": corps,
            "chemin": str(skill),
        })
    return competences


def _mots(texte):
    return set(re.findall(r"[a-zà-ÿ0-9]{4,}", (texte or "").lower()))


def selectionner(competences, requete, maximum=5):
    """Sélectionne les compétences pertinentes pour une requête.

    Score = nombre de mots en commun entre la requête et (nom + description).
    Les compétences sans aucun mot commun sont écartées. Renvoie au plus `maximum`.
    """
    mots_requete = _mots(requete)
    notees = []
    for c in competences:
        mots_comp = _mots(c["nom"] + " " + c["description"])
        score = len(mots_requete & mots_comp)
        if score > 0:
            notees.append((score, c))
    notees.sort(key=lambda t: (-t[0], t[1]["nom"]))
    return [c for _, c in notees[:maximum]]


def construire_prompt_systeme(competences, base=""):
    """Assemble un message système à partir des compétences sélectionnées.

    @param base : préambule éventuel (persona de l'agent) placé en tête.
    @returns str : texte prêt à injecter comme message role=system.
    """
    morceaux = []
    if base:
        morceaux.append(base.strip())
    if competences:
        morceaux.append("# Compétences chargées")
        for c in competences:
            titre = c["nom"]
            if c["description"]:
                titre += f" — {c['description']}"
            morceaux.append(f"## {titre}\n{c['corps']}".strip())
    return "\n\n".join(morceaux).strip()
