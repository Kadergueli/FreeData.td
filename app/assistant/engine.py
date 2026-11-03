"""Moteur de base de l'assistant : garde-fous -> choix de la lens -> réponse chiffrée et sourcée.

Une lens = un domaine (marchés, météo). Ajouter un domaine (transport, agriculture…) revient à
écrire une nouvelle lens et à l'ajouter à `Assistant.LENSES`, sans toucher au reste.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

from app.assistant.cache import CachedRepo
from app.assistant import guardrails, markets, rich, spellfix, weather
from app.assistant.text import find_alias, fmt_number, normalize

logger = logging.getLogger(__name__)

PRICE_WORDS = ("prix", "coute", "coutent", "cout", "cher", "chere", "combien", "tarif", "vaut", "marche", "marches",
               "moins cher", "se vend", "vend", "kilo", "kg", "sac")
TREND_WORDS = ("evolution", "evolue", "tendance", "augmente", "augmentation", "hausse", "baisse", "baisse", "monte", "monter",
               "descend", "diminue", "variation", "variations", "depuis")
CHEAPEST_WORDS = ("moins cher", "meilleur marche", "pas cher", "plus bas", "le moins", "partout", "tous les marches",
                  "quel marche", "ou acheter", "ou trouver", "ou est")
PRICEY_WORDS = ("plus cher", "le plus cher")
COMPARE_WORDS = ("compare", "comparer", "comparaison", "entre", "ou", "versus", "vs", "moins cher")

HELP_TEXT = ("Je peux vous donner les prix des marchés au Tchad (mil, riz, sucre, huile…) et la météo récente "
             "(températures et pluie), toujours avec la date et la source. Vous pouvez demander par exemple : "
             "« Prix du mil à Abéché », « Le riz est moins cher à Abéché ou à Dembé ? », "
             "« Où le sucre est-il le moins cher ? » ou « Quelle température à Moundou ? ».")


@dataclass
class Answer:
    text: str
    intent: str                      # price | compare | trend | weather | ask_* | no_data | help | refused_*
    lens: str | None = None          # "markets" | "weather" | None
    refused: bool = False
    data: dict[str, Any] = field(default_factory=dict)
    sources: list[str] = field(default_factory=list)
    rich: str = ""                   # même réponse mise en forme pour WhatsApp (emojis, lignes courtes) ; vide = utiliser text

    def to_dict(self) -> dict[str, Any]:
        out = {"text": self.text, "intent": self.intent, "lens": self.lens, "refused": self.refused,
               "data": self.data, "sources": self.sources}
        if self.rich:
            out["rich"] = self.rich
        return out


def _any(norm: str, words) -> bool:
    return any(find_alias(norm, w) for w in words)


class Assistant:
    """`repo` : un ObservationRepository (ou tout objet ayant list_observations et get_stats)."""

    LENSES = ("markets", "weather")

    def __init__(self, repo, today: date | None = None) -> None:
        self.repo = repo if isinstance(repo, CachedRepo) else CachedRepo(repo)
        self.today = today or datetime.now(UTC).date()
        self._directory: markets.MarketDirectory | None = None
        self._ctx: dict = {}
        self._fixes: list[tuple[str, str]] = []

    # ── entrée publique ──────────────────────────────────────────────────
    def answer(self, question: str, context: dict | None = None) -> Answer:
        """`context` : de quoi parlait la réponse précédente ({lens, product, market, province}) pour comprendre
        « et à Dembé ? ». Il vient du client : il est revalidé, jamais pris tel quel."""
        verdict = guardrails.check(question)
        refusal = self._refusal(verdict)
        if refusal:
            return refusal

        norm = normalize(question)
        norm, fixes = spellfix.fix(norm, self._vocabulary())
        self._ctx = self._clean_context(context)
        self._fixes = fixes
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
                    return Answer("Désolé, je n'arrive pas à lire les données pour le moment. Pouvez-vous réessayer dans quelques minutes ?",
                                  "unavailable", lens)

        if result is None:
            if verdict.sensitive:
                return Answer("Désolé, je ne traite pas ce sujet : je m'en tiens aux chiffres, "
                              "les prix des marchés et la météo au Tchad, avec leur source. Une question là-dessus ?", "refused_sensitive", None, True)
            if guardrails.is_greeting(norm):
                return Answer("Bonjour ! 👋 " + HELP_TEXT, "help")
            return Answer(HELP_TEXT, "help")

        if verdict.sensitive:        # question de données avec un sujet délicat autour : les chiffres, sans commentaire
            result.text += "\nJe ne peux pas dire pourquoi les chiffres évoluent : je donne seulement les données."
        if fixes and result.intent not in ("help",):
            shown = " et ".join(f"« {a} » comme « {b} »" for a, b in fixes[:3])
            result.text += f"\n(J'ai lu {shown}.)"
            result.data["corrected"] = [list(f) for f in fixes[:3]]
        return result

    # ── garde-fous ───────────────────────────────────────────────────────
    @staticmethod
    def _refusal(verdict: guardrails.Verdict) -> Answer | None:
        if verdict.kind == "empty":
            return Answer("Je vous écoute ! Posez-moi une question, par exemple : « Prix du mil à Abéché ».", "empty", None, True)
        if verdict.kind == "too_long":
            return Answer(f"Votre message est un peu long pour moi. Pouvez-vous le résumer en une question courte (moins de {guardrails.MAX_QUESTION_CHARS} caractères) ?",
                          "too_long", None, True)
        if verdict.kind == "distress":
            return Answer("Je suis vraiment désolé que vous traversiez cela. Je ne suis qu'un outil de données et je ne peux pas vous aider comme il le faudrait : "
                          "parlez-en dès maintenant à une personne de confiance, ou contactez les services de santé ou d'urgence de votre localité.", "refused_distress", None, True)
        if verdict.kind in ("abuse", "injection"):
            return Answer("Restons courtois, s'il vous plaît 🙂 Je suis là pour les prix des marchés et la météo au Tchad : que voulez-vous savoir ?",
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
        # suite de conversation : « et à Dembé ? » reprend le domaine de la réponse précédente
        lens = self._ctx.get("lens")
        if lens and len(norm.split()) <= 7 and (market_hits or weather.find_province(norm)):
            return lens
        return None

    @staticmethod
    def _clean_context(context: dict | None) -> dict:
        """Ne garde du contexte client que des valeurs connues (produit, marché, province, domaine)."""
        if not isinstance(context, dict):
            return {}
        out: dict = {}
        lens, product, market, province = (context.get(k) for k in ("lens", "product", "market", "province"))
        if isinstance(lens, str) and lens in ("markets", "weather"):
            out["lens"] = lens
        if isinstance(product, str) and product in markets.PRODUCT_ALIASES:
            out["product"] = product
        if isinstance(market, str) and market in {m.name for m in markets.MarketDirectory.from_regions().markets}:
            out["market"] = market
        if isinstance(province, str) and province in weather.PROVINCE_NAMES:
            out["province"] = province
        return out

    def _vocabulary(self) -> set[str]:
        vocab: set[str] = set()
        for aliases in markets.PRODUCT_ALIASES.values():
            for a in aliases:
                vocab.update(a.split())
        for m in self._markets_directory().markets:
            for a in m.aliases:
                vocab.update(a.split())
        for a in weather.all_aliases():
            vocab.update(a.split())
        for words in (PRICE_WORDS, TREND_WORDS, CHEAPEST_WORDS, weather.TEMPERATURE_WORDS, weather.RAIN_WORDS,
                      weather.GENERAL_WORDS, weather.FORECAST_WORDS):
            for w in words:
                vocab.update(w.split())
        return vocab

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
                names = list(self.repo.region_names())        # un seul appel, en cache 5 min
            except Exception as exc:     # sans la liste de la base, les marchés connus d'avance suffisent
                logger.info("assistant: region list unavailable (%s)", exc)
            self._directory = markets.MarketDirectory.from_regions(names)
        return self._directory

    # ── lens marchés ─────────────────────────────────────────────────────
    def _markets(self, norm: str) -> Answer | None:
        directory = self._markets_directory()
        hits = directory.find(norm)
        stripped = self._strip_spans(norm, [s for _, s in hits])
        products = markets.find_products(stripped)
        found = [m for m, _ in hits]
        examples = ", ".join(markets.spoken(m.name) for m in directory.markets if not m.generic)[:200]
        short = len(norm.split()) <= 7
        followup: list[str] = []

        if not products and self._ctx.get("product") and found:      # « et à Dembé ? »
            products, followup = [self._ctx["product"]], ["product"]
        if not products:
            return Answer("De quel produit parlez-vous ? Par exemple le mil, le riz, le sorgho, le sucre, l'huile, l'oignon, le niébé, le sel ou la farine.", "ask_product", "markets", data={"markets": [m.name for m in found]})
        product = products[0]

        if not found and _any(norm, CHEAPEST_WORDS) and len(products) == 1:
            return self._cheapest(product, expensive=_any(norm, PRICEY_WORDS))
        if not found and self._ctx.get("market") and short:           # « et le riz ? »
            m = next((m for m in directory.markets if m.name == self._ctx["market"]), None)
            if m:
                found, followup = [m], followup + ["market"]
        if not found:
            return Answer(f"Pour quel marché voulez-vous le prix {markets.de_product(product)} ? J'ai par exemple : {examples}.",
                          "ask_market", "markets", data={"product": product})

        trend = _any(norm, TREND_WORDS)
        if len(products) > 1 and not trend:
            return self._several(products, found[0])
        if len(found) >= 2 and not trend:
            return self._compare(product, found[0], found[1])
        answer = self._single(product, found[0], trend)
        if followup:
            answer.data["followup"] = followup
        return answer

    def _several(self, products: list[str], market: markets.Market) -> Answer:
        parts, data, sources, missing = [], [], set(), []
        for product in products:
            last = markets.latest_price(self.repo, product, market.name)
            name = markets.DISPLAY_PRODUCT.get(product, product)
            if last is None:
                missing.append(name)
                continue
            parts.append(f"{name} : {markets.money(last.value, last.unit)}")
            data.append({"product": product, "value": last.value, "unit": last.unit, "date": last.date})
            sources.add(last.source)
        where = markets.spoken(market.name)
        if not data:
            return Answer(f"Je n'ai pas encore de prix pour ces produits à {where} dans ma base.", "no_data", "markets",
                          data={"market": market.name})
        newest = max(d["date"] for d in data)
        src = " et ".join(sorted(markets.src_name(x) for x in sources))
        text = (f"Voici les derniers prix à {where} (relevé de {markets.fmt_month(newest)}, source {src}) :\n"
                + "\n".join(f"• {x}" for x in parts))
        if missing:
            text += f"\nJe n'ai pas de prix pour {', '.join(missing)} à {where}."
        text += ("\n" + markets._freshness(newest, self.today).strip().replace("ce relevé a", "ces relevés ont", 1)
                 if markets._freshness(newest, self.today) else "")
        shown = [(d["product"], markets.money(d["value"], d["unit"])) for d in data]
        return Answer(text, "prices", "markets", data={"market": market.name, "product": products[0], "items": data},
                      sources=sorted(sources), rich=rich.several(market.name, shown, newest, src, missing, self.today))

    def _cheapest(self, product: str, expensive: bool = False) -> Answer:
        ranked = markets.ranking(self.repo, product)
        label = markets.DISPLAY_PRODUCT.get(product, product)
        if len(ranked) < 2:
            return Answer(f"Je n'ai pas assez de marchés avec un prix récent {markets.de_product(product)} pour les classer. "
                          "Dites-moi plutôt un marché précis.", "no_data", "markets", data={"product": product})
        if expensive:
            ranked = ranked[::-1]
        top = ranked[:3]
        first = top[0]
        others = "".join(f", puis {markets.spoken(p.market)} ({fmt_number(p.value, 0 if p.value >= 100 else 1)})"
                         for i, p in enumerate(top[1:]))
        kind = "le plus cher" if expensive else "le moins cher"
        text = (f"Pour {label}, c'est à {markets.spoken(first.market)} que c'est {kind} : {markets.money(first.value, first.unit)}"
                f"{others}. J'ai comparé {len(ranked)} marchés (relevé de {markets.fmt_month(first.date)}, source "
                f"{markets.src_name(first.source)}).{markets._freshness(first.date, self.today)}")
        return Answer(text, "ranking", "markets", data={"product": product, "ranking": [{"market": p.market, "value": p.value, "date": p.date} for p in top]},
                      sources=[first.source], rich=rich.ranking(product, top, len(ranked), expensive, self.today))

    def _single(self, product: str, market: markets.Market, trend: bool) -> Answer:
        label = markets.DISPLAY_PRODUCT.get(product, product)
        history = markets.price_history(self.repo, product, market.name)
        if not history:
            return Answer(f"Je n'ai pas encore de prix {markets.de_product(product)} à {markets.spoken(market.name)} dans ma base.", "no_data", "markets",
                          data={"product": product, "market": market.name})
        latest = history[0]
        data = {"product": product, "market": market.name, "value": latest.value, "unit": latest.unit,
                "date": latest.date, "source": latest.source}
        if trend:
            change = markets.price_change(history)
            if change:
                old, new, pct = change
                word = "plus" if pct > 0 else "moins"
                move = "est passé" if pct != 0 else "est resté"
                span = (f"de {markets.money(old.value, old.unit)} en {markets.fmt_month(old.date)} à "
                        f"{markets.money(new.value, new.unit)} en {markets.fmt_month(new.date)}")
                if pct == 0:
                    text = f"À {markets.spoken(market.name)}, {label} n'a pas bougé : {markets.money(new.value, new.unit)} en {markets.fmt_month(new.date)} comme en {markets.fmt_month(old.date)}."
                else:
                    text = (f"À {markets.spoken(market.name)}, {label} {move} {span}, soit {fmt_number(abs(pct))} % de {word}. "
                            f"(Source : {markets.src_name(new.source)}.)")
                text += markets._freshness(new.date, self.today)
                data.update({"previous_value": old.value, "previous_date": old.date, "change_pct": pct})
                return Answer(text, "trend", "markets", data=data, sources=[new.source],
                              rich=rich.price(product, market.name, latest, change, self.today))
            text = markets.describe_price(latest, self.today) + " Je n'ai pas assez de relevés plus anciens pour dire comment il évolue."
            return Answer(text, "trend", "markets", data=data, sources=[latest.source],
                          rich=rich.price(product, market.name, latest, None, self.today)
                          + "\nℹ️ Pas assez de relevés plus anciens pour mesurer l'évolution.")
        return Answer(markets.describe_price(latest, self.today), "price", "markets", data=data, sources=[latest.source],
                      rich=rich.price(product, market.name, latest, markets.price_change(history), self.today))

    def _compare(self, product: str, a: markets.Market, b: markets.Market) -> Answer:
        label = markets.DISPLAY_PRODUCT.get(product, product)
        comp = markets.compare_markets(self.repo, product, a.name, b.name)
        if comp is None:
            missing = [markets.spoken(m.name) for m in (a, b) if markets.latest_price(self.repo, product, m.name) is None]
            return Answer(f"Je ne peux pas comparer : je n'ai pas encore de prix {markets.de_product(product)} à {' ni à '.join(missing)}.", "no_data", "markets",
                          data={"product": product, "markets": [a.name, b.name]})
        pa, pb = markets.spoken(comp.a.market), markets.spoken(comp.b.market)
        if comp.cheaper is None:
            text = (f"{label.capitalize()} coûte pareil à {pa} et à {pb} : {markets.money(comp.a.value, comp.a.unit)} "
                    f"(relevé de {markets.fmt_month(comp.a.date)}, source {markets.src_name(comp.a.source)}).")
        else:
            cheap, dear = (comp.a, comp.b) if comp.cheaper == comp.a.market else (comp.b, comp.a)
            text = (f"{label.capitalize()} est moins cher à {markets.spoken(cheap.market)} : {markets.money(cheap.value, cheap.unit)}, "
                    f"contre {fmt_number(dear.value, 0 if dear.value >= 100 else 1)} à {markets.spoken(dear.market)}, "
                    f"soit environ {fmt_number(comp.gap_pct)} % d'écart.")
            if comp.same_period:
                text += f" (Relevés de {markets.fmt_month(comp.a.date)}, source {markets.src_name(comp.a.source)}.)"
            else:
                text += (f" Attention, ces prix ne datent pas du même mois ({markets.spoken(comp.a.market)} : {markets.fmt_month(comp.a.date)}, "
                         f"{markets.spoken(comp.b.market)} : {markets.fmt_month(comp.b.date)}), la comparaison est donc indicative.")
        text += markets._freshness(max(comp.a.date, comp.b.date), self.today).replace("ce relevé a", "ces relevés ont", 1)
        data = {"product": product, "a": comp.a.__dict__, "b": comp.b.__dict__, "cheaper": comp.cheaper,
                "gap_pct": comp.gap_pct, "same_period": comp.same_period}
        return Answer(text, "compare", "markets", data=data, sources=[comp.a.source, comp.b.source],
                      rich=rich.compare(product, comp, self.today))

    # ── lens météo ───────────────────────────────────────────────────────
    def _weather(self, norm: str) -> Answer | None:
        place = weather.find_province(norm)
        if place is None:
            hit = [m for m, _ in self._markets_directory().find(norm) if m.province]
            place = (hit[0].province, hit[0].province) if hit else None
        if place is None and self._ctx.get("province") and (len(norm.split()) <= 7):     # « et la pluie ? »
            place = (self._ctx["province"], self._ctx["province"])
        if place is None:
            return Answer("Pour quelle ville ou quelle province ? Par exemple N'Djamena, Abéché, Moundou, Sarh, le Lac ou le Tibesti.",
                          "ask_place", "weather")
        province, word = place
        label = weather.city_label(word, province)
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
            return Answer(f"Je n'ai pas encore de mesure météo pour {label} dans ma base.", "no_data", "weather", data=data)
        if forecast:
            parts.insert(0, "Je n'ai pas de prévisions pour demain, mais voici les dernières mesures. 🌤️")
        return Answer("\n\n".join(parts), "weather", "weather", data=data, sources=sorted(set(sources)))
