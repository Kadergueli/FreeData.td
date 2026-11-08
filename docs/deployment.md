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

## Maintien en éveil (Cold Starts Render & WhatsApp) et Cache CDN (Cloudflare)

1. **Prévention des Cold Starts (`.github/workflows/keep_warm.yml`)** :
   - Sur l'offre gratuite de Render, le conteneur passe en veille après 15 minutes d'inactivité (30 à 50 s de redémarrage, ce qui provoque des timeouts sur les webhooks WhatsApp de Meta limités à ~15–20 s).
   - Le workflow `.github/workflows/keep_warm.yml` effectue un ping `GET /api/v1/health` toutes les 10 minutes entre **06h00 et 22h00 UTC** (07h00–23h00 heure du Tchad) en utilisant le secret `APP_URL`, ce qui maintient l'instance chaude toute la journée sans dépasser le quota gratuit de 750 h/mois (~496 h/mois actives).
   - Pour une cadence garantie à la minute près (les crons GitHub Actions pouvant fluctuer de quelques minutes en période de forte charge), ajoutez également une sonde gratuite **UptimeRobot** ou **Better Stack** toutes les 10 minutes sur `https://<votre-site>/api/v1/health` (fenêtre 06h00–22h00 UTC).

2. **Mise en cache CDN en amont (Cloudflare)** :
   - Les endpoints publics de lecture (`/api/v1/observations`, `/api/v1/stats`, `/api/v1/catalog`, `/api/v1/catalog.jsonld`, `/api/v1/catalog.dcat.json`, `/api/v1/regions`, `/api/v1/sources/freshness`, `/api/v1/export/*`, `/sitemap.xml`) émettent l'en-tête `Cache-Control: public, max-age=3600` (1 heure), tandis que `/api/v1/health` et `/api/v1/collection/scheduler-status` émettent `Cache-Control: no-store`.
   - En plaçant votre domaine derrière **Cloudflare** (mode Proxy activé + Cache Rule « Respect Origin Cache-Control » pour `/api/v1/*` et `/sitemap.xml`), 80 % à 90 % des lectures de prix des marchés, de météo et d'exports sont servies directement par le CDN sans solliciter la RAM (512 Mo) ni la bande passante de Render.

## Découvrabilité SEO & Moissonnage Open Data (Google Dataset Search, HDX, OpenDataSoft)

- **`/sitemap.xml` & `/robots.txt`** : listent le portail, la documentation et les jeux de données des 9 secteurs pour l'indexation par les moteurs de recherche.
- **`/api/v1/catalog.jsonld`** : catalogue complet au standard **schema.org/DataCatalog & Dataset** (JSON-LD) pour Google Dataset Search.
- **`/api/v1/catalog.dcat.json`** : catalogue complet au standard **DCAT-AP** (JSON-LD) pour le moissonnage automatique par HDX, OpenDataSoft et CKAN.
- **Balisage statique initial (`index.html`)** : inclut les métadonnées Microdata `schema.org/DataCatalog` et un bloc `<noscript>` listant les téléchargements directs CSV/Parquet de chaque secteur pour les robots qui n'exécutent pas JavaScript.

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

## Statistiques de l'INSEED (import depuis un PC)

Le portail `chad.opendataforafrica.org` publie les indicateurs nationaux (santé, prix, population,
éducation...) par une API SDMX protégée par Cloudflare : un serveur est souvent bloqué, et le
défi anti-robot n'est jamais contourné. En attendant une clé d'accès ou une exportation fournie
par l'INSEED, l'administrateur importe depuis son ordinateur :

```
pip install -r requirements.txt
python -m app.cli probe-inseed     # télécharge et enregistre data/raw/inseed_<flux>.xml
python -m app.cli import-inseed    # les range dans la base (par province quand l'INSEED la donne)
```

Seuls les flux dont la vraie réponse a été examinée sont importés (voir `DATASETS` dans
`app/agents/inseed.py`) ; les autres sont enregistrés mais signalés « unknown dataset ».
La mention « Source : INSEED. Contient des informations sous licence selon l'Accord de Licence
Ouverte de l'INSEED. » est conservée sur chaque donnée.

## Listes de régions et catalogue (Supabase)

Supabase ne renvoie jamais plus de 1000 lignes par requête. Pour que la liste des régions et le catalogue des
indicateurs soient exacts (comptes et dates réels), exécuter une fois `supabase/aggregates_setup.sql` dans l'éditeur
SQL. Tant que ce n'est pas fait, l'application utilise l'ancienne méthode, qui ne voit que les lignes les plus
récentes (un avertissement apparaît dans les journaux).

## Assistant WhatsApp (Meta Cloud API)

L'assistant de données (prix des marchés + météo) répond sur WhatsApp. Le canal reste **éteint** tant que les
variables ci-dessous ne sont pas toutes définies (le webhook répond alors 503).

1. Supabase : exécuter `supabase/assistant_log_setup.sql` (journal des questions et limites par numéro).
2. Meta : developers.facebook.com > créer une app « Business » > ajouter le produit **WhatsApp**. Un numéro de test
   gratuit est fourni (5 destinataires autorisés au maximum, sans vérification d'entreprise).
3. Render : définir les variables

| Variable | Valeur |
|---|---|
| `WHATSAPP_VERIFY_TOKEN` | un texte long que vous choisissez (sert à enregistrer le webhook) |
| `WHATSAPP_APP_SECRET` | Meta > Paramètres de l'app > De base > « Clé secrète » (signe chaque appel) |
| `WHATSAPP_ACCESS_TOKEN` | jeton **permanent** d'un utilisateur système (le jeton temporaire expire en 24 h) |
| `WHATSAPP_PHONE_NUMBER_ID` | WhatsApp > Configuration de l'API > « Identifiant du numéro de téléphone » |
| `WHATSAPP_HASH_SALT` | un secret long : les numéros ne sont stockés que sous forme hachée avec ce sel (ne plus le changer) |
| `WHATSAPP_DAILY_LIMIT` | questions par numéro et par jour (30 par défaut) |

4. Meta > WhatsApp > Configuration > Webhook : URL `https://<votre-site>/api/v1/whatsapp/webhook`, jeton de vérification =
   `WHATSAPP_VERIFY_TOKEN`, puis s'abonner au champ **messages**.
5. Envoyer « Prix du mil à Abéché » au numéro de test depuis un numéro autorisé.

Pour un numéro **public**, Meta exige la vérification de l'entreprise (documents officiels) et un numéro dédié :
à lancer en parallèle, c'est ce qui prend du temps. Le journal (admin > Assistant) distingue le canal `whatsapp`.

## Prix du PAM (HDX / HAPI)

HDX protège désormais le téléchargement automatique du fichier CSV des prix du PAM (réponse HTTP 202 vide).
Son API pour les programmes, HAPI, n'est pas concernée. Pour l'utiliser :

1. Créer un identifiant gratuit sur `https://hapi.humdata.org/docs` (« Generate App Identifier »).
2. L'ajouter dans les variables d'environnement de Render : `HDX_APP_IDENTIFIER` (secret : ne jamais le coller dans
   un chat, un ticket ou un dépôt). Il est envoyé dans un en-tête, jamais dans l'adresse.
3. Relancer la collecte du secteur « marchés ».

Sans cet identifiant, ou si HAPI échoue, le collecteur essaie l'ancien téléchargement CSV ; si les deux échouent,
le résultat de la collecte nomme les deux raisons.
