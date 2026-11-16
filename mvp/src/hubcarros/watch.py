"""Watchlists and alerts.

A watcher is identified by a random secret token (there is no user login yet).
Only a SHA-256 hash of the token is stored. Alerts are generated from market
events produced during ingestion and read by polling ``get_alerts``.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import asdict, dataclass

from .db import Database
from .models import Vehicle
from .search import SearchFilters, matches, parse_query

WATCH_KINDS = ("search", "ticker", "vehicle")
MAX_WATCHES_PER_WATCHER = 50


class WatchError(ValueError):
    pass


@dataclass(frozen=True)
class MarketEvent:
    kind: str  # NEW_MATCH | PRICE_DROP | SOLD
    vehicle_id: int
    ticker: str
    payload: dict


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_watcher(db: Database) -> str:
    token = "wt_" + secrets.token_urlsafe(24)
    db.insert_watcher(_hash(token))
    return token


def resolve(db: Database, token: str) -> int:
    wid = db.watcher_id_for(_hash(token.strip())) if token else None
    if wid is None:
        raise WatchError("Unknown watcher token. Create one with create_watcher.")
    return wid


def add_watch(db: Database, token: str, kind: str, *, query: str = "", filters: SearchFilters | None = None,
              ticker: str = "", vehicle_id: int | None = None, label: str = "") -> int:
    wid = resolve(db, token)
    if kind not in WATCH_KINDS:
        raise WatchError(f"kind must be one of {', '.join(WATCH_KINDS)}.")
    if len(db.watch_rows(wid)) >= MAX_WATCHES_PER_WATCHER:
        raise WatchError(f"Limit of {MAX_WATCHES_PER_WATCHER} watches reached.")
    if kind == "search":
        effective = (parse_query(query) if query else SearchFilters()).merged_with(filters or SearchFilters())
        params = {k: v for k, v in asdict(effective).items() if v not in (None, ())}
        if not params:
            raise WatchError("A search watch needs a query or at least one filter.")
        params["keywords"] = list(params.get("keywords", []))
    elif kind == "ticker":
        if not ticker.strip():
            raise WatchError("A ticker watch needs a ticker, e.g. TOYOTA-RAV4-2020.")
        params = {"ticker": ticker.strip().upper()}
    else:
        if vehicle_id is None or db.get_vehicle_row(vehicle_id) is None:
            raise WatchError("A vehicle watch needs a valid vehicle_id.")
        params = {"vehicle_id": vehicle_id}
    return db.insert_watch(wid, kind, label.strip(), params)


def list_watches(db: Database, token: str) -> list[dict]:
    wid = resolve(db, token)
    return [{"watch_id": r["id"], "kind": r["kind"], "label": r["label"], "params": json.loads(r["params"])}
            for r in db.watch_rows(wid)]


def remove_watch(db: Database, token: str, watch_id: int) -> bool:
    return db.delete_watch(resolve(db, token), watch_id)


def _watch_wants(watch_kind: str, params: dict, event: MarketEvent, vehicle: Vehicle) -> bool:
    if watch_kind == "vehicle":
        return params["vehicle_id"] == event.vehicle_id and event.kind in ("PRICE_DROP", "SOLD")
    if watch_kind == "ticker":
        return params["ticker"] == event.ticker
    p = dict(params)
    p["keywords"] = tuple(p.get("keywords", ()))
    return event.kind in ("NEW_MATCH", "PRICE_DROP") and matches(vehicle, SearchFilters(**p))


def dispatch(db: Database, events: list[MarketEvent], vehicles: dict[int, Vehicle], day: str) -> int:
    """Create alerts for every watch interested in the events. Caller commits."""
    if not events:
        return 0
    watches = db.watch_rows()
    created = 0
    for w in watches:
        params = json.loads(w["params"])
        for e in events:
            v = vehicles.get(e.vehicle_id)
            if v is None:
                continue
            if _watch_wants(w["kind"], params, e, v):
                db.insert_alert(w["watcher_id"], w["id"], e.kind, e.vehicle_id,
                                e.payload | {"title": v.title, "ticker": e.ticker}, day)
                created += 1
    return created


def get_alerts(db: Database, token: str, mark_read: bool = True, limit: int = 50) -> list[dict]:
    wid = resolve(db, token)
    rows = db.alert_rows(wid, unread_only=True, limit=limit)
    out = [{"alert_id": r["id"], "watch_id": r["watch_id"], "kind": r["kind"], "vehicle_id": r["vehicle_id"],
            "day": r["created_on"], **json.loads(r["payload"])} for r in rows]
    if mark_read:
        db.mark_alerts_read([r["id"] for r in rows])
    return out
