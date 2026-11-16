"""Application service: the single entry point used by the MCP server and the CLI."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime, timedelta, timezone

from . import compliance, leads, market, watch
from .db import Database, row_to_vehicle
from .ingest import IngestResult
from .models import Dealer, LeadRequest, ListingStatus, RiskReport, Vehicle
from .risk import RiskProvider, risk_flags, risk_summary
from .search import SearchFilters, matches, parse_query

SORTS = ("relevance", "best_deal", "price_asc", "price_desc", "newest_listing", "lowest_mileage")

MAX_RESULTS = 20


@dataclass
class IngestSummary:
    dealer_id: str
    upserted: int
    removed: int
    row_errors: list[dict]
    by_status: dict[str, int]
    new: int = 0
    price_drops: int = 0
    alerts_created: int = 0


def _postcode_area(postcode: str) -> str:
    outward = postcode.strip().upper().split(" ")[0]
    letters = ""
    for ch in outward:
        if ch.isalpha():
            letters += ch
        else:
            break
    return letters


class Hub:
    def __init__(self, db: Database, risk_provider: RiskProvider | None = None, today: date | None = None,
                 show_needs_review: bool = True):
        self.db = db
        self.risk = risk_provider
        self._today = today
        self.show_needs_review = show_needs_review

    @property
    def today(self) -> date:
        return self._today or date.today()

    # dealer side ---------------------------------------------------------
    def register_dealer(self, dealer: Dealer) -> None:
        self.db.upsert_dealer(dealer)

    def ingest(self, dealer_id: str, result: IngestResult, observed_on: date | None = None,
               allow_empty: bool = False) -> IngestSummary:
        """Load a full stock snapshot for one dealer. Cars missing from the snapshot are marked sold.

        Runs in one transaction and emits market events (new, price drop, sold) for watchers.
        """
        if self.db.get_dealer(dealer_id) is None:
            raise ValueError(f"Unknown dealer: {dealer_id}")
        day = (observed_on or self.today).isoformat()
        by_status: dict[str, int] = {}
        if result.errors and not result.vehicles:
            # Header-level failure: do not wipe the dealer's live stock.
            return IngestSummary(dealer_id, 0, 0, [asdict(e) for e in result.errors], by_status)
        if not result.vehicles and not allow_empty and self.db.dealer_vehicle_rows(dealer_id):
            # An empty export is far more often a glitch than a dealer selling everything at once.
            return IngestSummary(dealer_id, 0, 0, [{"line": 0, "reason": "Empty stock file ignored; pass allow_empty to confirm the dealer has no stock."}], by_status)
        visible = self._visible_statuses()
        events: list[watch.MarketEvent] = []
        touched: dict[int, Vehicle] = {}
        with self.db.conn:
            for v in result.vehicles:
                prev = self.db.get_vehicle_by_reg(dealer_id, v.reg)
                report = self.risk.check(v.reg) if self.risk else None
                issues = compliance.check_listing(v, report, observed_on or self.today)
                status = compliance.status_for(issues)
                by_status[status] = by_status.get(status, 0) + 1
                ticker = market.ticker_for(v)
                vid = self.db.upsert_vehicle(v, status, [i.to_dict() for i in issues],
                                             report.to_dict() if report else None, ticker, day)
                v.id = vid
                touched[vid] = v
                is_visible = status in visible
                was_visible = prev is not None and prev["removed_at"] is None and prev["status"] in visible
                if is_visible and not was_visible:
                    events.append(watch.MarketEvent("NEW_MATCH", vid, ticker, {"price_gbp": v.price_gbp}))
                elif is_visible and prev["price_gbp"] and v.price_gbp and v.price_gbp < prev["price_gbp"]:
                    drop = prev["price_gbp"] - v.price_gbp
                    events.append(watch.MarketEvent("PRICE_DROP", vid, ticker, {
                        "old_price_gbp": prev["price_gbp"], "price_gbp": v.price_gbp, "drop_gbp": drop,
                        "drop_pct": round(drop / prev["price_gbp"] * 100, 1)}))
            removed_ids = self.db.mark_removed_except(dealer_id, [v.reg for v in result.vehicles], day)
            for vid in removed_ids:
                row = self.db.get_vehicle_row(vid)
                sold = row_to_vehicle(row)
                touched[vid] = sold
                events.append(watch.MarketEvent("SOLD", vid, row["ticker"], {"last_price_gbp": row["price_gbp"]}))
            alerts = watch.dispatch(self.db, events, touched, day)
        self.db.log_event("ingest", {"dealer_id": dealer_id, "rows": len(result.vehicles), "removed": len(removed_ids)})
        return IngestSummary(
            dealer_id, len(result.vehicles), len(removed_ids), [asdict(e) for e in result.errors], by_status,
            new=sum(e.kind == "NEW_MATCH" for e in events),
            price_drops=sum(e.kind == "PRICE_DROP" for e in events),
            alerts_created=alerts,
        )

    def compliance_report(self, dealer_id: str) -> list[dict]:
        out = []
        for row in self.db.dealer_vehicle_rows(dealer_id):
            out.append({
                "vehicle_id": row["id"],
                "reg": row["reg"],
                "title": row_to_vehicle(row).title,
                "status": row["status"],
                "issues": json.loads(row["compliance_json"] or "[]"),
            })
        return out

    def dealer_leads(self, dealer_id: str | None = None) -> list[dict]:
        rows = self.db.lead_rows(dealer_id)
        return [dict(r) | {"intent_reasons": json.loads(r["intent_reasons"] or "[]")} for r in rows]

    # buyer side ----------------------------------------------------------
    def _visible_statuses(self) -> tuple[str, ...]:
        if self.show_needs_review:
            return (ListingStatus.PUBLISHED.value, ListingStatus.NEEDS_REVIEW.value)
        return (ListingStatus.PUBLISHED.value,)

    def search(self, query: str = "", filters: SearchFilters | None = None, near_postcode: str = "",
               limit: int = 10, sort: str = "relevance") -> dict:
        effective = parse_query(query) if query else SearchFilters()
        if query and effective.model is None:
            effective = self._infer_model(query, effective)
        if filters:
            effective = effective.merged_with(filters)
        limit = max(1, min(limit, MAX_RESULTS))
        if sort not in SORTS:
            sort = "relevance"
        area = _postcode_area(near_postcode) if near_postcode else ""
        by_ticker = self._listings_by_ticker()

        scored = []
        for row in self.db.live_vehicle_rows(self._visible_statuses()):
            v = row_to_vehicle(row)
            if not matches(v, effective):
                continue
            report = _report_from_row(row)
            flags = risk_flags(report, self.today)
            if any(f.severity == "block" for f in flags):
                continue
            deal = market.fair_price(by_ticker.get(row["ticker"], []), v.id, v.mileage, v.price_gbp, self.today)
            rank, why = 0.0, []
            if report is not None and not flags:
                rank += 3
                why.append("history checked, no alerts")
            if area and _postcode_area(row["dealer_postcode"]) == area:
                rank += 2
                why.append(f"dealer in the {area} postcode area")
            if deal and deal["rating"] in ("great", "good"):
                rank += 2 if deal["rating"] == "great" else 1
                why.append(f"{deal['rating']} deal: £{-deal['delta_gbp']:,} below fair price")
            if effective.max_price and v.price_gbp:
                rank += 1 - (v.price_gbp / effective.max_price) * 0.5
            rank += max(0, (v.year - 2010)) * 0.05 - v.mileage / 200_000
            scored.append((rank, row, v, report, why, flags, deal))

        keys = {
            "relevance": lambda t: -t[0],
            "best_deal": lambda t: t[6]["delta_pct"] if t[6] else 999,
            "price_asc": lambda t: t[2].price_gbp or 0,
            "price_desc": lambda t: -(t[2].price_gbp or 0),
            "newest_listing": lambda t: t[1]["first_seen"], 
            "lowest_mileage": lambda t: t[2].mileage,
        }
        scored.sort(key=keys[sort], reverse=(sort == "newest_listing"))
        results = [
            {
                "vehicle_id": v.id,
                "ticker": row["ticker"],
                "title": v.title,
                "price_gbp": v.price_gbp,
                "mileage": v.mileage,
                "fuel": v.fuel,
                "transmission": v.transmission,
                "body": v.body,
                "dealer": row["dealer_name"],
                "dealer_postcode": row["dealer_postcode"],
                "listed_since": row["first_seen"],
                "deal": {k: deal[k] for k in ("rating", "fair_price_gbp", "delta_gbp", "delta_pct")} if deal else None,
                "history_check": "checked" if report else "not checked",
                "history_alerts": [f.message for f in flags],
                "why": why,
            }
            for _, row, v, report, why, flags, deal in scored[:limit]
        ]
        self.db.log_event("search", {"query": query, "filters": _filters_dict(effective), "results": len(results), "total": len(scored)})
        return {"applied_filters": _filters_dict(effective), "sort": sort, "total_matches": len(scored), "results": results}

    def _infer_model(self, query: str, f: SearchFilters) -> SearchFilters:
        """Pick up a model name mentioned in free text, using the models actually in stock."""
        text = " " + re.sub(r"[^a-z0-9]+", " ", query.lower()) + " "
        best = None
        for make, model in self.db.conn.execute("SELECT DISTINCT make, model FROM vehicles WHERE removed_at IS NULL"):
            if f.make and make.lower() != f.make.lower():
                continue
            name = re.sub(r"[^a-z0-9]+", " ", model.lower()).strip()
            if name and f" {name} " in text and (best is None or len(name) > len(best[1])):
                best = (make, model)
        if best is None:
            return f
        return replace(f, make=f.make or best[0], model=best[1])

    def _listings_by_ticker(self) -> dict[str, list[market.Listing]]:
        out: dict[str, list[market.Listing]] = {}
        for l in market.load_listings(self.db):
            out.setdefault(l.ticker, []).append(l)
        return out

    def get_vehicle(self, vehicle_id: int) -> dict | None:
        row = self.db.get_vehicle_row(vehicle_id)
        if row is None or row["removed_at"] is not None or row["status"] not in self._visible_statuses():
            return None
        v = row_to_vehicle(row)
        dealer = self.db.get_dealer(v.dealer_id)
        report = _report_from_row(row)
        listings = market.load_listings(self.db, row["ticker"])
        own = next((l for l in listings if l.id == v.id), None)
        self.db.log_event("view", {"vehicle_id": vehicle_id})
        return {
            "vehicle_id": v.id,
            "ticker": row["ticker"],
            "title": v.title,
            "reg_area_hint": v.reg[:2],  # full plate withheld until contact
            "price_gbp": v.price_gbp,
            "mileage": v.mileage,
            "year": v.year,
            "fuel": v.fuel,
            "transmission": v.transmission,
            "body": v.body,
            "colour": v.colour,
            "doors": v.doors,
            "seats": v.seats,
            "features": v.features,
            "description": v.description,
            "history": risk_summary(report, self.today),
            "market": {
                "listed_since": row["first_seen"],
                "days_listed": (self.today - date.fromisoformat(row["first_seen"][:10])).days,
                "price_history": market.price_history_of(own) if own else [],
                "fair_price": market.fair_price(listings, v.id, v.mileage, v.price_gbp, self.today),
                "note": "Fair price is an estimate from comparable listings on this platform, not a valuation.",
            },
            "dealer": {"name": dealer.name, "postcode": dealer.postcode} if dealer else None,
            "next_step": "To contact the dealer, use request_contact with the buyer's explicit consent.",
        }

    def request_contact(self, req: LeadRequest, channel: str = "mcp") -> dict:
        leads.validate(req)
        row = self.db.get_vehicle_row(req.vehicle_id)
        if row is None or row["removed_at"] is not None or row["status"] not in self._visible_statuses():
            raise leads.LeadValidationError("This vehicle is no longer available.")
        since = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat(timespec="seconds")
        if self.db.recent_duplicate_lead(req.vehicle_id, req.email.strip(), req.phone.strip(), since):
            return {"status": "duplicate", "message": "We already received your request for this car in the last 7 days; the dealer will be in touch."}
        intent = leads.score(req, row["price_gbp"])
        created = datetime.now(timezone.utc)
        lead_id = self.db.insert_lead(
            vehicle_id=req.vehicle_id,
            dealer_id=row["dealer_id"],
            name=req.name.strip(),
            email=req.email.strip(),
            phone=req.phone.strip(),
            message=req.message.strip(),
            budget_gbp=req.budget_gbp,
            timeframe_days=req.timeframe_days,
            wants_test_drive=int(req.wants_test_drive),
            has_part_exchange=int(req.has_part_exchange),
            consent_contact=1,
            consent_marketing=int(req.consent_marketing),
            intent_score=intent.score,
            intent_tier=intent.tier.value,
            intent_reasons=json.dumps(list(intent.reasons)),
            channel=channel,
            created_at=created.isoformat(timespec="seconds"),
            retain_until=(created + timedelta(days=leads.RETENTION_DAYS)).date().isoformat(),
        )
        dealer = self.db.get_dealer(row["dealer_id"])
        self.db.log_event("lead", {"lead_id": lead_id, "tier": intent.tier.value})
        return {
            "status": "sent",
            "lead_id": lead_id,
            "message": f"Request sent to {dealer.name if dealer else 'the dealer'}. "
                       "They will contact you using the details you provided. "
                       f"Your details are kept for up to {leads.RETENTION_DAYS} days.",
        }

    # terminal ------------------------------------------------------------
    def market_overview(self, limit: int = 10) -> dict:
        self.db.log_event("market_overview", {})
        return market.market_overview(self.db, self.today, limit)

    def get_ticker(self, ticker: str, history_days: int = 30) -> dict | None:
        t = ticker.strip().upper()
        listings = market.load_listings(self.db, t)
        if not listings:
            return None
        self.db.log_event("ticker", {"ticker": t})
        return {"ticker": t, **market.ticker_stats(listings, self.today, max(1, min(history_days, 180)))}

    def create_watcher(self) -> dict:
        token = watch.create_watcher(self.db)
        return {"watcher_token": token,
                "note": "Keep this token private. Anyone with it can read these alerts. It cannot be recovered."}

    def add_watch(self, token: str, kind: str, **kwargs) -> dict:
        wid = watch.add_watch(self.db, token, kind, **kwargs)
        return {"watch_id": wid, "watches": watch.list_watches(self.db, token)}

    def list_watches(self, token: str) -> list[dict]:
        return watch.list_watches(self.db, token)

    def remove_watch(self, token: str, watch_id: int) -> dict:
        return {"removed": watch.remove_watch(self.db, token, watch_id)}

    def get_alerts(self, token: str, mark_read: bool = True, limit: int = 50) -> dict:
        alerts = watch.get_alerts(self.db, token, mark_read, max(1, min(limit, 200)))
        return {"count": len(alerts), "alerts": alerts}

    def metrics(self) -> dict:
        return self.db.event_counts()


def _report_from_row(row) -> RiskReport | None:
    raw = row["risk_json"]
    return RiskReport(**json.loads(raw)) if raw else None


def _filters_dict(f: SearchFilters) -> dict:
    return {k: v for k, v in asdict(f).items() if v not in (None, ())}
