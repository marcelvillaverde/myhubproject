"""Market data: tickers, daily quotes, liquidity and fair price.

A *ticker* groups comparable listings (make + model + year). Every quote is
computed from listing life-cycles (first_seen / removed_at) and the price
history, so any past day can be reconstructed exactly.
"""

from __future__ import annotations

import re
import statistics
from bisect import bisect_right
from dataclasses import dataclass
from datetime import date, timedelta

from .db import Database
from .models import Vehicle

MIN_COMPARABLES_REGRESSION = 5
MIN_COMPARABLES_MEDIAN = 2
MIN_ACTIVE_FOR_MOVERS = 5


def _slug(text: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "-", text.upper()).strip("-")


def ticker_for(v: Vehicle) -> str:
    return f"{_slug(v.make)}-{_slug(v.model)}-{v.year}"


@dataclass(frozen=True)
class Listing:
    id: int
    ticker: str
    mileage: int
    first_seen: date
    removed_at: date | None
    days: tuple[date, ...]
    prices: tuple[int | None, ...]

    def active_on(self, day: date) -> bool:
        return self.first_seen <= day and (self.removed_at is None or self.removed_at > day)

    def price_on(self, day: date) -> int | None:
        i = bisect_right(self.days, day)
        return self.prices[i - 1] if i else None


def load_listings(db: Database, ticker: str | None = None) -> list[Listing]:
    rows = db.ticker_vehicle_rows(ticker)
    history: dict[int, list] = {}
    for h in db.price_history_rows([r["id"] for r in rows] if ticker else None):
        history.setdefault(h["vehicle_id"], []).append(h)
    out = []
    for r in rows:
        hist = history.get(r["id"], [])
        out.append(Listing(
            id=r["id"], ticker=r["ticker"], mileage=r["mileage"],
            first_seen=date.fromisoformat(r["first_seen"][:10]),
            removed_at=date.fromisoformat(r["removed_at"][:10]) if r["removed_at"] else None,
            days=tuple(date.fromisoformat(h["observed_on"][:10]) for h in hist),
            prices=tuple(h["price_gbp"] for h in hist),
        ))
    return out


def quote(listings: list[Listing], day: date) -> dict:
    active = [l for l in listings if l.active_on(day)]
    prices = [p for p in (l.price_on(day) for l in active) if p]
    return {
        "day": day.isoformat(),
        "active": len(active),
        "new": sum(1 for l in listings if l.first_seen == day),
        "sold": sum(1 for l in listings if l.removed_at == day),
        "median_price": int(statistics.median(prices)) if prices else None,
        "min_price": min(prices) if prices else None,
        "max_price": max(prices) if prices else None,
        "median_mileage": int(statistics.median([l.mileage for l in active])) if active else None,
    }


def _pct(now: int | None, before: int | None) -> float | None:
    if not now or not before:
        return None
    return round((now - before) / before * 100, 1)


def ticker_stats(listings: list[Listing], today: date, history_days: int = 30) -> dict:
    current = quote(listings, today)
    q7 = quote(listings, today - timedelta(days=7))
    q30 = quote(listings, today - timedelta(days=30))
    sold = [l for l in listings if l.removed_at and l.removed_at <= today]
    window = [l for l in sold if l.removed_at > today - timedelta(days=30)]
    dom = [(l.removed_at - l.first_seen).days for l in sold]
    active = [l for l in listings if l.active_on(today)]
    drops = 0
    for l in active:
        p_now, p_week = l.price_on(today), l.price_on(today - timedelta(days=7))
        if p_now and p_week and p_now < p_week:
            drops += 1
    return {
        "quote": current,
        "change_7d_pct": _pct(current["median_price"], q7["median_price"]),
        "change_30d_pct": _pct(current["median_price"], q30["median_price"]),
        "sold_last_30d": len(window),
        "avg_days_to_sell": round(statistics.mean(dom), 1) if dom else None,
        "median_age_active_days": int(statistics.median([(today - l.first_seen).days for l in active])) if active else None,
        "price_drops_last_7d": drops,
        "history": [quote(listings, today - timedelta(days=d)) for d in range(history_days, -1, -1)],
    }


def market_overview(db: Database, today: date, limit: int = 10) -> dict:
    by_ticker: dict[str, list[Listing]] = {}
    for l in load_listings(db):
        by_ticker.setdefault(l.ticker, []).append(l)
    rows = []
    for t, ls in by_ticker.items():
        q = quote(ls, today)
        if not q["active"]:
            continue
        q30 = quote(ls, today - timedelta(days=30))
        sold30 = sum(1 for l in ls if l.removed_at and today - timedelta(days=30) < l.removed_at <= today)
        rows.append({
            "ticker": t, "active": q["active"], "median_price": q["median_price"],
            "change_30d_pct": _pct(q["median_price"], q30["median_price"]) if min(q30["active"], q["active"]) >= MIN_ACTIVE_FOR_MOVERS else None,
            "sold_last_30d": sold30,
        })
    movers = [r for r in rows if r["change_30d_pct"] is not None]
    return {
        "day": today.isoformat(),
        "tickers": len(rows),
        "active_listings": sum(r["active"] for r in rows),
        "sold_last_30d": sum(r["sold_last_30d"] for r in rows),
        "most_listed": sorted(rows, key=lambda r: r["active"], reverse=True)[:limit],
        "most_sold": sorted(rows, key=lambda r: r["sold_last_30d"], reverse=True)[:limit],
        "top_gainers": sorted(movers, key=lambda r: r["change_30d_pct"], reverse=True)[:limit],
        "top_losers": sorted(movers, key=lambda r: r["change_30d_pct"])[:limit],
    }


def _linear_fit(xs: list[float], ys: list[float]) -> tuple[float, float] | None:
    mx, my = statistics.mean(xs), statistics.mean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return None
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    return slope, my - slope * mx


def rating_for(delta_pct: float) -> str:
    if delta_pct <= -10:
        return "great"
    if delta_pct <= -3:
        return "good"
    if delta_pct <= 3:
        return "fair"
    return "high"


def fair_price(listings: list[Listing], target_id: int, mileage: int, price: int | None, today: date) -> dict | None:
    comps = [(l.mileage, l.price_on(today)) for l in listings if l.id != target_id and l.active_on(today)]
    comps = [(m, p) for m, p in comps if p]
    if len(comps) < MIN_COMPARABLES_MEDIAN or not price:
        return None
    method = "median"
    estimate = statistics.median(p for _, p in comps)
    if len(comps) >= MIN_COMPARABLES_REGRESSION:
        fit = _linear_fit([m for m, _ in comps], [p for _, p in comps])
        # Only trust the fit when more miles means a lower price.
        if fit and fit[0] < 0:
            estimate = fit[0] * mileage + fit[1]
            method = "mileage-adjusted regression"
    estimate = int(round(estimate, -1))
    if estimate <= 0:
        return None
    delta = price - estimate
    delta_pct = round(delta / estimate * 100, 1)
    return {
        "fair_price_gbp": estimate,
        "delta_gbp": delta,
        "delta_pct": delta_pct,
        "rating": rating_for(delta_pct),
        "comparables": len(comps),
        "method": method,
    }


def price_history_of(listing: Listing) -> list[dict]:
    out, last = [], object()
    for d, p in zip(listing.days, listing.prices):
        if p != last:
            out.append({"day": d.isoformat(), "price_gbp": p})
            last = p
    return out
