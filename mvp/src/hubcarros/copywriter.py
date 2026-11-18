"""Draft listing text from structured facts only.

The canvas promises "IA gera textos automaticamente". The safe first step is a
template that can only state facts present in the data, so it can never
invent "one owner" or "full service history". An LLM can later rewrite the
tone, but its output must pass ``compliance.check_listing`` and be approved by
the dealer before publishing.
"""

from __future__ import annotations

from .models import RiskReport, Vehicle


def draft_description(v: Vehicle, report: RiskReport | None = None) -> str:
    specs = [
        f"{v.mileage:,} miles",
        v.fuel.capitalize() if v.fuel else "",
        v.transmission.capitalize() if v.transmission else "",
        v.body.upper() if v.body == "suv" or v.body == "mpv" else v.body.capitalize(),
        f"{v.doors} doors" if v.doors else "",
        f"{v.seats} seats" if v.seats else "",
        v.colour,
    ]
    lines = [f"{v.title}. " + ", ".join(s for s in specs if s) + "."]
    if v.features:
        lines.append("Features: " + ", ".join(v.features[:8]) + ".")
    if report is not None:
        if report.write_off_category:
            lines.append(f"Recorded as Category {report.write_off_category} insurance loss.")
        if report.previous_keepers is not None:
            lines.append(f"Previous keepers on record: {report.previous_keepers}.")
        if report.mot_expiry:
            lines.append(f"MOT recorded until {report.mot_expiry}.")
        lines.append(f"History check: {report.source}, {report.checked_at}.")
    if v.price_gbp:
        lines.append(f"Price £{v.price_gbp:,}, including all mandatory fees.")
    return " ".join(lines)
