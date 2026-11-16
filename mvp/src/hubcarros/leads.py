"""Lead validation and intent scoring.

Weights are a starting point; recalibrate after the dealer interviews
(question 11 of the interview script) and with real visit outcomes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .models import IntentTier, LeadRequest

RETENTION_DAYS = 180
HIGH_THRESHOLD = 70
MEDIUM_THRESHOLD = 40

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
UK_PHONE_RE = re.compile(r"^(?:\+44\s?|0)\d[\d\s]{8,12}$")


class LeadValidationError(ValueError):
    pass


@dataclass(frozen=True)
class IntentScore:
    score: int
    tier: IntentTier
    reasons: tuple[str, ...]


def validate(req: LeadRequest) -> None:
    if not req.consent_contact:
        raise LeadValidationError(
            "The buyer must explicitly agree that the dealer may contact them (consent_contact=true)."
        )
    if not req.name.strip():
        raise LeadValidationError("Name is required.")
    if not req.email and not req.phone:
        raise LeadValidationError("Provide an email address or phone number.")
    if req.email and not EMAIL_RE.match(req.email.strip()):
        raise LeadValidationError("Invalid email address.")
    if req.phone and not UK_PHONE_RE.match(req.phone.strip()):
        raise LeadValidationError("Invalid UK phone number (e.g. 07700 900123 or +44 7700 900123).")
    if req.budget_gbp is not None and req.budget_gbp < 0:
        raise LeadValidationError("Invalid budget.")
    if req.timeframe_days is not None and req.timeframe_days < 0:
        raise LeadValidationError("Invalid timeframe.")


def score(req: LeadRequest, vehicle_price: int | None) -> IntentScore:
    points = 0
    reasons: list[str] = []

    if req.wants_test_drive:
        points += 25
        reasons.append("wants a test drive/viewing")
    if req.timeframe_days is not None:
        if req.timeframe_days <= 7:
            points += 20
            reasons.append("buying within 7 days")
        elif req.timeframe_days <= 30:
            points += 10
            reasons.append("buying within 30 days")
    if req.budget_gbp is not None:
        if vehicle_price and req.budget_gbp >= 0.9 * vehicle_price:
            points += 20
            reasons.append("budget covers the price")
        else:
            points += 8
            reasons.append("gave a budget (below price)")
    if req.phone:
        points += 10
        reasons.append("left a phone number")
    if req.has_part_exchange:
        points += 10
        reasons.append("has a part-exchange")
    if len(req.message.strip()) >= 40:
        points += 10
        reasons.append("specific message")

    points = min(points, 100)
    if points >= HIGH_THRESHOLD:
        tier = IntentTier.HIGH
    elif points >= MEDIUM_THRESHOLD:
        tier = IntentTier.MEDIUM
    else:
        tier = IntentTier.LOW
    return IntentScore(points, tier, tuple(reasons))
