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
| `SUPABASE_ANON_KEY` | la clé « publishable » du projet (Project Settings > API) | permet la connexion à l'espace admin (clé publique par conception) |
| `ADMIN_EMAILS` | votre e-mail (plusieurs : séparés par des virgules) | propriétaires permanents de l'espace admin |

## Collecte automatique (tous les secteurs)

Le workflow `.github/workflows/scheduled_harvest.yml` tourne chaque jour : il réveille le
service, lance la collecte de tous les secteurs et attend le résultat. Il faut créer deux
secrets dans GitHub (Settings > Secrets and variables > Actions) :

- `APP_URL` : l'adresse du service Render, sans `/` final
- `COLLECTION_API_KEY` : la même valeur que sur Render

Lancement manuel : onglet Actions > « Daily harvest (all sectors) » > Run workflow.

## Espace administrateur (`#/admin`)

1. Supabase : exécuter `supabase/admin_setup.sql` (tables `table_admins` et `table_admin_audit`).
2. Supabase > Authentication > Users > *Add user* : créer le compte (e-mail + mot de passe),
   cocher « Auto Confirm User ». **Désactiver les inscriptions publiques** (Authentication >
   Sign In / Providers > désactiver « Allow new users to sign up »).
3. Render : définir `SUPABASE_ANON_KEY` et `ADMIN_EMAILS` (voir tableau ci-dessus).
4. Ouvrir `https://<votre-site>/#/admin` (lien « Administration » en bas de page) et se connecter.

Même connecté à Supabase, un compte absent de `ADMIN_EMAILS` / `table_admins` est refusé (403).
Chaque connexion et chaque action sensible est écrite dans `table_admin_audit`.
