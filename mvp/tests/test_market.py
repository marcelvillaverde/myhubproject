from datetime import date, timedelta

from hubcarros.db import Database
from hubcarros.ingest import parse_csv
from hubcarros.market import load_listings, quote, ticker_for
from hubcarros.models import Dealer, Vehicle
from hubcarros.service import Hub

D0 = date(2026, 10, 1)
HEADER = "reg,make,model,year,mileage,price,description\n"


def stock(*rows):
    return HEADER + "".join(f"{r},Toyota,Yaris,2019,{m},{p},Clean car\n" for r, m, p in rows)


def make_hub():
    hub = Hub(Database(":memory:"), None, today=D0 + timedelta(days=40))
    hub.register_dealer(Dealer("d1", "Dealer One", "LS1 1AA"))
    return hub


def ingest(hub, day_offset, *rows):
    return hub.ingest("d1", parse_csv(stock(*rows), "d1"), observed_on=D0 + timedelta(days=day_offset))


def test_ticker_slug():
    v = Vehicle("d", "R", "Mercedes-Benz", "C 200 AMG", 2020, 1, 1)
    assert ticker_for(v) == "MERCEDES-BENZ-C-200-AMG-2020"


def test_lifecycle_quotes_and_liquidity():
    hub = make_hub()
    ingest(hub, 0, ("A1", 20000, 10000), ("A2", 40000, 9000), ("A3", 60000, 8000))
    s = ingest(hub, 10, ("A1", 20000, 9500), ("A2", 40000, 9000))  # A1 drops, A3 sold
    assert (s.removed, s.price_drops, s.new) == (1, 1, 0)
    ingest(hub, 35, ("A1", 20000, 9500), ("A4", 30000, 9200))      # A2 sold, A4 new

    listings = load_listings(hub.db, "TOYOTA-YARIS-2019")
    q0 = quote(listings, D0)
    assert (q0["active"], q0["median_price"], q0["min_price"], q0["max_price"]) == (3, 9000, 8000, 10000)
    q10 = quote(listings, D0 + timedelta(days=10))
    assert (q10["active"], q10["sold"], q10["median_price"]) == (2, 1, 9250)

    t = hub.get_ticker("toyota-yaris-2019")
    assert t["quote"]["active"] == 2 and t["quote"]["median_price"] == 9350
    assert t["avg_days_to_sell"] == 22.5  # A3: 10 days, A2: 35 days
    assert t["change_30d_pct"] == round((9350 - 9250) / 9250 * 100, 1)
    assert len(t["history"]) == 31
    assert hub.get_ticker("NOPE-1999") is None


def test_relisted_car_starts_new_life():
    hub = make_hub()
    ingest(hub, 0, ("A1", 20000, 10000))
    guarded = ingest(hub, 5)  # empty export: ignored by default
    assert guarded.removed == 0 and guarded.row_errors
    hub.ingest("d1", parse_csv(stock(), "d1"), observed_on=D0 + timedelta(days=5), allow_empty=True)
    row = hub.db.get_vehicle_by_reg("d1", "A1")
    assert row["removed_at"] is not None
    s = ingest(hub, 9, ("A1", 20100, 9900))
    row = hub.db.get_vehicle_by_reg("d1", "A1")
    assert row["removed_at"] is None and row["first_seen"] == (D0 + timedelta(days=9)).isoformat()
    assert s.new == 1


def test_fair_price_regression_and_rating():
    hub = make_hub()
    rows = [("B%d" % i, 10000 + i * 10000, 12000 - i * 1000) for i in range(6)]  # perfect line
    rows.append(("CHEAP", 30000, 7000))  # line says ~10,000 at 30k miles
    ingest(hub, 40, *rows)
    res = hub.search(filters=None, query="toyota", sort="best_deal")
    top = res["results"][0]
    assert top["title"].startswith("2019 Toyota Yaris") and top["deal"]["rating"] == "great"
    detail = hub.get_vehicle(top["vehicle_id"])
    fp = detail["market"]["fair_price"]
    assert fp["method"] == "mileage-adjusted regression" and fp["comparables"] == 6
    assert abs(fp["fair_price_gbp"] - 10000) <= 10


def test_fair_price_needs_comparables():
    hub = make_hub()
    ingest(hub, 40, ("ONLY", 10000, 9000))
    detail = hub.get_vehicle(hub.search(query="toyota")["results"][0]["vehicle_id"])
    assert detail["market"]["fair_price"] is None
    assert detail["market"]["price_history"] == [{"day": "2026-11-10", "price_gbp": 9000}]


def test_market_overview():
    hub = make_hub()
    ingest(hub, 0, *[(f"A{i}", 20000 + i * 1000, 9000 + i * 100) for i in range(5)])
    ingest(hub, 39, *[(f"A{i}", 20000 + i * 1000, 10000 + i * 100) for i in range(5)])
    ov = hub.market_overview()
    assert ov["tickers"] == 1 and ov["active_listings"] == 5
    assert ov["top_gainers"][0]["ticker"] == "TOYOTA-YARIS-2019"
    assert ov["top_gainers"][0]["change_30d_pct"] == round(1000 / 9200 * 100, 1)


def test_thin_tickers_are_not_movers():
    hub = make_hub()
    ingest(hub, 0, ("A1", 20000, 9000))
    ingest(hub, 39, ("A1", 20000, 12000))
    assert hub.market_overview()["top_gainers"] == []


def test_search_sorts():
    hub = make_hub()
    ingest(hub, 40, ("A1", 50000, 9000), ("A2", 10000, 11000))
    asc = [r["price_gbp"] for r in hub.search(query="toyota", sort="price_asc")["results"]]
    low = [r["mileage"] for r in hub.search(query="toyota", sort="lowest_mileage")["results"]]
    assert asc == [9000, 11000] and low == [10000, 50000]
