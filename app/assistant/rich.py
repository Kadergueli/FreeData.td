"""Version « message WhatsApp » des réponses : réponse en tête, contexte utile, source, suggestions.

Le texte courant (Answer.text) ne change pas : il sert l'admin, le journal et les tests. Ce module ne produit
qu'une mise en forme à partir des mêmes chiffres, jamais une donnée nouvelle."""
from __future__ import annotations

from datetime import date

from app.assistant import markets
from app.assistant.text import fmt_number

EMOJI = {
    "Oil (groundnut)": "🛢️", "Sugar": "🍬", "Salt": "🧂", "Beans (niebe)": "🫘", "Beans (niebe, red)": "🫘",
    "Onions (red)": "🧅", "Garlic": "🧄", "Fish (dry)": "🐟", "Livestock (cattle)": "🐄",
    "Livestock (goat, medium-sized castrated male)": "🐐", "Livestock (sheep, medium-sized castrated male)": "🐑",
    "Mangoes": "🥭", "Dates": "🌴", "Tomatoes (dried)": "🍅", "Pasta": "🍝", "Sweet potatoes": "🍠",
    "Groundnuts (shelled)": "🥜", "Peanut": "🥜",
}
MEDALS = ("🥇", "🥈", "🥉")


def product_emoji(product: str) -> str:
    return EMOJI.get(product, "🌾" if product.split(" ")[0] in ("Millet", "Sorghum", "Maize", "Wheat", "Rice", "Cassava") else "🛒")


def product_name(product: str) -> str:
    """« le mil » -> « Mil »."""
    label = markets.DISPLAY_PRODUCT.get(product, product)
    for article in ("le ", "la ", "les ", "l'"):
        if label.startswith(article):
            label = label[len(article):]
            break
    return label[:1].upper() + label[1:]


def _currency(unit: str) -> str:
    return (unit or "").partition("/")[0]


def _num(value: float) -> str:
    return fmt_number(value, 0 if value >= 100 else 1)


def _stale(price_date: str, today: date, plural: bool = False) -> str:
    d = markets.parse_date(price_date)
    if d and (today - d).days > 60:
        months = (today - d).days // 30
        who = "Ces relevés ont" if plural else "Ce relevé a"
        return f"⏳ {who} plus de {months} mois : le PAM publie avec du retard, les prix ont pu changer depuis."
    return ""


def _source(price_date: str, source: str) -> str:
    return f"📅 Relevé de {markets.fmt_month(price_date)} · Source : {markets.src_name(source)}"


def q_rank(product: str) -> str:
    return f"Où {markets.DISPLAY_PRODUCT.get(product, product)} est-il le moins cher ?"


def q_trend(product: str, market: str) -> str:
    return f"Évolution du prix {markets.de_product(product)} à {markets.spoken(market)}"


def q_price(product: str, market: str) -> str:
    return f"Prix {markets.de_product(product)} à {markets.spoken(market)}"


def q_weather(market: str) -> str:
    return f"Météo à {markets.spoken(market)}"


def tips(first: str, second: str) -> str:
    """Deux questions que l'assistant comprend, pour donner envie de continuer."""
    return f"💡 Essayez : « {first} » ou « {second} »"


def _lines(*lines: str) -> str:
    return "\n".join(x for x in lines if x)


def price(product: str, market: str, latest, change, today: date) -> str:
    head = f"{product_emoji(product)} *{product_name(product)} à {markets.spoken(market)} : {markets.money(latest.value, latest.unit)}*"
    move = ""
    if change:
        old, new, pct = change
        arrow = "📈" if pct > 0 else "📉" if pct < 0 else "➡️"
        sign = "+" if pct > 0 else "−" if pct < 0 else ""
        move = (f"{arrow} {sign}{fmt_number(abs(pct))} % depuis {markets.fmt_month(old.date)} "
                f"({_num(old.value)} → {_num(new.value)} {_currency(new.unit)})".replace("  ", " ").strip())
    second = q_weather(market) if change else q_trend(product, market)
    return _lines(head, move, _source(latest.date, latest.source), _stale(latest.date, today), "",
                  tips(q_rank(product), second))


def ranking(product: str, top, compared: int, expensive: bool, today: date) -> str:
    kind = "le plus cher" if expensive else "le moins cher"
    head = f"🏆 *{product_name(product)} : où c'est {kind}*  ({compared} marchés comparés)"
    rows = [f"{MEDALS[i]} {markets.spoken(p.market)} : {markets.money(p.value, p.unit)}" for i, p in enumerate(top[:3])]
    first = top[0]
    return _lines(head, *rows, _source(first.date, first.source), _stale(first.date, today), "",
                  tips(q_price(product, first.market), q_trend(product, first.market)))


def compare(product: str, comp, today: date) -> str:
    pa, pb = markets.spoken(comp.a.market), markets.spoken(comp.b.market)
    head = f"⚖️ *{product_name(product)} : {pa} ou {pb} ?*"
    newest = max(comp.a.date, comp.b.date)
    if comp.cheaper is None:
        body = f"🟰 Même prix aux deux endroits : {markets.money(comp.a.value, comp.a.unit)}"
    else:
        cheap, dear = (comp.a, comp.b) if comp.cheaper == comp.a.market else (comp.b, comp.a)
        body = _lines(f"✅ Moins cher à {markets.spoken(cheap.market)} : {markets.money(cheap.value, cheap.unit)}",
                      f"{markets.spoken(dear.market)} : {_num(dear.value)} {_currency(dear.unit)} "
                      f"(environ {fmt_number(comp.gap_pct)} % d'écart)")
    when = (_source(comp.a.date, comp.a.source) if comp.same_period else
            f"⚠️ Relevés de mois différents ({pa} : {markets.fmt_month(comp.a.date)}, {pb} : {markets.fmt_month(comp.b.date)}) : "
            "comparaison indicative.")
    best = comp.a.market if comp.cheaper in (None, comp.a.market) else comp.b.market
    return _lines(head, body, when, _stale(newest, today, plural=True), "",
                  tips(q_rank(product), q_trend(product, best)))


def several(market: str, items: list[tuple[str, str]], newest: str, source: str, missing: list[str], today: date) -> str:
    """items = [(produit, « 204 XAF le kilo »), ...]"""
    head = f"🛒 *Prix à {markets.spoken(market)}*"
    rows = [f"{product_emoji(p)} {product_name(p)} : {m}" for p, m in items]
    gap = f"Pas de prix pour : {', '.join(missing)}." if missing else ""
    return _lines(head, *rows, gap, f"📅 Relevé de {markets.fmt_month(newest)} · Source : {source}",
                  _stale(newest, today, plural=True), "",
                  tips(q_rank(items[0][0]), q_weather(market)))
