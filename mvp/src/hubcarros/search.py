"""Search filters and a light free-text interpreter.

Inside ChatGPT/Claude the model fills the structured filters itself; the
free-text parser covers other channels (SEO pages, widget) and acts as a
fallback when the assistant only forwards the user's sentence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, fields, replace

from .ingest import BODY_MAP, FUEL_MAP
from .makes import KNOWN_MAKES, MAKE_ALIASES
from .models import Vehicle




@dataclass(frozen=True)
class SearchFilters:
    make: str | None = None
    model: str | None = None
    min_price: int | None = None
    max_price: int | None = None
    max_mileage: int | None = None
    min_year: int | None = None
    fuel: str | None = None
    transmission: str | None = None
    body: str | None = None
    min_seats: int | None = None
    keywords: tuple[str, ...] = ()

    def merged_with(self, other: SearchFilters) -> SearchFilters:
        """Explicit values in ``other`` win over values in ``self``."""
        updates = {f.name: getattr(other, f.name) for f in fields(other) if getattr(other, f.name) not in (None, ())}
        return replace(self, **updates)


def _money(num: str, k: str | None) -> int:
    value = float(num.replace(",", ""))
    return int(value * 1000) if k else int(value)


def parse_query(text: str) -> SearchFilters:
    t = " " + text.lower() + " "
    out: dict = {}

    # Mileage first, then remove it so "under 50k miles" is not read as a price.
    m = re.search(r"(?:under|below|less than|fewer than|max(?:imum)?|up to)\s*(\d[\d,.]*)\s*(k)?\s*(?:miles|mi\b|mileage)", t)
    if m:
        out["max_mileage"] = _money(m.group(1), m.group(2))
        t = t[: m.start()] + " " + t[m.end() :]
    elif re.search(r"\blow mileage\b", t):
        out["max_mileage"] = 30000

    m = re.search(r"(?:under|below|less than|max(?:imum)?|up to|no more than|<)\s*£?\s*(\d[\d,.]*)\s*(k)?", t)
    if m:
        out["max_price"] = _money(m.group(1), m.group(2))
    m = re.search(r"(?:over|above|more than|from|at least)\s*£\s*(\d[\d,.]*)\s*(k)?", t)
    if m:
        out["min_price"] = _money(m.group(1), m.group(2))
    m = re.search(r"£\s*(\d[\d,.]*)\s*(k)?\s*(?:-|to)\s*£?\s*(\d[\d,.]*)\s*(k)?", t)
    if m:
        out["min_price"] = _money(m.group(1), m.group(2))
        out["max_price"] = _money(m.group(3), m.group(4))


    m = re.search(r"(?:20\d\d|19\d\d)\s*(?:or newer|onwards|\+|or later)|(?:newer than|after|from)\s*(20\d\d|19\d\d)", t)
    if m:
        year = re.search(r"(19|20)\d\d", m.group(0))
        out["min_year"] = int(year.group(0)) + (1 if "newer than" in m.group(0) or "after" in m.group(0) else 0)

    for word in sorted(FUEL_MAP, key=len, reverse=True):
        if re.search(rf"\b{re.escape(word)}\b", t):
            out["fuel"] = FUEL_MAP[word]
            break
    if re.search(r"\b(?:automatic|auto)\b", t):
        out["transmission"] = "automatic"
    elif re.search(r"\bmanual\b", t):
        out["transmission"] = "manual"
    for word in sorted(BODY_MAP, key=len, reverse=True):
        if re.search(rf"\b{re.escape(word)}s?\b", t):
            out["body"] = BODY_MAP[word]
            break
    m = re.search(r"\b(\d)\s*(?:-|\s)?seat(?:s|er)?\b", t)
    if m:
        out["min_seats"] = int(m.group(1))
    elif re.search(r"\bfamily\b", t) and "body" not in out:
        out["min_seats"] = 5

    for alias, make in MAKE_ALIASES.items():
        if re.search(rf"\b{re.escape(alias)}\b", t):
            out["make"] = make
    if "make" not in out:
        for make in KNOWN_MAKES:
            if re.search(rf"\b{re.escape(make.lower())}\b", t):
                out["make"] = make
                break
    return SearchFilters(**out)


def matches(v: Vehicle, f: SearchFilters) -> bool:
    """True when listing ``v`` satisfies every filter in ``f``."""
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
