# opencode-free-router (français)

Un routeur local qui permet à **OpenCode** (et à tout agent de code compatible OpenAI) de continuer à travailler avec les **quotas gratuits** des fournisseurs de modèles : il mesure les fournisseurs, n'envoie les grosses requêtes qu'aux plus rapides, bascule seul en cas d'erreur de quota, et répond tout de suite par un message clair au lieu de rester bloqué.

> Réalisé par **Oscar Mulume** — [M-SEC Technology Consulting](https://oscarmulume.github.io/msec-technology-consulting/) · [Portfolio](https://oscarmulume.github.io/)
> English: [../README.md](../README.md)

## Le problème

Un agent de code envoie de gros prompts (20 à 30 000 jetons) très souvent. Les offres gratuites limitent les requêtes par minute ou par jour, certaines refusent les gros prompts (HTTP 413/429), et un modèle local sur processeur peut mettre des minutes à répondre. Résultat : l'agent reste bloqué, ou retombe sans le dire sur un fournisseur inutilisable de lenteur.

## Fonctionnement

```text
OpenCode / Aider / Continue / Hermes / tout client OpenAI
                    |
                    v
        Proxy LiteLLM local (127.0.0.1:4000)
                    |
   free-auto       grosses requêtes d'agent : seulement les fournisseurs MESURÉS < 30 s au premier jeton
                   sur 30K jetons, du plus rapide au plus lent, modèle local EXCLU
   free-fast       petites requêtes (< 6K jetons) : les plus rapides, Ollama local en dernier recours
   free-check      mêmes règles que free-auto, ordre inverse (un autre modèle relit le travail)
   free-exhausted  réponse immédiate et explicite quand tous les fournisseurs rapides sont épuisés
```

- **Banc d'essai** (`scripts/bench.py`) : mesure en direct disponibilité, délai du premier jeton et débit (requête de 1K et de 30K jetons), plafond de contexte réel, erreurs 413/429.
- **Groupes générés** depuis le banc (`scripts/render-config.py`) ; **cooldown** après échec ; **auto-réglage** toutes les 2 h (`scripts/autoreglage.py`) ; `scripts/status.ps1` affiche OK / LENT / ÉPUISÉ / SANS CLÉ avec le délai mesuré.

## Installation (Windows, PowerShell)

```powershell
git clone https://github.com/OscarMulume/opencode-free-router; cd opencode-free-router
setx GEMINI_API_KEY "<votre clé>"       # et/ou GROQ_API_KEY ... puis rouvrir le terminal
.\scripts\installer.ps1                 # venv, LiteLLM, clé locale, tâche planifiée, contrôle de santé
```

Pointez ensuite votre outil sur `http://localhost:4000/v1` avec la clé locale `LITELLM_MASTER_KEY` (générée par l'installateur, jamais affichée). Fichiers prêts à copier : dossier `integrations/` ; explications : [INTEGRATIONS.md](INTEGRATIONS.md).

## Fournisseurs

Registre : `scripts/providers.yaml`. **Un fournisseur n'est actif que si sa variable d'environnement existe.** Gemini (`GEMINI_API_KEY`), Groq (`GROQ_API_KEY`), GitHub Models (`GITHUB_MODELS_TOKEN`, jeton dédié `models: read`), Cloudflare Workers AI (`CLOUDFLARE_API_TOKEN` + `CLOUDFLARE_ACCOUNT_ID`), NVIDIA NIM (`NVIDIA_API_KEY`, désactivé tant qu'il est mesuré lent), Ollama local. **Cerebras, OpenRouter et Mistral sont désactivés dans ce dépôt : leur inscription nécessite une carte bancaire.**

**Règle :** un seul compte par fournisseur, et respect de leurs conditions d'utilisation (pas de multi-comptes pour contourner une limite).

## Limites honnêtes

- Les offres gratuites n'ont **aucune garantie** : quotas, modèles et conditions changent, un fournisseur peut être saturé à tout moment. Le routeur réduit les blocages, il ne crée pas de capacité.
- Avec un seul fournisseur rapide, une rafale de requêtes de 30K jetons peut l'épuiser ; le routeur répond alors par le message explicite « quotas épuisés ».
- Un modèle local sur un PC sans carte graphique est lent (environ 9 minutes pour 30K jetons avec un modèle 7B sur un i5-13400) : dernier recours pour les petites requêtes uniquement.
- Windows d'abord ; installateur Linux/macOS prévu à la feuille de route.

## Licence

MIT. Construit sur [LiteLLM](https://github.com/BerriAI/litellm) (MIT).
