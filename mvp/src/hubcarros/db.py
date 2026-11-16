"""SQLite persistence. Standard library only."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path

from .models import Dealer, Vehicle

SCHEMA = """
CREATE TABLE IF NOT EXISTS dealers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    postcode TEXT NOT NULL,
    phone TEXT DEFAULT '',
    email TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS vehicles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dealer_id TEXT NOT NULL REFERENCES dealers(id),
    reg TEXT NOT NULL,
    make TEXT NOT NULL,
    model TEXT NOT NULL,
    variant TEXT DEFAULT '',
    year INTEGER NOT NULL,
    price_gbp INTEGER,
    mileage INTEGER NOT NULL,
    fuel TEXT DEFAULT '',
    transmission TEXT DEFAULT '',
    body TEXT DEFAULT '',
    colour TEXT DEFAULT '',
    doors INTEGER,
    seats INTEGER,
    description TEXT DEFAULT '',
    features TEXT DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'needs_review',
    compliance_json TEXT DEFAULT '[]',
    risk_json TEXT,
    ticker TEXT NOT NULL DEFAULT '',
    first_seen TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    removed_at TEXT,
    UNIQUE (dealer_id, reg)
);
CREATE INDEX IF NOT EXISTS idx_vehicles_ticker ON vehicles(ticker);
CREATE TABLE IF NOT EXISTS price_history (
    vehicle_id INTEGER NOT NULL REFERENCES vehicles(id),
    observed_on TEXT NOT NULL,
    price_gbp INTEGER,
    PRIMARY KEY (vehicle_id, observed_on)
);
CREATE TABLE IF NOT EXISTS watchers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS watches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    watcher_id INTEGER NOT NULL REFERENCES watchers(id),
    kind TEXT NOT NULL,
    label TEXT DEFAULT '',
    params TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    watcher_id INTEGER NOT NULL REFERENCES watchers(id),
    watch_id INTEGER NOT NULL REFERENCES watches(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    vehicle_id INTEGER NOT NULL REFERENCES vehicles(id),
    payload TEXT DEFAULT '{}',
    created_on TEXT NOT NULL,
    read_at TEXT,
    UNIQUE (watch_id, vehicle_id, kind, created_on)
);
CREATE INDEX IF NOT EXISTS idx_vehicles_live ON vehicles(status, removed_at);
CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vehicle_id INTEGER NOT NULL REFERENCES vehicles(id),
    dealer_id TEXT NOT NULL REFERENCES dealers(id),
    name TEXT NOT NULL,
    email TEXT DEFAULT '',
    phone TEXT DEFAULT '',
    message TEXT DEFAULT '',
    budget_gbp INTEGER,
    timeframe_days INTEGER,
    wants_test_drive INTEGER NOT NULL DEFAULT 0,
    has_part_exchange INTEGER NOT NULL DEFAULT 0,
    consent_contact INTEGER NOT NULL,
    consent_marketing INTEGER NOT NULL DEFAULT 0,
    intent_score INTEGER NOT NULL,
    intent_tier TEXT NOT NULL,
    intent_reasons TEXT DEFAULT '[]',
    channel TEXT DEFAULT 'mcp',
    created_at TEXT NOT NULL,
    retain_until TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    payload TEXT DEFAULT '{}',
    created_at TEXT NOT NULL
);
"""

VEHICLE_COLUMNS = (
    "dealer_id", "reg", "make", "model", "variant", "year", "price_gbp", "mileage", "fuel",
    "transmission", "body", "colour", "doors", "seats", "description",
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: Path | str = ":memory:"):
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    # dealers -------------------------------------------------------------
    def upsert_dealer(self, d: Dealer) -> None:
        self.conn.execute(
            "INSERT INTO dealers (id, name, postcode, phone, email) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET name=excluded.name, postcode=excluded.postcode, "
            "phone=excluded.phone, email=excluded.email",
            (d.id, d.name, d.postcode.upper(), d.phone, d.email),
        )
        self.conn.commit()

    def get_dealer(self, dealer_id: str) -> Dealer | None:
        row = self.conn.execute("SELECT * FROM dealers WHERE id = ?", (dealer_id,)).fetchone()
        return Dealer(**dict(row)) if row else None

    # vehicles ------------------------------------------------------------
    def get_vehicle_by_reg(self, dealer_id: str, reg: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM vehicles WHERE dealer_id = ? AND reg = ?", (dealer_id, reg)
        ).fetchone()

    def upsert_vehicle(self, v: Vehicle, status: str, compliance: list[dict], risk: dict | None,
                       ticker: str, observed_on: str) -> int:
        """Insert or update a listing. Caller commits (ingest runs in one transaction)."""
        values = [getattr(v, c) for c in VEHICLE_COLUMNS]
        cur = self.conn.execute(
            f"INSERT INTO vehicles ({', '.join(VEHICLE_COLUMNS)}, features, status, compliance_json, risk_json, "
            "ticker, first_seen, updated_at, removed_at) "
            f"VALUES ({', '.join('?' * len(VEHICLE_COLUMNS))}, ?, ?, ?, ?, ?, ?, ?, NULL) "
            "ON CONFLICT(dealer_id, reg) DO UPDATE SET "
            + ", ".join(f"{c}=excluded.{c}" for c in VEHICLE_COLUMNS[2:])
            + ", features=excluded.features, status=excluded.status, compliance_json=excluded.compliance_json, "
            "risk_json=excluded.risk_json, ticker=excluded.ticker, updated_at=excluded.updated_at, "
            # a relisted car starts a new market life
            "first_seen=CASE WHEN vehicles.removed_at IS NOT NULL THEN excluded.first_seen ELSE vehicles.first_seen END, "
            "removed_at=NULL "
            "RETURNING id",
            (*values, json.dumps(v.features), status, json.dumps(compliance),
             json.dumps(risk) if risk is not None else None, ticker, observed_on, observed_on),
        )
        vid = cur.fetchone()[0]
        self.conn.execute(
            "INSERT INTO price_history (vehicle_id, observed_on, price_gbp) VALUES (?, ?, ?) "
            "ON CONFLICT(vehicle_id, observed_on) DO UPDATE SET price_gbp = excluded.price_gbp",
            (vid, observed_on, v.price_gbp),
        )
        return vid

    def mark_removed_except(self, dealer_id: str, keep_regs: Iterable[str], observed_on: str) -> list[int]:
        keep = list(keep_regs)
        placeholders = ", ".join("?" * len(keep)) or "''"
        rows = self.conn.execute(
            f"UPDATE vehicles SET removed_at = ? WHERE dealer_id = ? AND removed_at IS NULL "
            f"AND reg NOT IN ({placeholders}) RETURNING id",
            (observed_on, dealer_id, *keep),
        ).fetchall()
        return [r[0] for r in rows]

    def commit(self) -> None:
        self.conn.commit()

    def get_vehicle_row(self, vehicle_id: int) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM vehicles WHERE id = ?", (vehicle_id,)).fetchone()

    def live_vehicle_rows(self, statuses: tuple[str, ...]) -> list[sqlite3.Row]:
        q = (
            "SELECT v.*, d.name AS dealer_name, d.postcode AS dealer_postcode FROM vehicles v "
            "JOIN dealers d ON d.id = v.dealer_id "
            f"WHERE v.removed_at IS NULL AND v.status IN ({', '.join('?' * len(statuses))})"
        )
        return self.conn.execute(q, statuses).fetchall()

    def dealer_vehicle_rows(self, dealer_id: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM vehicles WHERE dealer_id = ? AND removed_at IS NULL ORDER BY status, make, model",
            (dealer_id,),
        ).fetchall()

    # leads ---------------------------------------------------------------
    def recent_duplicate_lead(self, vehicle_id: int, email: str, phone: str, since_iso: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM leads WHERE vehicle_id = ? AND created_at >= ? AND "
            "((? <> '' AND lower(email) = lower(?)) OR (? <> '' AND replace(phone, ' ', '') = replace(?, ' ', ''))) LIMIT 1",
            (vehicle_id, since_iso, email, email, phone, phone),
        ).fetchone()
        return row is not None

    def insert_lead(self, **cols) -> int:
        keys = list(cols)
        cur = self.conn.execute(
            f"INSERT INTO leads ({', '.join(keys)}) VALUES ({', '.join('?' * len(keys))})",
            [cols[k] for k in keys],
        )
        self.conn.commit()
        return cur.lastrowid

    def lead_rows(self, dealer_id: str | None = None) -> list[sqlite3.Row]:
        if dealer_id:
            return self.conn.execute(
                "SELECT * FROM leads WHERE dealer_id = ? ORDER BY created_at DESC", (dealer_id,)
            ).fetchall()
        return self.conn.execute("SELECT * FROM leads ORDER BY created_at DESC").fetchall()

    def purge_expired_leads(self, today_iso: str) -> int:
        cur = self.conn.execute("DELETE FROM leads WHERE retain_until < ?", (today_iso,))
        self.conn.commit()
        return cur.rowcount

    # metrics -------------------------------------------------------------
    def log_event(self, kind: str, payload: dict) -> None:
        self.conn.execute(
            "INSERT INTO events (kind, payload, created_at) VALUES (?, ?, ?)",
            (kind, json.dumps(payload), now_iso()),
        )
        self.conn.commit()

    def event_counts(self) -> dict[str, int]:
        rows = self.conn.execute("SELECT kind, COUNT(*) AS n FROM events GROUP BY kind").fetchall()
        return {r["kind"]: r["n"] for r in rows}

    # market --------------------------------------------------------------
    def ticker_vehicle_rows(self, ticker: str | None = None) -> list[sqlite3.Row]:
        q = "SELECT id, ticker, mileage, year, first_seen, removed_at, status FROM vehicles"
        return self.conn.execute(q + (" WHERE ticker = ?" if ticker else ""), (ticker,) if ticker else ()).fetchall()

    def price_history_rows(self, vehicle_ids: list[int] | None = None) -> list[sqlite3.Row]:
        if vehicle_ids is None:
            return self.conn.execute("SELECT * FROM price_history ORDER BY vehicle_id, observed_on").fetchall()
        out: list[sqlite3.Row] = []
        for i in range(0, len(vehicle_ids), 500):
            chunk = vehicle_ids[i:i + 500]
            out += self.conn.execute(
                f"SELECT * FROM price_history WHERE vehicle_id IN ({', '.join('?' * len(chunk))}) "
                "ORDER BY vehicle_id, observed_on", chunk).fetchall()
        return out

    # watchers ------------------------------------------------------------
    def insert_watcher(self, token_hash: str) -> int:
        cur = self.conn.execute("INSERT INTO watchers (token_hash, created_at) VALUES (?, ?)", (token_hash, now_iso()))
        self.conn.commit()
        return cur.lastrowid

    def watcher_id_for(self, token_hash: str) -> int | None:
        row = self.conn.execute("SELECT id FROM watchers WHERE token_hash = ?", (token_hash,)).fetchone()
        return row[0] if row else None

    def insert_watch(self, watcher_id: int, kind: str, label: str, params: dict) -> int:
        cur = self.conn.execute(
            "INSERT INTO watches (watcher_id, kind, label, params, created_at) VALUES (?, ?, ?, ?, ?)",
            (watcher_id, kind, label, json.dumps(params), now_iso()),
        )
        self.conn.commit()
        return cur.lastrowid

    def watch_rows(self, watcher_id: int | None = None) -> list[sqlite3.Row]:
        if watcher_id is None:
            return self.conn.execute("SELECT * FROM watches").fetchall()
        return self.conn.execute("SELECT * FROM watches WHERE watcher_id = ? ORDER BY id", (watcher_id,)).fetchall()

    def delete_watch(self, watcher_id: int, watch_id: int) -> bool:
        self.conn.execute("DELETE FROM alerts WHERE watch_id = ? AND watcher_id = ?", (watch_id, watcher_id))
        cur = self.conn.execute("DELETE FROM watches WHERE id = ? AND watcher_id = ?", (watch_id, watcher_id))
        self.conn.commit()
        return cur.rowcount > 0

    def insert_alert(self, watcher_id: int, watch_id: int, kind: str, vehicle_id: int, payload: dict,
                     created_on: str) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO alerts (watcher_id, watch_id, kind, vehicle_id, payload, created_on) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (watcher_id, watch_id, kind, vehicle_id, json.dumps(payload), created_on),
        )

    def alert_rows(self, watcher_id: int, unread_only: bool = True, limit: int = 50) -> list[sqlite3.Row]:
        q = "SELECT * FROM alerts WHERE watcher_id = ?" + (" AND read_at IS NULL" if unread_only else "")
        return self.conn.execute(q + " ORDER BY id DESC LIMIT ?", (watcher_id, limit)).fetchall()

    def mark_alerts_read(self, ids: list[int]) -> None:
        if ids:
            self.conn.execute(
                f"UPDATE alerts SET read_at = ? WHERE id IN ({', '.join('?' * len(ids))})", (now_iso(), *ids)
            )
            self.conn.commit()


def row_to_vehicle(row: sqlite3.Row) -> Vehicle:
    data = {c: row[c] for c in VEHICLE_COLUMNS}
    return Vehicle(**data, features=json.loads(row["features"] or "[]"), id=row["id"])
