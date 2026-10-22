# Déploiement (Render + GitHub Actions)

## Variables d'environnement Render

| Variable | Valeur | Pourquoi |
|---|---|---|
| `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` | vos clés | stockage de production |
| `COLLECTION_API_KEY` | un secret long (`python -c "import secrets; print(secrets.token_urlsafe(32))"`) | protège les endpoints d'administration |
| `GROQ_API_KEY` | votre clé | rapports IA (sinon rapport statistique de repli) |
| `ALLOWED_ORIGINS` | l'URL du site | CORS |
| **`FORWARDED_ALLOW_IPS`** | **`*`** | **sans elle, uvicorn voit l'IP du proxy Render pour tous les visiteurs : les limites « par IP » (10 collectes/h, 5 rapports/h) deviennent des limites globales partagées par tout le monde** |
| `MALLOC_ARENA_MAX` | `2` | limite la fragmentation mémoire des threads |

## Collecte automatique (tous les secteurs)

Le workflow `.github/workflows/scheduled_harvest.yml` tourne chaque jour : il réveille le
service, lance la collecte de tous les secteurs et attend le résultat. Il faut créer deux
secrets dans GitHub (Settings > Secrets and variables > Actions) :

- `APP_URL` : l'adresse du service Render, sans `/` final
- `COLLECTION_API_KEY` : la même valeur que sur Render

Lancement manuel : onglet Actions > « Daily harvest (all sectors) » > Run workflow.
