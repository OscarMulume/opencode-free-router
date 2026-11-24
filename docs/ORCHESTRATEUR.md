# Orchestrateur « un seul agent » + compétences portables

Cette couche se pose **devant** le routeur free-router. Elle réalise l'idée : un seul
interlocuteur (« l'agent »), qui derrière utilise plusieurs modèles gratuits comme s'il
n'en était qu'un seul, avec ses propres capacités (compétences / skills).

```text
   ton client (OpenCode, Codex, Continue, Aider, un chat...)
                       |
                       v
         orchestrateur/agent.py  (preparer_requete)
            |  1. classe la demande  → choisit le groupe
            |  2. charge les compétences utiles → message système
            v
     proxy LiteLLM local 127.0.0.1:4000  (free-auto / free-code / free-check / ...)
            |  mesure, bascule auto, cooldown  (voir README)
            v
     Gemini · Groq · GitHub Models · Cloudflare · NVIDIA NIM · Ollama
```

## 1. Un seul agent, plusieurs modèles (transparent)

`orchestrateur/classeur.py` → `choisir_groupe(messages, indice=None)` décide tout seul
quel groupe LiteLLM utiliser, sans que l'appelant ait à le savoir :

| Demande | Groupe choisi |
|---|---|
| « relis / vérifie / revue / audit... » | `free-check` (modèle **différent** pour la relecture) |
| gros contexte (≥ 6000 tokens estimés) | `free-auto` (rapides seulement, local exclu) |
| travail de code (bug, fonction, refactor, API...) | `free-code` (meilleure qualité d'abord) |
| petite question | `free-question` |
| reste | `free-fast` |

La correspondance se fait par **début de mot** (`\b`) pour éviter les faux positifs
(« api » dans « capitale »). On peut forcer un groupe via `indice`.

## 2. Compétences (skills) portables entre agents

`orchestrateur/competences.py` charge des dossiers `SKILL.md` (frontmatter `nom` /
`description` + corps) et assemble un **message système**. Comme c'est du simple texte
injecté en `role: system`, les mêmes compétences marchent avec **n'importe quel** agent
compatible OpenAI (OpenCode, Codex, Continue, Aider, ou Claude/Gemini derrière le proxy).

- `charger_competences(dossier)` → liste des compétences.
- `selectionner(competences, requete)` → ne garde que les pertinentes (mots communs).
- `construire_prompt_systeme(competences, base=persona)` → le préambule système.

Exemple fourni : `orchestrateur/competences-exemple/revue-securite/`.

## 3. Mettre bout à bout

`orchestrateur/agent.py` :

```python
from agent import preparer_requete, appeler

payload = {"messages": [{"role": "user", "content": "Corrige ce bug dans le login"}]}
prep = preparer_requete(payload, dossier_competences="orchestrateur/competences-exemple")
# prep["model"] == "free-code" ; un message système (persona + compétences) est ajouté
reponse = appeler(prep)   # envoie au proxy LiteLLM local (doit être lancé)
```

En ligne de commande (lit un payload JSON sur stdin, écrit le payload préparé) :

```bash
echo '{"messages":[{"role":"user","content":"relis ce code"}]}' | \
  FREE_ROUTER_COMPETENCES=orchestrateur/competences-exemple python orchestrateur/agent.py
```

## Tests

`python -m unittest tests.test_orchestrateur` — classement, chargement/sélection des
compétences, assemblage du prompt et préparation de requête. Aucun appel réseau.

## À venir

- Petit serveur HTTP compatible OpenAI (`/v1/chat/completions`) exposant l'agent sous un
  seul nom de modèle, pour le brancher tel quel dans n'importe quel client.
- Chargement des compétences depuis plusieurs sources (dossier local + dépôt Git).
