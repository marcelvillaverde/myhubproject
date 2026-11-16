from datetime import date

from hubcarros.compliance import check_listing
from hubcarros.copywriter import draft_description
from hubcarros.models import RiskReport, Vehicle


def test_draft_states_only_facts_and_passes_compliance():
    v = Vehicle("d", "AB12CDE", "Skoda", "Octavia", 2019, 12250, 54000, fuel="diesel",
                transmission="automatic", body="estate", features=["Sat nav"])
    r = RiskReport("AB12CDE", "fixture", "2026-11-16", write_off_category="N", previous_keepers=2, mot_expiry="2027-04-18")
    text = draft_description(v, r)
    assert "Category N" in text and "54,000 miles" in text and "£12,250" in text
    v.description = text
    assert check_listing(v, r, date(2026, 11, 16)) == []
