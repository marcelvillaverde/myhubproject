"""Application service: the single entry point used by the MCP server and the CLI."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone

from . import compliance, leads
from .db import Database, row_to_vehicle
from .ingest import IngestResult
from .models import Dealer, LeadRequest, ListingStatus, RiskReport
from .risk import RiskProvider, risk_flags, risk_summary
from .search import SearchFilters, parse_query

MAX_RESULTS = 20


@dataclass
class IngestSummary:
    dealer_id: str
    upserted: int
    removed: int
    row_errors: list[dict]
    by_status: dict[str, int]


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

    def ingest(self, dealer_id: str, result: IngestResult) -> IngestSummary:
        if self.db.get_dealer(dealer_id) is None:
            raise ValueError(f"Unknown dealer: {dealer_id}")
        by_status: dict[str, int] = {}
        if result.errors and not result.vehicles:
            # Header-level failure: do not wipe the dealer's live stock.
            return IngestSummary(dealer_id, 0, 0, [asdict(e) for e in result.errors], by_status)
        for v in result.vehicles:
            report = self.risk.check(v.reg) if self.risk else None
            issues = compliance.check_listing(v, report, self.today)
            status = compliance.status_for(issues)
            by_status[status] = by_status.get(status, 0) + 1
            self.db.upsert_vehicle(
                v, status, [i.to_dict() for i in issues], report.to_dict() if report else None
            )
        removed = self.db.mark_removed_except(dealer_id, [v.reg for v in result.vehicles])
        self.db.log_event("ingest", {"dealer_id": dealer_id, "rows": len(result.vehicles), "removed": removed})
        return IngestSummary(dealer_id, len(result.vehicles), removed, [asdict(e) for e in result.errors], by_status)

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
               limit: int = 10) -> dict:
        effective = parse_query(query) if query else SearchFilters()
        if filters:
            effective = effective.merged_with(filters)
        limit = max(1, min(limit, MAX_RESULTS))
        area = _postcode_area(near_postcode) if near_postcode else ""

        scored = []
        for row in self.db.live_vehicle_rows(self._visible_statuses()):
            v = row_to_vehicle(row)
            if not _matches(v, effective):
                continue
            report = _report_from_row(row)
            flags = risk_flags(report, self.today)
            verified_clear = report is not None and not flags
            if any(f.severity == "block" for f in flags):
                continue
            rank, why = 0.0, []
            if verified_clear:
                rank += 3
                why.append("history checked, no alerts")
            if area and _postcode_area(row["dealer_postcode"]) == area:
                rank += 2
                why.append(f"dealer in the {area} postcode area")
            if effective.max_price and v.price_gbp:
                rank += 1 - (v.price_gbp / effective.max_price) * 0.5
            rank += max(0, (v.year - 2010)) * 0.05 - v.mileage / 200_000
            scored.append((rank, row, v, report, why, flags))

        scored.sort(key=lambda t: t[0], reverse=True)
        results = [
            {
                "vehicle_id": v.id,
                "title": v.title,
                "price_gbp": v.price_gbp,
                "mileage": v.mileage,
                "fuel": v.fuel,
                "transmission": v.transmission,
                "body": v.body,
                "dealer": row["dealer_name"],
                "dealer_postcode": row["dealer_postcode"],
                "history_check": "checked" if report else "not checked",
                "history_alerts": [f.message for f in flags],
                "why": why,
            }
            for _, row, v, report, why, flags in scored[:limit]
        ]
        self.db.log_event("search", {"query": query, "filters": _filters_dict(effective), "results": len(results), "total": len(scored)})
        return {"applied_filters": _filters_dict(effective), "total_matches": len(scored), "results": results}

    def get_vehicle(self, vehicle_id: int) -> dict | None:
        row = self.db.get_vehicle_row(vehicle_id)
        if row is None or row["removed_at"] is not None or row["status"] not in self._visible_statuses():
            return None
        v = row_to_vehicle(row)
        dealer = self.db.get_dealer(v.dealer_id)
        report = _report_from_row(row)
        self.db.log_event("view", {"vehicle_id": vehicle_id})
        return {
            "vehicle_id": v.id,
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

    def metrics(self) -> dict:
        return self.db.event_counts()


def _report_from_row(row) -> RiskReport | None:
    raw = row["risk_json"]
    return RiskReport(**json.loads(raw)) if raw else None


def _filters_dict(f: SearchFilters) -> dict:
    return {k: v for k, v in asdict(f).items() if v not in (None, ())}


def _matches(v, f: SearchFilters) -> bool:
    if f.make and v.make.lower() != f.make.lower():
        return False
    if f.model and f.model.lower() not in v.model.lower():
        return False
    if f.min_price is not None and (v.price_gbp or 0) < f.min_price:
        return False
    if f.max_price is not None and (v.price_gbp is None or v.price_gbp > f.max_price):
        return False
    if f.max_mileage is not None and v.mileage > f.max_mileage:
        return False
    if f.min_year is not None and v.year < f.min_year:
        return False
    if f.fuel and v.fuel != f.fuel.lower():
        return False
    if f.transmission and v.transmission != f.transmission.lower():
        return False
    if f.body and v.body != f.body.lower():
        return False
    if f.min_seats is not None and (v.seats is None or v.seats < f.min_seats):
        return False
    if f.keywords:
        haystack = " ".join([v.description, " ".join(v.features), v.variant]).lower()
        if not all(k.lower() in haystack for k in f.keywords):
            return False
    return True
