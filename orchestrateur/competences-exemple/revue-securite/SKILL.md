---
nom: revue-securite
description: Relire du code pour les failles de sécurité OWASP courantes avant livraison.
---
Quand on te demande de relire ou vérifier du code, cherche en priorité :

- injections (SQL, commandes, chemins) et entrées non validées ;
- authentification/autorisation manquante ou contournable ;
- secrets en dur (clés, jetons, mots de passe) ;
- gestion d'erreurs qui divulgue des informations sensibles ;
- dépendances obsolètes ou vulnérables.

Pour chaque problème : explique le risque concret, puis propose un correctif minimal.
Ne signale que des problèmes réels et vérifiables ; n'invente pas de vulnérabilité.
