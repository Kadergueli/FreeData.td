"""In English, no screen may show French: the static shell, the views, the source catalogue."""
import re

import pytest

# accented letters, plus French words that do not exist in English
FRENCH = re.compile(r"[éèêëàâçùûôîï]|\b(le|la|les|des|du|et|pour|aucun|aucune|données|chargement|erreur|dernier|résultats?|"
                    r"fraîcheur|statut|valeur|région|régions|télécharger|rechercher|accueil|répertoire|démographie)\b", re.I)
ROUTES = ["", "#/sectors", "#/data", "#/data?sector=demography", "#/sources", "#/insights", "#/status", "#/api", "#/terms"]


@pytest.mark.parametrize("route", ROUTES)
def test_no_french_on_the_page_in_english(probe, route):
    probe.page.add_init_script("localStorage.setItem('fd_lang', 'en')")
    probe.goto(route)
    probe.page.wait_for_timeout(800)
    assert probe.page.evaluate("document.documentElement.lang") == "en"        # the shell was translated at load
    french = [ln.strip() for ln in probe.page.evaluate("document.body.innerText").splitlines() if FRENCH.search(ln)]
    assert french == [], french
    assert probe.page_errors == []                                              # a module that fails to load would leave the shell in French


def test_demography_is_offered_everywhere_in_both_languages(probe):
    for lang, name in (("en", "DEMOGRAPHY"), ("fr", "DÉMOGRAPHIE")):
        probe.goto("#/sectors")
        probe.page.evaluate(f"localStorage.setItem('fd_lang', '{lang}')")
        probe.page.reload()                       # a hash change alone would keep the previous language
        probe.page.wait_for_selector("[data-sector=demography]")
        assert name in probe.page.inner_text("[data-sector=demography]").upper()
        probe.goto("#/data")
        probe.page.wait_for_selector('.filter-sector-btn[data-sector="demography"]')
        probe.goto("#/api")
        probe.page.wait_for_selector("text=" + name)
