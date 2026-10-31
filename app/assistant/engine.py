"""Moteur de base de l'assistant : garde-fous -> choix de la lens -> réponse chiffrée et sourcée.

Une lens = un domaine (marchés, météo). Ajouter un domaine (transport, agriculture…) revient à
écrire une nouvelle lens et à l'ajouter à `Assistant.LENSES`, sans toucher au reste.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

from app.assistant import guardrails, markets, weather
from app.assistant.text import find_alias, fmt_number, normalize

logger = logging.getLogger(__name__)

PRICE_WORDS = ("prix", "coute", "coutent", "cout", "cher", "chere", "combien", "tarif", "vaut", "marche", "marches",
               "moins cher", "se vend", "vend", "kilo", "kg", "sac")
TREND_WORDS = ("evolution", "evolue", "tendance", "augmente", "augmentation", "hausse", "baisse", "baisse", "monte", "monter",
               "descend", "diminue", "variation", "variations", "depuis")
COMPARE_WORDS = ("compare", "comparer", "comparaison", "entre", "ou", "versus", "vs", "moins cher")

HELP_TEXT = ("Je donne des chiffres sur le Tchad : les prix des marchés (mil, riz, sucre, huile…) et la météo "
             "(températures et pluie). Exemples : « Prix du mil à Abéché », « Le riz est moins cher à Abéché ou à Dembé ? », "
             "« Évolution du prix du sucre à N'Djamena », « Température à Moundou ».")


@dataclass
class Answer:
    text: str
    intent: str                      # price | compare | trend | weather | ask_* | no_data | help | refused_*
    lens: str | None = None          # "markets" | "weather" | None
    refused: bool = False
    data: dict[str, Any] = field(default_factory=dict)
    sources: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"text": self.text, "intent": self.intent, "lens": self.lens, "refused": self.refused,
                "data": self.data, "sources": self.sources}


def _any(norm: str, words) -> bool:
    return any(find_alias(norm, w) for w in words)


class Assistant:
    """`repo` : un ObservationRepository (ou tout objet ayant list_observations et get_stats)."""

    LENSES = ("markets", "weather")

    def __init__(self, repo, today: date | None = None) -> None:
        self.repo = repo
        self.today = today or datetime.now(UTC).date()
        self._directory: markets.MarketDirectory | None = None

    # ── entrée publique ──────────────────────────────────────────────────
    def answer(self, question: str) -> Answer:
        verdict = guardrails.check(question)
        refusal = self._refusal(verdict)
        if refusal:
            return refusal

        norm = normalize(question)
        lens = self._route(norm)
        result = None
        for attempt in (1, 2):          # une coupure réseau passagère vers la base ne doit pas faire échouer la question
            try:
                if lens == "markets":
                    result = self._markets(norm)
                elif lens == "weather":
                    result = self._weather(norm)
                break
            except Exception as exc:
                logger.warning("assistant: data unavailable (attempt %d): %r", attempt, exc)
                if attempt == 2:        # la base est vraiment indisponible : on ne devine rien
                    return Answer("Je n'arrive pas à lire les données pour le moment. Réessayez dans quelques minutes.",
                                  "unavailable", lens)

        if result is None:
            if verdict.sensitive:
                return Answer("Je ne traite pas ce sujet. Je donne uniquement des chiffres sur les prix des marchés "
                              "et la météo au Tchad, avec leur source.", "refused_sensitive", None, True)
            if guardrails.is_greeting(norm):
                return Answer("Bonjour ! " + HELP_TEXT, "help")
            return Answer(HELP_TEXT, "help")

        if verdict.sensitive:        # question de données avec un sujet délicat autour : les chiffres, sans commentaire
            result.text += " Je ne peux pas dire pourquoi les chiffres évoluent : je donne seulement les données."
        return result

    # ── garde-fous ───────────────────────────────────────────────────────
    @staticmethod
    def _refusal(verdict: guardrails.Verdict) -> Answer | None:
        if verdict.kind == "empty":
            return Answer("Posez-moi une question, par exemple : « Prix du mil à Abéché ».", "empty", None, True)
        if verdict.kind == "too_long":
            return Answer(f"Votre message est trop long. Posez une question courte (moins de {guardrails.MAX_QUESTION_CHARS} caractères).",
                          "too_long", None, True)
        if verdict.kind == "distress":
            return Answer("Je suis désolé que vous traversiez cela. Je ne suis qu'un outil de données : parlez-en à une personne de confiance "
                          "ou contactez les services d'urgence ou de santé de votre localité.", "refused_distress", None, True)
        if verdict.kind in ("abuse", "injection"):
            return Answer("Je préfère rester courtois. Posez-moi une question sur les prix des marchés ou la météo au Tchad.",
                          "refused_abuse" if verdict.kind == "abuse" else "refused_injection", None, True)
        return None

    # ── aiguillage ───────────────────────────────────────────────────────
    def _route(self, norm: str) -> str | None:
        directory = self._markets_directory()
        market_hits = directory.find(norm)
        stripped = self._strip_spans(norm, [s for _, s in market_hits])
        product = markets.find_product(stripped)
        price_intent = _any(norm, PRICE_WORDS) or _any(norm, TREND_WORDS)
        weather_intent = weather.mentions_weather(norm)
        if product:
            return "markets"
        if weather_intent and not price_intent:
            return "weather"
        if price_intent:
            return "markets"
        return None

    @staticmethod
    def _strip_spans(norm: str, spans: list[tuple[int, int]]) -> str:
        out = norm
        for start, end in sorted(spans, reverse=True):
            out = out[:start] + " " * (end - start) + out[end:]
        return out

    def _markets_directory(self) -> markets.MarketDirectory:
        if self._directory is None:
            names: list[str] = []
            try:
                stats = self.repo.get_stats() or {}
                names = list((stats.get("regions") or {}).keys())
            except Exception as exc:     # sans la liste de la base, les marchés connus d'avance suffisent
                logger.info("assistant: region list unavailable (%s)", exc)
            self._directory = markets.MarketDirectory.from_regions(names)
        return self._directory

    # ── lens marchés ─────────────────────────────────────────────────────
    def _markets(self, norm: str) -> Answer | None:
        directory = self._markets_directory()
        hits = directory.find(norm)
        stripped = self._strip_spans(norm, [s for _, s in hits])
        product = markets.find_product(stripped)
        found = [m for m, _ in hits]
        examples = ", ".join(markets.pretty(m.name) for m in directory.markets if not m.generic)[:200]

        if not product:
            return Answer("Quel produit ? Par exemple : mil, riz, sorgho, sucre, huile, oignon, niébé, sel, farine, "
                          "bœuf.", "ask_product", "markets", data={"markets": [m.name for m in found]})
        if not found:
            return Answer(f"Dans quel marché voulez-vous le prix {markets.de_product(product)} ? Marchés disponibles : {examples}.",
                          "ask_market", "markets", data={"product": product})

        trend = _any(norm, TREND_WORDS)
        if len(found) >= 2 and not trend:
            return self._compare(product, found[0], found[1])
        return self._single(product, found[0], trend)

    def _single(self, product: str, market: markets.Market, trend: bool) -> Answer:
        label = markets.DISPLAY_PRODUCT.get(product, product)
        history = markets.price_history(self.repo, product, market.name)
        if not history:
            return Answer(f"Je n'ai pas de prix {markets.de_product(product)} à {markets.pretty(market.name)}.", "no_data", "markets",
                          data={"product": product, "market": market.name})
        latest = history[0]
        data = {"product": product, "market": market.name, "value": latest.value, "unit": latest.unit,
                "date": latest.date, "source": latest.source}
        if trend:
            change = markets.price_change(history)
            if change:
                old, new, pct = change
                sign = "+" if pct > 0 else ""
                text = (f"{label.capitalize()} à {markets.pretty(market.name)} : {fmt_number(old.value, 0 if old.value >= 100 else 1)} "
                        f"({markets.fmt_month(old.date)}) → {fmt_number(new.value, 0 if new.value >= 100 else 1)} "
                        f"{markets.fmt_unit(new.unit)} ({markets.fmt_month(new.date)}), soit {sign}{fmt_number(pct)} %. "
                        f"Source {markets.SOURCE_LABEL.get(new.source, new.source)}.{markets._freshness(new.date, self.today)}")
                data.update({"previous_value": old.value, "previous_date": old.date, "change_pct": pct})
                return Answer(text, "trend", "markets", data=data, sources=[new.source])
            text = markets.describe_price(latest, self.today) + " Je n'ai pas assez d'historique pour calculer une évolution."
            return Answer(text, "trend", "markets", data=data, sources=[latest.source])
        return Answer(markets.describe_price(latest, self.today), "price", "markets", data=data, sources=[latest.source])

    def _compare(self, product: str, a: markets.Market, b: markets.Market) -> Answer:
        label = markets.DISPLAY_PRODUCT.get(product, product)
        comp = markets.compare_markets(self.repo, product, a.name, b.name)
        if comp is None:
            missing = [markets.pretty(m.name) for m in (a, b) if markets.latest_price(self.repo, product, m.name) is None]
            return Answer(f"Je ne peux pas comparer : pas de prix {markets.de_product(product)} à {' ni à '.join(missing)}.", "no_data", "markets",
                          data={"product": product, "markets": [a.name, b.name]})
        fmt = lambda p: f"{fmt_number(p.value, 0 if p.value >= 100 else 1)} {markets.fmt_unit(p.unit)}"   # noqa: E731
        lines = [f"{label.capitalize()} :",
                 f"• {markets.pretty(comp.a.market)} : {fmt(comp.a)} ({markets.fmt_month(comp.a.date)})",
                 f"• {markets.pretty(comp.b.market)} : {fmt(comp.b)} ({markets.fmt_month(comp.b.date)})"]
        if comp.cheaper is None:
            lines.append("Les deux prix sont identiques.")
        else:
            lines.append(f"Moins cher à {markets.pretty(comp.cheaper)} (écart de {fmt_number(comp.gap_pct)} %).")
        if not comp.same_period:
            lines.append("⚠️ Les deux prix ne datent pas du même mois : la comparaison est indicative.")
        lines.append(f"Source {markets.SOURCE_LABEL.get(comp.a.source, comp.a.source)}.")
        data = {"product": product, "a": comp.a.__dict__, "b": comp.b.__dict__, "cheaper": comp.cheaper,
                "gap_pct": comp.gap_pct, "same_period": comp.same_period}
        return Answer("\n".join(lines), "compare", "markets", data=data, sources=[comp.a.source, comp.b.source])

    # ── lens météo ───────────────────────────────────────────────────────
    def _weather(self, norm: str) -> Answer | None:
        place = weather.find_province(norm)
        if place is None:
            hit = [m for m, _ in self._markets_directory().find(norm) if m.province]
            place = (hit[0].province, hit[0].province) if hit else None
        if place is None:
            return Answer("Pour quelle province ou quelle ville ? Par exemple : N'Djamena, Abéché, Moundou, Sarh, Lac, Tibesti.",
                          "ask_place", "weather")
        province, word = place
        label = word.title() if word.lower() != province.lower() else weather.province_label(province)
        forecast = weather.wants_forecast(norm)
        window = 30 if weather.wants_month(norm) else 7
        want_temp, want_rain = weather.wants(norm)

        parts: list[str] = []
        data: dict[str, Any] = {"province": province}
        sources: list[str] = []
        if want_temp:
            r = weather.describe_temperature(self.repo, province, label, self.today, window)
            if r:
                parts.append(r[0]); data["temperature"] = r[1]; sources.append("Open-Meteo")
        if want_rain:
            r = weather.describe_rain(self.repo, province, label, self.today, window)
            if r:
                parts.append(r[0]); data["rain"] = r[1]; sources.append("Open-Meteo")
        if not parts:
            return Answer(f"Je n'ai pas de mesure météo pour {label}.", "no_data", "weather", data=data)
        if forecast:
            parts.insert(0, "Je n'ai pas de prévisions, seulement les dernières mesures :")
        return Answer("\n".join(parts), "weather", "weather", data=data, sources=sorted(set(sources)))
