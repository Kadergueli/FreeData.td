# Déploiement (Render + GitHub Actions)

## Variables d'environnement Render

| Variable | Valeur | Pourquoi |
|---|---|---|
| `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` | vos clés | stockage de production |
| `READ_RATE_LIMIT_PER_MINUTE`, `EXPORT_RATE_LIMIT_PER_MINUTE` | `120` / `10` (par défaut) | plafonds de lecture par IP de l'API publique |
| `COLLECTION_API_KEY` | un secret long (`python -c "import secrets; print(secrets.token_urlsafe(32))"`) | protège les endpoints d'administration |
| `GROQ_API_KEY` | votre clé | rapports IA (sinon rapport statistique de repli) |
| `ALLOWED_ORIGINS` | l'URL du site | CORS |
| **`FORWARDED_ALLOW_IPS`** | **`*`** | **sans elle, uvicorn voit l'IP du proxy Render pour tous les visiteurs : les limites « par IP » (lecture 120/min, exports 10/min, 5 rapports/h, tentatives de connexion admin) deviennent des limites globales partagées par tout le monde** |
| `MALLOC_ARENA_MAX` | `2` | limite la fragmentation mémoire des threads |
| `SUPABASE_ANON_KEY` | la clé « publishable » du projet (Project Settings > API) | permet la connexion à l'espace admin (clé publique par conception) |
| `ADMIN_EMAILS` | votre e-mail (plusieurs : séparés par des virgules) | propriétaires permanents de l'espace admin |

## Collecte automatique (tous les secteurs)

Le workflow `.github/workflows/scheduled_harvest.yml` tourne chaque jour : il réveille le
service, lance la collecte des secteurs qui sont dus (chaque secteur a son rythme : quotidien, hebdomadaire ou mensuel, voir `app/services/cadence.py`) et attend le résultat. `?force=true` sur l'appel `run-scheduled-harvest` collecte tout. Il faut créer deux
secrets dans GitHub (Settings > Secrets and variables > Actions) :

- `APP_URL` : l'adresse du service Render, sans `/` final
- `COLLECTION_API_KEY` : la même valeur que sur Render

Lancement manuel : onglet Actions > « Daily harvest (sectors that are due) » > Run workflow.

## Espace administrateur (`#/admin`)

1. Supabase : exécuter `supabase/admin_setup.sql` (tables `table_admins` et `table_admin_audit`).
2. Supabase > Authentication > Users > *Add user* : créer le compte (e-mail + mot de passe),
   cocher « Auto Confirm User ». **Désactiver les inscriptions publiques** (Authentication >
   Sign In / Providers > désactiver « Allow new users to sign up »).
3. Render : définir `SUPABASE_ANON_KEY` et `ADMIN_EMAILS` (voir tableau ci-dessus).
4. Ouvrir `https://<votre-site>/#/admin` (lien « Administration » en bas de page) et se connecter.

Même connecté à Supabase, un compte absent de `ADMIN_EMAILS` / `table_admins` est refusé (403).
Chaque connexion et chaque action sensible est écrite dans `table_admin_audit`.

## Historique des collectes (admin > Collectes)

Exécuter une fois `supabase/harvest_runs_setup.sql` (table `table_harvest_runs`, additive).
Chaque collecte (planificateur, workflow GitHub, espace admin) y est enregistrée : début, fin,
déclencheur, secteurs, statut (`completed`, `partial`, `failed`, `interrupted`) et raisons d'échec.
Une collecte restée « en cours » après un redémarrage est marquée `interrupted`.

## Quarantaine des valeurs suspectes (admin > Qualité)

Exécuter une fois `supabase/quarantine_setup.sql` (table `table_quarantine`, additive).
Une valeur impossible ou hors domaine (signalée `SUPERVISOR_REVIEW` : humidité > 100 %, température
hors plage, rendement négatif...) n'est plus publiée automatiquement : elle attend dans l'onglet
**Qualité**. L'administrateur la valide telle quelle, la corrige ou la rejette ; seules les valeurs
validées ou corrigées arrivent dans `table_public` (colonne `approuve_par` = e-mail du relecteur).
Une valeur déjà tranchée n'est pas reproposée à la collecte suivante, sauf si elle change.
Chaque décision figure dans le journal d'audit ; l'aperçu affiche une alerte tant qu'il reste des valeurs en attente.

## Gestion des données, rapports et équipe (admin > Données / Rapports IA / Équipe)

Exécuter une fois `supabase/data_admin_setup.sql` (table `table_deleted_observations`, additive).

- **Données** : recherche d'une valeur publiée, correction ou suppression. Un motif est obligatoire,
  l'action est écrite dans le journal (avant / après). Une valeur supprimée est archivée et peut être
  restaurée. La collecte suivante ne défait pas la décision tant que la source donne la même valeur ;
  si la source publie une valeur révisée, celle-ci est publiée.
- **Rapports IA** : suppression d'un rapport erroné ou obsolète (motif obligatoire).
- **Équipe** : réservée aux propriétaires (`ADMIN_EMAILS`). Ajouter un administrateur = saisir son e-mail,
  après avoir créé son compte dans Supabase > Authentication > Users (« Auto Confirm User »).
  Le retirer coupe son accès immédiatement. Un propriétaire permanent ne peut pas être retiré ici.
