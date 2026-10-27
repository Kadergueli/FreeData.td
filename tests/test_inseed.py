"""INSEED statistics: SDMX-ML files saved from the official portal -> observations."""
import asyncio
from datetime import date

import pytest

from app.agents.inseed import (ATTRIBUTION, DATASETS, PROVINCES, InseedAgent, load_files, parse_period,
                               parse_sdmx)
from app.cli import import_inseed
from app.services.storage import ObservationRepository

# Shape copied from a real answer of the portal (health facilities, urtpzwb), shortened.
HEALTH_XML = """<?xml version="1.0" encoding="utf-8"?>
<StructureSpecificData xmlns:message="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message">
<DataSet>
<Series R_GIONS="TD" ID_RÉGIONS="TD" REGIONID_RÉGIONS="TD" SECTEUR="PUB" ID_SECTEUR="PUB" ETABLISSEMENT_SANITAIRE="HN" ID_ETABLISSEMENT_X0020_SANITAIRE="HN" STATUT="TOT" ID_STATUT="TOT" FREQ="A">
  <Obs TIME_PERIOD="2017" OBS_VALUE="4" /><Obs TIME_PERIOD="2018" OBS_VALUE="7" /><Obs TIME_PERIOD="2019" OBS_VALUE="" />
</Series>
<Series R_GIONS="TD-LC" ID_RÉGIONS="TD-LC" REGIONID_RÉGIONS="TD-LC" SECTEUR="PRV" ID_SECTEUR="PRV" ETABLISSEMENT_SANITAIRE="CLI" ID_ETABLISSEMENT_X0020_SANITAIRE="CLI" STATUT="TOT" ID_STATUT="TOT" FREQ="A">
  <Obs TIME_PERIOD="2024" OBS_VALUE="12.5" /><Obs TIME_PERIOD="2025" OBS_VALUE="abc" />
</Series>
</DataSet></StructureSpecificData>"""
DS = DATASETS["urtpzwb"]


def test_series_become_observations_with_province_names_and_readable_codes():
    recs = parse_sdmx(HEALTH_XML, DS)
    assert [(r["year"], r["value"]) for r in recs] == [(2017, 4.0), (2018, 7.0), (2024, 12.5)]   # empty / "abc" skipped
    nat, lac = recs[0], recs[2]
    assert nat["region"] == "national" and nat["indicator"] == "Établissements de santé - public, hôpital national"
    assert lac["region"] == "Lac" and lac["indicator"] == "Établissements de santé - privé, clinique"
    assert nat["sector"] == "health" and nat["unit"] == "établissements"


def test_unknown_codes_are_kept_as_they_are_not_guessed():
    xml = HEALTH_XML.replace('ETABLISSEMENT_SANITAIRE="HN"', 'ETABLISSEMENT_SANITAIRE="ZZZ"')
    assert "public, ZZZ" in parse_sdmx(xml, DS)[0]["indicator"]


@pytest.mark.parametrize("text,expected", [
    ("2024", (2024, 1, 1)), ("2024-03", (2024, 3, 1)), ("2024-M07", (2024, 7, 1)), ("2024M12", (2024, 12, 1)),
    ("2024-Q2", (2024, 4, 1)), ("2024-03-15", (2024, 3, 15)), ("2024-13", None), ("2024-02-30", None), ("", None), ("x", None),
])
def test_period_formats(text, expected):
    assert parse_period(text) == expected


def test_documents_with_entities_are_refused():
    bomb = '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><DataSet><Series FREQ="A"/></DataSet>'
    with pytest.raises(ValueError, match="refused"):
        parse_sdmx(bomb, DS)
    with pytest.raises(ValueError, match="not a valid XML"):
        parse_sdmx("<DataSet><Series>", DS)


def test_every_province_code_has_a_region_name_and_no_duplicates():
    assert len(PROVINCES) == 24 and len(set(PROVINCES.values())) == 24
    assert PROVINCES["TD"] == "national"


def test_files_are_matched_by_name_and_problems_are_reported(tmp_path):
    good = tmp_path / "inseed_urtpzwb.xml"
    good.write_text(HEALTH_XML, encoding="utf-8")
    other = tmp_path / "inseed_unknown.xml"
    other.write_text("<x/>", encoding="utf-8")
    broken = tmp_path / "inseed_xxhsxif.xml"
    broken.write_text("<DataSet><Series>", encoding="utf-8")
    by_sector, problems = load_files([good, other, broken])
    assert list(by_sector) == ["health"] and len(by_sector["health"]) == 3
    assert any("unknown dataset" in p for p in problems) and any("not a valid XML" in p for p in problems)


def test_import_goes_through_the_pipeline_with_attribution(tmp_path):
    f = tmp_path / "inseed_urtpzwb.xml"
    f.write_text(HEALTH_XML, encoding="utf-8")
    repo = ObservationRepository(tmp_path / "t.db")
    out = asyncio.run(import_inseed([f], repo))
    assert "health: 3 read" in out and "3 stored" in out and "PROBLEM" not in out
    rows = repo.list_observations(sector="health", limit=50)
    assert {r["source"] for r in rows} == {"INSEED"}
    assert all(r["license"] == "Licence Ouverte INSEED" and ATTRIBUTION in (r["notes"] or "") for r in rows)
    assert {r["region"] for r in rows} == {"national", "Lac"}
    # running it again must not create duplicates
    asyncio.run(import_inseed([f], repo))
    assert len(repo.list_observations(sector="health", limit=50)) == 3


def test_import_without_files_explains_what_to_do(tmp_path):
    assert "probe-inseed" in asyncio.run(import_inseed([], ObservationRepository(tmp_path / "e.db")))


def test_normalize_rounds_and_dates(tmp_path):
    agent = InseedAgent(ObservationRepository(tmp_path / "n.db"), "economy",
                        [])
    obs = agent.normalize({"year": 2024, "month": 3, "day": 1, "value": 101.2345, "indicator": "Indice", "unit": "indice", "region": "national"})
    assert obs.reference_date == date(2024, 3, 1) and obs.value == 101.23 and obs.sector == "economy"
    assert agent.normalize({"year": 2024, "value": None, "indicator": "x"}) is None
