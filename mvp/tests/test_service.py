import pytest

from hubcarros.ingest import parse_csv
from hubcarros.leads import LeadValidationError
from hubcarros.models import LeadRequest
from hubcarros.search import SearchFilters


def regs(result):
    return {r["title"] for r in result["results"]}


def status_by_reg(hub, dealer):
    return {r["reg"]: (r["status"], {i["code"] for i in r["issues"]}) for r in hub.compliance_report(dealer)}


def test_demo_compliance_outcomes(hub):
    n = status_by_reg(hub, "demo-northgate")
    r = status_by_reg(hub, "demo-riverside")
    assert n["DM19AAA"][0] == "published"
    assert n["DM20BBB"] == ("needs_review", {"UNVERIFIED_HISTORY_CLAIM"})  # FSH unproven; one owner corroborated
    assert "CONSUMER_RIGHTS_EXCLUSION" in n["DM18CCC"][1]
    assert {"FINANCE_NO_REP_EXAMPLE", "UNSUBSTANTIATED_SUPERLATIVE"} <= n["DM21DDD"][1]
    assert "MILEAGE_MISMATCH" in n["DM17EEE"][1]
    assert "FINANCE_OUTSTANDING" in n["DM22FFF"][1]
    assert "DRIP_PRICING" in r["RS16GGG"][1] and "MOT_EXPIRED_NOT_DISCLOSED" in r["RS16GGG"][1]
    assert r["RS19HHH"][0] == "published"  # Cat N disclosed
    assert r["RS15KKK"][0] == "blocked"  # one owner vs 3 keepers
    assert r["RS21LLL"][0] == "published"  # finance with representative example
    assert "PRICE_MISSING" in r["RS18MMM"][1]


def test_search_hides_blocked_and_ranks_verified(hub):
    res = hub.search("automatic suv under £20k")
    titles = [x["title"] for x in res["results"]]
    assert titles  # Tucson (published, verified) should be there
    assert all("Niro" not in t for t in titles)  # blocked: outstanding finance
    assert res["results"][0]["history_check"] == "checked"


def test_search_structured_filters(hub):
    res = hub.search(filters=SearchFilters(make="Skoda"))
    assert [r["title"] for r in res["results"]] == ["2019 Skoda Octavia 2.0 TDI SE L Estate"]
    assert res["results"][0]["history_alerts"]  # Cat N shown to buyer


def test_near_postcode_boosts_same_area(hub):
    res = hub.search(filters=SearchFilters(max_price=30000), near_postcode="LS6 3XY")
    for r in res["results"]:
        boosted = any("LS postcode area" in w for w in r["why"])
        assert boosted == r["dealer_postcode"].startswith("LS")
    assert any(r["dealer_postcode"].startswith("WF") for r in res["results"])


def test_get_vehicle_has_history_and_hides_blocked(hub):
    rows = {r["reg"]: r for r in hub.compliance_report("demo-riverside") + hub.compliance_report("demo-northgate")}
    ok = hub.get_vehicle(rows["RS20JJJ"]["vehicle_id"])
    assert ok["history"]["verified"] and ok["history"]["disclaimer"]
    assert hub.get_vehicle(rows["DM22FFF"]["vehicle_id"]) is None


def test_hide_needs_review_option(hub):
    hub.show_needs_review = False
    titles = [r["title"] for r in hub.search(filters=SearchFilters(make="Toyota"))["results"]]
    assert titles == []


def test_reingest_marks_sold_cars_removed(hub):
    before = hub.search(filters=SearchFilters(make="Honda"))["total_matches"]
    csv = "reg,make,model,year,mileage,price\nRS19HHH,Skoda,Octavia,2019,54000,12250\n"
    summary = hub.ingest("demo-riverside", parse_csv(csv, "demo-riverside"))
    assert summary.removed == 5
    assert before == 1 and hub.search(filters=SearchFilters(make="Honda"))["total_matches"] == 0


def test_header_failure_does_not_wipe_stock(hub):
    summary = hub.ingest("demo-riverside", parse_csv("foo,bar\n1,2\n", "demo-riverside"))
    assert summary.removed == 0 and summary.row_errors
    assert hub.search(filters=SearchFilters(make="Honda"))["total_matches"] == 1


def _jazz_id(hub):
    return next(r["vehicle_id"] for r in hub.compliance_report("demo-riverside") if r["reg"] == "RS20JJJ")


def test_lead_requires_consent(hub):
    with pytest.raises(LeadValidationError):
        hub.request_contact(LeadRequest(_jazz_id(hub), "Ana", consent_contact=False, email="ana@example.com"))


def test_lead_validation(hub):
    vid = _jazz_id(hub)
    with pytest.raises(LeadValidationError):
        hub.request_contact(LeadRequest(vid, "Ana", True))
    with pytest.raises(LeadValidationError):
        hub.request_contact(LeadRequest(vid, "Ana", True, email="not-an-email"))
    with pytest.raises(LeadValidationError):
        hub.request_contact(LeadRequest(vid, "Ana", True, phone="123"))


def test_high_intent_lead_and_duplicate(hub):
    vid = _jazz_id(hub)
    req = LeadRequest(vid, "Ana", True, email="ana@example.com", phone="07700 900123",
                      message="Is it available for a test drive on Saturday morning please?",
                      budget_gbp=15000, timeframe_days=5, wants_test_drive=True)
    out = hub.request_contact(req)
    assert out["status"] == "sent"
    lead = hub.dealer_leads("demo-riverside")[0]
    assert lead["intent_tier"] == "high" and lead["intent_score"] >= 70
    assert hub.request_contact(req)["status"] == "duplicate"


def test_low_intent_lead(hub):
    out = hub.request_contact(LeadRequest(_jazz_id(hub), "Bo", True, email="bo@example.com"))
    assert out["status"] == "sent"
    assert hub.dealer_leads("demo-riverside")[0]["intent_tier"] == "low"


def test_metrics_logged(hub):
    hub.search("hybrid")
    m = hub.metrics()
    assert m["search"] == 1 and m["ingest"] == 2


def test_free_text_model_is_inferred_from_stock(hub):
    res = hub.search("hybrid jazz")
    assert res["applied_filters"]["model"] == "Jazz" and res["applied_filters"]["make"] == "Honda"
    assert [r["title"] for r in res["results"]] == ["2020 Honda Jazz 1.5 i-MMD EX"]
