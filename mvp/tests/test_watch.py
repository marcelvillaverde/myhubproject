from datetime import date, timedelta

import pytest

from hubcarros.db import Database
from hubcarros.ingest import parse_csv
from hubcarros.models import Dealer
from hubcarros.search import SearchFilters
from hubcarros.service import Hub
from hubcarros.watch import WatchError

D0 = date(2026, 11, 1)
HEADER = "reg,make,model,year,mileage,price,fuel,description\n"


def csv(*rows):
    return HEADER + "".join(f"{r},{mk},{md},{y},{mi},{p},{f},Clean car\n" for r, mk, md, y, mi, p, f in rows)


YARIS = ("Y1", "Toyota", "Yaris", 2019, 30000, 9000, "hybrid")
GOLF = ("G1", "Volkswagen", "Golf", 2018, 50000, 8000, "diesel")


@pytest.fixture
def hub():
    h = Hub(Database(":memory:"), None, today=D0 + timedelta(days=10))
    h.register_dealer(Dealer("d1", "Dealer One", "LS1 1AA"))
    return h


def ingest(hub, day, *rows, allow_empty=False):
    return hub.ingest("d1", parse_csv(csv(*rows), "d1"), observed_on=D0 + timedelta(days=day), allow_empty=allow_empty)


def test_token_is_secret_and_required(hub):
    token = hub.create_watcher()["watcher_token"]
    assert token.startswith("wt_") and len(token) > 20
    row = hub.db.conn.execute("SELECT token_hash FROM watchers").fetchone()
    assert token not in row["token_hash"]
    with pytest.raises(WatchError):
        hub.list_watches("wt_wrong")


def test_search_watch_gets_new_match_and_price_drop_only_when_matching(hub):
    token = hub.create_watcher()["watcher_token"]
    hub.add_watch(token, "search", query="hybrid under £10k", label="cheap hybrid")
    s = ingest(hub, 0, YARIS, GOLF)
    assert s.alerts_created == 1
    alerts = hub.get_alerts(token)["alerts"]
    assert [(a["kind"], a["title"]) for a in alerts] == [("NEW_MATCH", "2019 Toyota Yaris")]
    assert hub.get_alerts(token)["count"] == 0  # marked read

    ingest(hub, 1, ("Y1", "Toyota", "Yaris", 2019, 30000, 8500, "hybrid"), ("G1", "Volkswagen", "Golf", 2018, 50000, 7000, "diesel"))
    alerts = hub.get_alerts(token)["alerts"]
    assert len(alerts) == 1 and alerts[0]["kind"] == "PRICE_DROP"
    assert (alerts[0]["drop_gbp"], alerts[0]["drop_pct"], alerts[0]["old_price_gbp"]) == (500, 5.6, 9000)


def test_price_increase_does_not_alert(hub):
    token = hub.create_watcher()["watcher_token"]
    hub.add_watch(token, "search", filters=SearchFilters(make="Toyota"))
    ingest(hub, 0, YARIS)
    hub.get_alerts(token)
    ingest(hub, 1, ("Y1", "Toyota", "Yaris", 2019, 30000, 9900, "hybrid"))
    assert hub.get_alerts(token)["count"] == 0


def test_vehicle_watch_gets_drop_and_sold(hub):
    ingest(hub, 0, YARIS, GOLF)
    vid = hub.search(query="golf")["results"][0]["vehicle_id"]
    token = hub.create_watcher()["watcher_token"]
    hub.add_watch(token, "vehicle", vehicle_id=vid)
    ingest(hub, 1, YARIS, ("G1", "Volkswagen", "Golf", 2018, 50000, 7500, "diesel"))
    ingest(hub, 2, YARIS)
    kinds = sorted(a["kind"] for a in hub.get_alerts(token)["alerts"])
    assert kinds == ["PRICE_DROP", "SOLD"]


def test_ticker_watch_sees_everything_in_ticker(hub):
    token = hub.create_watcher()["watcher_token"]
    hub.add_watch(token, "ticker", ticker="toyota-yaris-2019")
    ingest(hub, 0, YARIS, GOLF)
    ingest(hub, 1, GOLF)
    kinds = [a["kind"] for a in hub.get_alerts(token)["alerts"]]
    assert sorted(kinds) == ["NEW_MATCH", "SOLD"]


def test_watchers_are_isolated_and_remove_works(hub):
    a = hub.create_watcher()["watcher_token"]
    b = hub.create_watcher()["watcher_token"]
    wid = hub.add_watch(a, "search", filters=SearchFilters(make="Toyota"))["watch_id"]
    assert hub.list_watches(b) == []
    assert hub.remove_watch(b, wid)["removed"] is False
    ingest(hub, 0, YARIS)
    assert hub.get_alerts(b)["count"] == 0
    assert hub.remove_watch(a, wid)["removed"] is True
    assert hub.list_watches(a) == []


def test_invalid_watches(hub):
    token = hub.create_watcher()["watcher_token"]
    with pytest.raises(WatchError):
        hub.add_watch(token, "search")
    with pytest.raises(WatchError):
        hub.add_watch(token, "vehicle", vehicle_id=999)
    with pytest.raises(WatchError):
        hub.add_watch(token, "stocks")


def test_blocked_listing_never_alerts(hub):
    token = hub.create_watcher()["watcher_token"]
    hub.add_watch(token, "search", filters=SearchFilters(make="Toyota"))
    hub.ingest("d1", parse_csv(HEADER + "Y9,Toyota,Yaris,2019,30000,9000,hybrid,Sold as seen\n", "d1"), observed_on=D0)
    assert hub.get_alerts(token)["count"] == 0
