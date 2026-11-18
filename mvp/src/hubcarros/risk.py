"""Vehicle history (risk) checks.

The MVP ships with a fixture-backed provider so pilots can run before any
commercial data contract is signed. Real providers (DVSA MOT history, HPI,
Experian AutoCheck) implement the same ``RiskProvider`` protocol.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Protocol

from .models import RiskReport, Severity

DISCLAIMER = (
    "History check based on third-party data on the date shown. "
    "Confirm with the dealer and carry out your own checks before buying."
)


class RiskProvider(Protocol):
    name: str

    def check(self, reg: str) -> RiskReport | None:
        """Return a report, or None when the provider has no data for ``reg``."""
        ...


def normalise_reg(reg: str) -> str:
    return "".join(reg.split()).upper()


class FixtureRiskProvider:
    """Reads reports from a JSON file keyed by registration. For demos/tests only."""

    name = "simulated provider (demo data)"

    def __init__(self, path: Path | str, today: date | None = None):
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        self._data = {normalise_reg(k): v for k, v in raw.items()}
        self._today = today or date.today()

    def check(self, reg: str) -> RiskReport | None:
        row = self._data.get(normalise_reg(reg))
        if row is None:
            return None
        return RiskReport(
            reg=normalise_reg(reg),
            source=self.name,
            checked_at=self._today.isoformat(),
            outstanding_finance=bool(row.get("outstanding_finance", False)),
            write_off_category=row.get("write_off_category"),
            stolen=bool(row.get("stolen", False)),
            mileage_discrepancy=bool(row.get("mileage_discrepancy", False)),
            mot_expiry=row.get("mot_expiry"),
            previous_keepers=row.get("previous_keepers"),
        )


@dataclass(frozen=True)
class RiskFlag:
    code: str
    severity: Severity
    message: str


def mot_expired(report: RiskReport, today: date | None = None) -> bool:
    if not report.mot_expiry:
        return False
    return date.fromisoformat(report.mot_expiry) < (today or date.today())


def risk_flags(report: RiskReport | None, today: date | None = None) -> list[RiskFlag]:
    """Buyer-facing interpretation of a report."""
    if report is None:
        return []
    flags: list[RiskFlag] = []
    if report.stolen:
        flags.append(RiskFlag("STOLEN_MARKER", Severity.BLOCK, "Stolen marker recorded."))
    if report.outstanding_finance:
        flags.append(
            RiskFlag("FINANCE_OUTSTANDING", Severity.BLOCK, "Outstanding finance recorded.")
        )
    if report.write_off_category:
        flags.append(
            RiskFlag(
                "WRITE_OFF",
                Severity.WARN,
                f"Recorded as a Category {report.write_off_category} insurance write-off.",
            )
        )
    if report.mileage_discrepancy:
        flags.append(
            RiskFlag("MILEAGE_DISCREPANCY", Severity.WARN, "Mileage discrepancy in the vehicle history.")
        )
    if mot_expired(report, today):
        flags.append(RiskFlag("MOT_EXPIRED", Severity.WARN, f"MOT expired on {report.mot_expiry}."))
    return flags


def risk_summary(report: RiskReport | None, today: date | None = None) -> dict:
    """Shape shown to buyers. Always carries source, date and disclaimer."""
    if report is None:
        return {"verified": False, "message": "No history check available for this vehicle."}
    flags = risk_flags(report, today)
    return {
        "verified": True,
        "clear": not flags,
        "source": report.source,
        "checked_at": report.checked_at,
        "flags": [{"code": f.code, "severity": str(f.severity), "message": f.message} for f in flags],
        "previous_keepers": report.previous_keepers,
        "mot_expiry": report.mot_expiry,
        "disclaimer": DISCLAIMER,
    }
