"""Rule-based compliance checks for used-car listings (UK).

Each rule is small and explicit so the pilot can measure precision per rule
(hypothesis H5) before any ML classifier is introduced. Listing text is
assumed to be English, as published on UK sites.

These rules are a risk screen, not legal advice. See
docs/modulo-conteudo/briefing-juridico.md.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import date

from .models import ComplianceIssue, ListingStatus, RiskReport, Severity, Vehicle
from .risk import mot_expired

Rule = Callable[[Vehicle, RiskReport | None, date], list[ComplianceIssue]]

_I = re.IGNORECASE

FINANCE_TRIGGER = re.compile(
    r"(£\s?\d[\d,]*(?:\.\d{2})?\s*(?:/|per|a)\s*(?:month|mth|pm\b|week)"
    r"|\b\d[\d,]*\s*(?:per month|p/m|pcm)\b"
    r"|\bAPR\b|\binterest rate\b|\bdeposit of\b|\bmonthly payments?\b|\bfinance from\b)",
    _I,
)
REP_EXAMPLE = re.compile(r"representative\s+example", _I)
REP_APR = re.compile(r"\d+(?:\.\d+)?\s*%\s*APR|APR\s*(?:of\s*)?\d+(?:\.\d+)?\s*%", _I)

DRIP_FEE = re.compile(
    r"(?:\+|plus|excluding|excl\.?|not including)\s*(?:a\s*)?(?:£\s?\d[\d,]*\s*)?"
    r"(?:admin(?:istration)?|prep(?:aration)?|documentation|doc|dealer|handling)\s*fee"
    r"|(?:admin(?:istration)?|prep(?:aration)?|documentation|doc|dealer|handling)\s*fee\s*(?:of\s*)?£\s?\d[\d,]*\s*(?:applies|payable|extra|on top)",
    _I,
)
EX_VAT = re.compile(r"\+\s*VAT\b|\bplus VAT\b|\bex(?:cl(?:uding)?)?\.?\s*VAT\b", _I)
RIGHTS_EXCLUSION = re.compile(
    r"\bsold as seen\b|\bno warrant(?:y|ies)\b|\bno returns\b|\bno refunds?\b|\bsold as is\b",
    _I,
)
TRADE_SALE = re.compile(r"\btrade sale\b|\btrade only\b|\bto the trade\b", _I)
MILEAGE_IN_TEXT = re.compile(r"\b(\d{1,3}(?:,\d{3})+|\d{4,6})\s*(?:miles|mi\b)", _I)
MILEAGE_K_IN_TEXT = re.compile(r"\b(\d{1,3})\s*k\s*(?:miles|mi\b)", _I)
HISTORY_CLAIMS = {
    "full service history": re.compile(r"\bfull (?:main dealer )?service history\b|\bF\.?S\.?H\b", _I),
    "one owner": re.compile(r"\b(?:one|1|single) owner\b", _I),
    "HPI clear": re.compile(r"\bHPI clear\b|\bclear HPI\b", _I),
    "accident free": re.compile(r"\baccident[- ]free\b|\bnever been in an accident\b|\bno accidents?\b", _I),
}
WRITE_OFF_DISCLOSURE = re.compile(r"\bcat(?:egory)?\s*[ABCDNS]\b|\bwrite[- ]off\b|\binsurance loss\b", _I)
MOT_DISCLOSURE = re.compile(r"\bMOT (?:expired|due|required|needed)\b|\bno (?:current )?MOT\b|\bwithout (?:an )?MOT\b", _I)
SUPERLATIVE = re.compile(
    r"\bcheapest in the (?:UK|country|area)\b|\bbest price guaranteed\b|\bunbeatable\b|\blowest price in the UK\b",
    _I,
)


def _issue(code: str, sev: Severity, msg: str, evidence: str = "") -> ComplianceIssue:
    return ComplianceIssue(code=code, severity=sev, message=msg, evidence=evidence.strip())


def rule_price_missing(v: Vehicle, r: RiskReport | None, today: date) -> list[ComplianceIssue]:
    if not v.price_gbp or v.price_gbp <= 0:
        return [_issue("PRICE_MISSING", Severity.BLOCK, "Listing has no full price.")]
    return []


def rule_finance(v: Vehicle, r: RiskReport | None, today: date) -> list[ComplianceIssue]:
    m = FINANCE_TRIGGER.search(v.description)
    if not m:
        return []
    if REP_EXAMPLE.search(v.description) and REP_APR.search(v.description):
        return []
    return [
        _issue(
            "FINANCE_NO_REP_EXAMPLE",
            Severity.BLOCK,
            "Mentions cost of credit without a representative example and APR (FCA CONC 3.5).",
            m.group(0),
        )
    ]


def rule_drip_pricing(v: Vehicle, r: RiskReport | None, today: date) -> list[ComplianceIssue]:
    m = DRIP_FEE.search(v.description)
    if not m:
        return []
    return [
        _issue(
            "DRIP_PRICING",
            Severity.BLOCK,
            "Mandatory fee charged on top of the advertised price (DMCC Act / CAP Code). Include it in the price.",
            m.group(0),
        )
    ]


def rule_ex_vat(v: Vehicle, r: RiskReport | None, today: date) -> list[ComplianceIssue]:
    m = EX_VAT.search(v.description)
    if not m:
        return []
    return [
        _issue(
            "PRICE_EX_VAT",
            Severity.WARN,
            "Price shown excluding VAT; only acceptable if the ad is addressed exclusively to business buyers.",
            m.group(0),
        )
    ]


def rule_consumer_rights(v: Vehicle, r: RiskReport | None, today: date) -> list[ComplianceIssue]:
    m = RIGHTS_EXCLUSION.search(v.description)
    if not m:
        return []
    if TRADE_SALE.search(v.description):
        return [
            _issue(
                "TRADE_SALE_CHECK",
                Severity.WARN,
                "Declared as a trade sale. Confirm it will not be sold to consumers.",
                m.group(0),
            )
        ]
    return [
        _issue(
            "CONSUMER_RIGHTS_EXCLUSION",
            Severity.BLOCK,
            "Purports to exclude statutory consumer rights (Consumer Rights Act 2015), which is not allowed in consumer sales.",
            m.group(0),
        )
    ]


def _mileages_in_text(text: str) -> list[int]:
    found = [int(x.replace(",", "")) for x in MILEAGE_IN_TEXT.findall(text)]
    found += [int(x) * 1000 for x in MILEAGE_K_IN_TEXT.findall(text)]
    return found


def rule_mileage_mismatch(v: Vehicle, r: RiskReport | None, today: date) -> list[ComplianceIssue]:
    for miles in _mileages_in_text(v.description):
        if abs(miles - v.mileage) > 1000:
            return [
                _issue(
                    "MILEAGE_MISMATCH",
                    Severity.BLOCK,
                    f"Text says {miles:,} miles; vehicle record says {v.mileage:,}.",
                    f"{miles} miles",
                )
            ]
    return []


def rule_unverified_history(v: Vehicle, r: RiskReport | None, today: date) -> list[ComplianceIssue]:
    issues = []
    for claim, pattern in HISTORY_CLAIMS.items():
        m = pattern.search(v.description)
        if not m:
            continue
        # A history check can corroborate some claims; others need dealer evidence.
        if r is not None:
            if claim == "one owner" and r.previous_keepers is not None and r.previous_keepers <= 1:
                continue
            if claim == "HPI clear" and not (r.outstanding_finance or r.stolen or r.write_off_category):
                continue
        issues.append(
            _issue(
                "UNVERIFIED_HISTORY_CLAIM",
                Severity.WARN,
                f"Claim '{claim}' has no recorded evidence. Attach evidence or remove it.",
                m.group(0),
            )
        )
    # Contradictions with the history check are hard failures.
    if r is not None:
        if r.previous_keepers and r.previous_keepers > 1:
            m = HISTORY_CLAIMS["one owner"].search(v.description)
            if m:
                issues.append(
                    _issue(
                        "HISTORY_CONTRADICTION",
                        Severity.BLOCK,
                        f"Text says one owner; history check records {r.previous_keepers} keepers.",
                        m.group(0),
                    )
                )
    return issues


def rule_risk_report(v: Vehicle, r: RiskReport | None, today: date) -> list[ComplianceIssue]:
    if r is None:
        return []
    issues = []
    if r.stolen:
        issues.append(_issue("STOLEN_MARKER", Severity.BLOCK, "History check shows a stolen marker."))
    if r.outstanding_finance:
        issues.append(
            _issue("FINANCE_OUTSTANDING", Severity.BLOCK, "History check shows outstanding finance.")
        )
    if r.write_off_category and not WRITE_OFF_DISCLOSURE.search(v.description):
        issues.append(
            _issue(
                "WRITE_OFF_NOT_DISCLOSED",
                Severity.BLOCK,
                f"Recorded as Category {r.write_off_category} write-off and the listing does not disclose it.",
            )
        )
    if mot_expired(r, today) and not MOT_DISCLOSURE.search(v.description):
        issues.append(
            _issue(
                "MOT_EXPIRED_NOT_DISCLOSED",
                Severity.WARN,
                f"MOT expired on {r.mot_expiry} and the listing does not say so.",
            )
        )
    return issues


def rule_superlative(v: Vehicle, r: RiskReport | None, today: date) -> list[ComplianceIssue]:
    m = SUPERLATIVE.search(v.description)
    if not m:
        return []
    return [
        _issue(
            "UNSUBSTANTIATED_SUPERLATIVE",
            Severity.WARN,
            "Absolute comparative claim that needs substantiation (CAP Code 3.7).",
            m.group(0),
        )
    ]


RULES: list[Rule] = [
    rule_price_missing,
    rule_finance,
    rule_drip_pricing,
    rule_ex_vat,
    rule_consumer_rights,
    rule_mileage_mismatch,
    rule_unverified_history,
    rule_risk_report,
    rule_superlative,
]


def check_listing(
    vehicle: Vehicle, report: RiskReport | None = None, today: date | None = None
) -> list[ComplianceIssue]:
    today = today or date.today()
    issues: list[ComplianceIssue] = []
    for rule in RULES:
        issues.extend(rule(vehicle, report, today))
    return issues


def status_for(issues: list[ComplianceIssue]) -> ListingStatus:
    if any(i.severity is Severity.BLOCK for i in issues):
        return ListingStatus.BLOCKED
    if issues:
        return ListingStatus.NEEDS_REVIEW
    return ListingStatus.PUBLISHED
