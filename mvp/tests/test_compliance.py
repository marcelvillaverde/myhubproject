from datetime import date

import pytest

from hubcarros.compliance import check_listing, status_for
from hubcarros.models import ListingStatus, RiskReport, Vehicle

TODAY = date(2026, 11, 16)


def car(description="", price=10000, mileage=40000):
    return Vehicle("d", "AB12CDE", "Ford", "Focus", 2019, price, mileage, description=description)


def codes(v, r=None):
    return {i.code for i in check_listing(v, r, TODAY)}


def test_clean_listing_is_published():
    issues = check_listing(car("Nice car, 40,000 miles, price includes all fees."), None, TODAY)
    assert issues == [] and status_for(issues) is ListingStatus.PUBLISHED


@pytest.mark.parametrize("text", ["Finance from £199 per month", "Only £150/month", "Low APR available", "Deposit of £500"])
def test_finance_trigger_without_rep_example_blocks(text):
    assert "FINANCE_NO_REP_EXAMPLE" in codes(car(text))


def test_finance_with_rep_example_passes():
    text = "Representative example: 48 monthly payments of £250. Representative 9.9% APR."
    assert "FINANCE_NO_REP_EXAMPLE" not in codes(car(text))


@pytest.mark.parametrize("text", ["Price plus £199 admin fee", "+ admin fee", "Excluding preparation fee", "Admin fee of £149 applies"])
def test_drip_pricing_blocks(text):
    assert "DRIP_PRICING" in codes(car(text))


def test_price_includes_fees_is_not_drip_pricing():
    assert "DRIP_PRICING" not in codes(car("Price includes admin fee."))


def test_sold_as_seen_blocks_unless_trade():
    assert "CONSUMER_RIGHTS_EXCLUSION" in codes(car("Sold as seen"))
    c = codes(car("Trade sale, sold as seen"))
    assert "TRADE_SALE_CHECK" in c and "CONSUMER_RIGHTS_EXCLUSION" not in c


def test_mileage_mismatch():
    assert "MILEAGE_MISMATCH" in codes(car("Only 25,000 miles", mileage=40000))
    assert "MILEAGE_MISMATCH" in codes(car("Only 25k miles", mileage=40000))
    assert "MILEAGE_MISMATCH" not in codes(car("Only 40,500 miles", mileage=40000))


def test_price_missing():
    assert "PRICE_MISSING" in codes(car(price=None))


def test_ex_vat_warns():
    assert "PRICE_EX_VAT" in codes(car("£8,000 + VAT"))


def test_history_claims_and_corroboration():
    v = car("One owner, full service history, HPI clear")
    assert "UNVERIFIED_HISTORY_CLAIM" in codes(v)
    r = RiskReport("AB12CDE", "t", "2026-11-16", previous_keepers=1)
    issues = [i for i in check_listing(v, r, TODAY) if i.code == "UNVERIFIED_HISTORY_CLAIM"]
    # one owner and HPI clear corroborated; FSH still needs evidence
    assert len(issues) == 1 and "full service history" in issues[0].message


def test_one_owner_contradiction_blocks():
    r = RiskReport("AB12CDE", "t", "2026-11-16", previous_keepers=3)
    assert "HISTORY_CONTRADICTION" in codes(car("One owner"), r)


def test_write_off_must_be_disclosed():
    r = RiskReport("AB12CDE", "t", "2026-11-16", write_off_category="S")
    assert "WRITE_OFF_NOT_DISCLOSED" in codes(car("Great car"), r)
    assert "WRITE_OFF_NOT_DISCLOSED" not in codes(car("Recorded Cat S, repaired"), r)


def test_outstanding_finance_and_stolen_block():
    r = RiskReport("AB12CDE", "t", "2026-11-16", outstanding_finance=True, stolen=True)
    assert {"FINANCE_OUTSTANDING", "STOLEN_MARKER"} <= codes(car("ok"), r)


def test_mot_expired_warning():
    r = RiskReport("AB12CDE", "t", "2026-11-16", mot_expiry="2026-01-01")
    assert "MOT_EXPIRED_NOT_DISCLOSED" in codes(car("ok"), r)
    assert "MOT_EXPIRED_NOT_DISCLOSED" not in codes(car("MOT expired, sold with new MOT on request"), r)


def test_superlative_warns_and_status_needs_review():
    issues = check_listing(car("Cheapest in the UK"), None, TODAY)
    assert {i.code for i in issues} == {"UNSUBSTANTIATED_SUPERLATIVE"}
    assert status_for(issues) is ListingStatus.NEEDS_REVIEW


def test_innocent_phrases_do_not_trigger():
    text = "Drives as it should. Comes with warranty and returns policy. Monthly servicing done."
    assert codes(car(text)) == set()
