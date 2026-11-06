# Utiliser le Free Router depuis plusieurs outils

Le routeur est un serveur **compatible OpenAI** : `http://localhost:4000/v1`. Cle = variable d'environnement `LITELLM_MASTER_KEY` (jamais dans un fichier du depot). Trois modeles :

| Modele | Usage |
|---|---|
| `free-auto` | grosses requetes d'agent (jusqu'a 30K+ tokens) : uniquement les fournisseurs mesures rapides, sans Ollama |
| `free-fast` | petites questions (< 6K tokens) : les plus rapides, Ollama en dernier recours |
| `free-check` | verificateur independant (memes regles que free-auto, autre ordre) |

Si tous les fournisseurs rapides sont epuises, le routeur repond en moins de 2 s « Quotas gratuits epuises ... » au lieu de faire attendre 30 minutes. Etat : `scripts\status.ps1`.
**A paid Claude Code subscription is separate**: it does not go through this router (son propre quota, voir `/usage`) ; les outils ci-dessous sont l'alternative gratuite quand on veut le preserver.

Fichiers prets a copier : dossier `integrations/`.

| Outil | Fichier | Etat du test (06/11/2026) |
|---|---|---|
| OpenCode | `integrations/opencode.json` (ou `~/.config/opencode/opencode.json`) ; lancer `opencode run -m free-router/free-fast "..."` | **Teste** : free-fast en 4 a 7 s ; free-auto teste en mission A |
| Hermes Agent v0.20.5 | `integrations/hermes-config.yaml` -> `%LOCALAPPDATA%\hermes\config.yaml` (fournisseur `custom_providers` avec `key_env: LITELLM_MASTER_KEY`) | **Teste** avec un `HERMES_HOME` isole : reponse « OK » via le routeur (9 a 18 s, le prompt systeme de Hermes est lourd) |
| Client OpenAI Python | `integrations/client-openai.py` | **Teste** |
| curl | voir ci-dessous | **Teste** (1 s) |
| Aider | `integrations/aider.conf.yml` | **Non teste** (Aider non installe) |
| Continue (VS Code) | `integrations/continue-config.yaml` | **Non teste** (extension non installee) |

## curl

```powershell
curl http://localhost:4000/v1/chat/completions -H "Authorization: Bearer $env:LITELLM_MASTER_KEY" -H "Content-Type: application/json" -d '{"model":"free-fast","messages":[{"role":"user","content":"Reponds OK."}]}'
```

## Hermes Agent sous WSL

Le routeur n'ecoute que sur `127.0.0.1` de Windows. Deux options (**non testees**, WSL non utilise ici) :
1. WSL en reseau « mirrored » (`[wsl2] networkingMode=mirrored` dans `%USERPROFILE%\.wslconfig`) : `localhost:4000` fonctionne tel quel ;
2. sinon, adresse de l'hote Windows vue de WSL (`ip route show | awk '/default/ {print $3}'`) dans `base_url`, ET demarrer le routeur avec `--host 0.0.0.0` (a ne faire que sur un reseau de confiance : la cle maitre protege l'acces).

## Notes

- Chaque outil envoie son propre prompt systeme : les delais mesures incluent ce poids.
- Aucune cle dans ces fichiers : OpenCode et Hermes lisent `LITELLM_MASTER_KEY` ; pour Aider : `$env:OPENAI_API_KEY = $env:LITELLM_MASTER_KEY`.
