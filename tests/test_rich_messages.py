"""WhatsApp answers: answer first, useful context, source, suggestions. Same numbers as the plain text."""
from datetime import date

import pytest

from app.assistant import Assistant, cache
from tests.test_assistant import ABECHE, DEMBE, FakeRepo, ask, price

TODAY = date(2026, 10, 31)


@pytest.fixture(autouse=True)
def _fresh():
    cache.clear()
    yield
    cache.clear()


def rows_millet():
    return [price(ABECHE, "Millet", 204, "2026-06-01"), price(ABECHE, "Millet", 215, "2026-03-01"),
            price(DEMBE, "Millet", 230, "2026-06-01")]


def test_price_card_has_answer_first_trend_source_and_tips():
    a = ask(rows_millet(), "prix du mil à Abéché")
    lines = a.rich.splitlines()
    assert lines[0] == "🌾 *Mil à Abéché : 204 XAF le kilo*"
    assert any(l.startswith("📉 −5,1 % depuis mars 2026 (215 → 204 XAF)") for l in lines)
    assert "📅 Relevé de juin 2026 · Source : PAM (WFP)" in a.rich
    assert any(l.startswith("⏳ Ce relevé a plus de 5 mois") for l in lines)
    assert any(l.startswith("💡 Essayez") for l in lines)
    assert "204 XAF le kilo" in a.text and "💡" not in a.text            # the plain text is untouched


def test_no_trend_line_without_older_prices():
    a = ask([price(ABECHE, "Millet", 204, "2026-06-01")], "prix du mil à Abéché")
    assert "📉" not in a.rich and "📈" not in a.rich and a.rich.startswith("🌾 *Mil à Abéché")


def test_fresh_price_has_no_stale_warning():
    a = ask([price(ABECHE, "Millet", 204, "2026-10-01")], "prix du mil à Abéché")
    assert "⏳" not in a.rich


def test_ranking_card_uses_medals():
    rows = [price(m, "Rice (imported)", v, "2026-06-01") for m, v in ((ABECHE, 700), (DEMBE, 800), ("Moundou (Logone Occidental)", 750))]
    a = ask(rows, "Où le riz est-il le moins cher ?")
    assert a.rich.splitlines()[0].startswith("🏆 *Riz importé : où c'est le moins cher*")
    assert "🥇 Abéché : 700 XAF le kilo" in a.rich and "🥈 Moundou" in a.rich and "🥉 Dembé" in a.rich


def test_compare_card():
    rows = [price(ABECHE, "Rice (imported)", 700, "2026-06-01"), price(DEMBE, "Rice (imported)", 800, "2026-06-01")]
    a = ask(rows, "Le riz est moins cher à Abéché ou à Dembé ?")
    assert a.rich.splitlines()[0].startswith("⚖️ *Riz importé : Abéché ou Dembé")
    assert "✅ Moins cher à Abéché : 700 XAF le kilo" in a.rich and "14,3 % d'écart" in a.rich


def test_several_products_card():
    rows = [price(ABECHE, "Millet", 204, "2026-06-01"), price(ABECHE, "Rice (imported)", 700, "2026-06-01")]
    a = ask(rows, "prix du mil et du riz à Abéché")
    assert a.intent == "prices" and a.rich.splitlines()[0] == "🛒 *Prix à Abéché*"
    assert "🌾 Mil : 204 XAF le kilo" in a.rich and "🌾 Riz importé : 700 XAF le kilo" in a.rich


def test_every_suggestion_is_a_question_the_assistant_understands():
    millet = rows_millet() + [price("Moundou (Logone Occidental)", "Millet", 210, "2026-06-01")]
    rice = [price(m, "Rice (imported)", v, "2026-06-01") for m, v in ((ABECHE, 700), (DEMBE, 800), ("Moundou (Logone Occidental)", 750))]
    weather = [{"sector": "environment", "region": "Ouaddai", "indicator": "Daily mean temperature", "value": 33.0,
                "unit": "°C", "reference_date": "2026-10-30", "source": "Open-Meteo Archive"}]
    rows = millet + rice + weather
    cards = [ask(rows, q) for q in ("prix du mil à Abéché", "Où le riz est-il le moins cher ?",
                                     "Le riz est moins cher à Abéché ou à Dembé ?", "prix du mil et du riz à Abéché")]
    for card in cards:
        tip = [l for l in card.rich.splitlines() if l.startswith("💡")][0]
        questions = [part.split("»")[0].strip() for part in tip.split("« ")[1:]]
        assert len(questions) == 2
        for q in questions:
            got = Assistant(FakeRepo(rows), today=TODAY).answer(q)
            assert got.intent in ("price", "ranking", "trend", "weather"), (card.intent, q, got.intent, got.text)


def test_other_answers_have_no_rich_version():
    a = ask([], "météo à Abéché")
    assert a.rich == "" and "rich" not in a.to_dict()


# --- the WhatsApp channel sends the rich version; the admin keeps the plain one --------------------
from tests.test_whatsapp import NUMBER, URL, _msg, _signed, env  # noqa: E402,F401


def test_whatsapp_sends_the_rich_message_with_a_short_welcome(env):
    client, sent, _ = env
    body, headers = _signed(_msg("Prix du mil à Abeche"))
    assert client.post(URL, content=body, headers=headers).status_code == 200
    text = sent[0][1]
    assert text.startswith("👋 Bienvenue sur FreeData.td")
    assert "🌾 *Mil à Abéché : 425 XAF le kilo*" in text and "💡 Essayez" in text
    assert len(text) <= 1500


def test_admin_answer_stays_plain(env):
    from app.assistant import Assistant
    from app.main import repository
    a = Assistant(repository).answer("Prix du mil à Abeche").to_dict()
    assert "425 XAF le kilo" in a["text"] and "*" not in a["text"] and "💡" not in a["text"]
