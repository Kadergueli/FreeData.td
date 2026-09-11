from __future__ import annotations

import json
import logging

import httpx

from app.config import settings
from app.schemas import StudyResult
from app.services.storage import ObservationRepository

logger = logging.getLogger(__name__)


class AnalysisAgent:
    """Creates evidence-bound French studies from FreeDatatd's published observations."""

    def __init__(self, repository: ObservationRepository) -> None:
        self.repository = repository

    async def study(self, sector: str | None = None) -> StudyResult:
        # Sample up to 60 representative observations
        observations = self.repository.list_observations(sector=sector, limit=60)
        if not observations:
            raise ValueError("Aucune observation publiée n'est disponible pour ce secteur.")

        compact_data = [
            {key: item.get(key) for key in ("indicator", "value", "unit", "reference_date", "region", "source")}
            for item in observations
        ]

        report = None
        used_model = "DS-StatisticalEngine"

        # Candidate Groq model IDs to try in sequence if one returns 404 / model_not_found
        candidate_models = [
            settings.groq_model,
            "llama-3.1-70b-versatile",
            "llama3-70b-8192",
            "llama3-8b-8192",
            "mixtral-8x7b-32768",
        ]
        # Deduplicate while preserving order
        seen_models = set()
        models_to_try = [m for m in candidate_models if m and not (m in seen_models or seen_models.add(m))]

        # Try Groq LLM API if key is configured
        if settings.groq_api_key:
            prompt = f"""Rédigez une note d'analyse institutionnelle et synthétique en français pour la plateforme nationale de données ouvertes du Tchad (FreeData.td), basée UNIQUEMENT sur les observations ci-dessous.

Directives de rédaction :
- Adoptez un style professionnel, exécutif et neutre (style note de synthèse pour décideurs et chercheurs).
- N'incluez AUCUN préambule ni méta-commentaire (ex: pas de "Voici l'analyse...", pas de "En tant qu'assistant...").
- Ne pas inventer de données, d'explications non vérifiées ni d'extrapolations géographiques non présentes.
- Structurez impérativement la note avec les titres suivants :
  ### 1. Synthèse Exécutive
  ### 2. Constats & Indicateurs Clés
  ### 3. Couverture Spatiale & Fiabilité
  ### 4. Limites & Recommandations

Secteur : {sector or 'Ensemble des secteurs'}
Données d'observations (JSON) :
{json.dumps(compact_data, ensure_ascii=False)}"""

            for model_id in models_to_try:
                try:
                    async with httpx.AsyncClient(timeout=20) as client:
                        response = await client.post(
                            "https://api.groq.com/openai/v1/chat/completions",
                            headers={"Authorization": f"Bearer {settings.groq_api_key}"},
                            json={
                                "model": model_id,
                                "temperature": 0.2,
                                "max_tokens": 1200,
                                "messages": [
                                    {"role": "system", "content": "Vous êtes l'analyste principal de FreeData.td. Vous produisez des notes de synthèse institutionnelles, rigoureuses et directement éditées en français sans méta-langage."},
                                    {"role": "user", "content": prompt},
                                ],
                            },
                        )
                        if response.status_code == 200:
                            content = response.json()["choices"][0]["message"]["content"]
                            if content:
                                report = content
                                used_model = f"Groq ({model_id})"
                                break
                        else:
                            logger.info("Groq model %s returned HTTP %s, trying fallback model...", model_id, response.status_code)
                except Exception as exc:
                    logger.warning("Groq request with model %s failed: %s", model_id, exc)

        # Fallback to Evidence-Bound Data Science Statistical Synthesis
        if not report:
            report = self._generate_statistical_report(sector, compact_data)
            used_model = "FreeDatatd DS-StatisticalEngine (Automated Fallback)"

        study_id = self.repository.save_study(
            sector=sector,
            model=used_model,
            observations_used=len(observations),
            report=report,
        )
        return StudyResult(id=study_id, sector=sector, model=used_model, observations_used=len(observations), report=report)

    def _generate_statistical_report(self, sector: str | None, observations: list[dict]) -> str:
        count = len(observations)
        dates = [o.get("reference_date") for o in observations if o.get("reference_date")]
        dates_str = f"du {min(dates)} au {max(dates)}" if dates else "période récente"
        regions = set(o.get("region") for o in observations if o.get("region"))
        sources = set(o.get("source") for o in observations if o.get("source"))
        indicators = set(o.get("indicator") for o in observations if o.get("indicator"))

        numeric_vals = [float(o["value"]) for o in observations if isinstance(o.get("value"), (int, float))]
        stats_text = ""
        if numeric_vals:
            avg_val = sum(numeric_vals) / len(numeric_vals)
            min_val = min(numeric_vals)
            max_val = max(numeric_vals)
            stats_text = f"- **Moyenne globale des mesures** : {avg_val:.2f}\n- **Amplitude des valeurs** : de {min_val:.2f} à {max_val:.2f}\n"

        sec_label = (sector or 'Tous Secteurs').upper()
        return f"""### 1. Synthèse Exécutive
La présente note synthétise un lot de **{count} observations publiées** dans le secteur **{sec_label}** pour la période **{dates_str}**. L'analyse s'appuie exclusivement sur les données publiques contrôlées et consolidées au sein du dépôt national FreeData.td.

### 2. Constats & Indicateurs Clés
- **Indicateurs mesurés** : {', '.join(sorted(list(indicators))[:5])}.
- **Organismes émetteurs** : {', '.join(sorted(list(sources)))}.
{stats_text}
### 3. Couverture Spatiale & Fiabilité
- **Maillage géographique** : {len(regions)} zones/régions couvertes ({', '.join(sorted(list(regions))[:5])}).
- **Niveau de validation** : Enregistrements vérifiés selon les règles d'intégrité et de traçabilité des sources officielles.

### 4. Limites & Recommandations
1. **Périmètre d'analyse** : Évaluation basée sur les séries d'observations actuellement indexées dans le catalogue.
2. **Recommandations** : Poursuivre le croisement avec les enquêtes sectorielles terrain et étendre la fréquence de collecte sur les sous-régions prioritaires.
"""
