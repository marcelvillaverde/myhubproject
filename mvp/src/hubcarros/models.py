"""Domain models shared by every module. Pure data, no I/O."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum


class Severity(StrEnum):
    BLOCK = "block"
    WARN = "warn"


class ListingStatus(StrEnum):
    PUBLISHED = "published"
    NEEDS_REVIEW = "needs_review"
    BLOCKED = "blocked"


class IntentTier(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass(frozen=True)
class Dealer:
    id: str
    name: str
    postcode: str
    phone: str = ""
    email: str = ""


@dataclass
class Vehicle:
    dealer_id: str
    reg: str
    make: str
    model: str
    year: int
    price_gbp: int | None
    mileage: int
    fuel: str = ""
    transmission: str = ""
    body: str = ""
    variant: str = ""
    colour: str = ""
    doors: int | None = None
    seats: int | None = None
    description: str = ""
    features: list[str] = field(default_factory=list)
    id: int | None = None

    @property
    def title(self) -> str:
        parts = [str(self.year), self.make, self.model, self.variant]
        return " ".join(p for p in parts if p)


@dataclass(frozen=True)
class ComplianceIssue:
    code: str
    severity: Severity
    message: str
    evidence: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["severity"] = str(self.severity)
        return d


@dataclass(frozen=True)
class RiskReport:
    """Result of a vehicle history check. Field semantics follow the usual UK
    history-check products (HPI/Experian) so a real provider can map onto it."""

    reg: str
    source: str
    checked_at: str  # ISO date
    outstanding_finance: bool = False
    write_off_category: str | None = None  # "A", "B", "S", "N" (or legacy "C", "D")
    stolen: bool = False
    mileage_discrepancy: bool = False
    mot_expiry: str | None = None  # ISO date
    previous_keepers: int | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class LeadRequest:
    vehicle_id: int
    name: str
    consent_contact: bool
    email: str = ""
    phone: str = ""
    message: str = ""
    budget_gbp: int | None = None
    timeframe_days: int | None = None
    wants_test_drive: bool = False
    has_part_exchange: bool = False
    consent_marketing: bool = False
