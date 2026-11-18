"""Parse a dealer stock CSV into ``Vehicle`` objects.

Dealer exports vary, so headers are matched through an alias table and values
are normalised ("£12,995" -> 12995, "45k miles" -> 45000). Rows that cannot be
used are reported, never silently dropped.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from pathlib import Path

from .makes import canonical_make
from .models import Vehicle
from .risk import normalise_reg

HEADER_ALIASES: dict[str, tuple[str, ...]] = {
    "reg": ("reg", "registration", "vrm", "reg_no", "registration number", "plate"),
    "make": ("make", "manufacturer", "brand"),
    "model": ("model",),
    "variant": ("variant", "derivative", "trim", "version"),
    "year": ("year", "reg_year", "model year", "first registered"),
    "price_gbp": ("price", "price_gbp", "retail price", "asking price", "cash price"),
    "mileage": ("mileage", "miles", "odometer"),
    "fuel": ("fuel", "fuel type", "fuel_type"),
    "transmission": ("transmission", "gearbox"),
    "body": ("body", "body type", "body_type", "bodystyle", "body style"),
    "colour": ("colour", "color"),
    "doors": ("doors",),
    "seats": ("seats",),
    "description": ("description", "advert text", "advert", "comments", "notes"),
    "features": ("features", "options", "equipment"),
}
REQUIRED = ("reg", "make", "model", "year", "mileage")

FUEL_MAP = {
    "petrol": "petrol", "unleaded": "petrol", "gasoline": "petrol",
    "diesel": "diesel",
    "hybrid": "hybrid", "petrol hybrid": "hybrid", "diesel hybrid": "hybrid", "self-charging hybrid": "hybrid",
    "plug-in hybrid": "plug-in hybrid", "phev": "plug-in hybrid", "petrol plug-in hybrid": "plug-in hybrid",
    "electric": "electric", "ev": "electric", "bev": "electric",
}
TRANSMISSION_MAP = {"manual": "manual", "automatic": "automatic", "auto": "automatic", "semi-auto": "automatic", "cvt": "automatic", "dsg": "automatic"}
BODY_MAP = {
    "hatchback": "hatchback", "hatch": "hatchback",
    "saloon": "saloon", "sedan": "saloon",
    "estate": "estate", "tourer": "estate", "wagon": "estate",
    "suv": "suv", "4x4": "suv", "crossover": "suv",
    "mpv": "mpv", "people carrier": "mpv",
    "coupe": "coupe", "convertible": "convertible", "cabriolet": "convertible",
    "pickup": "pickup", "pick-up": "pickup", "van": "van",
}


@dataclass
class RowError:
    line: int
    reason: str


@dataclass
class IngestResult:
    vehicles: list[Vehicle] = field(default_factory=list)
    errors: list[RowError] = field(default_factory=list)


def _int(value: str) -> int | None:
    if value is None:
        return None
    v = value.strip().lower().replace(",", "").replace("£", "")
    if not v:
        return None
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*k(?:\s*miles)?", v)
    if m:
        return int(float(m.group(1)) * 1000)
    m = re.match(r"(\d+(?:\.\d+)?)", v)
    return int(float(m.group(1))) if m else None


def _norm(value: str, mapping: dict[str, str]) -> str:
    v = (value or "").strip().lower()
    return mapping.get(v, v)


def _resolve_headers(fieldnames: list[str]) -> dict[str, str]:
    lookup = {f.strip().lower(): f for f in fieldnames}
    resolved = {}
    for key, aliases in HEADER_ALIASES.items():
        for alias in aliases:
            if alias in lookup:
                resolved[key] = lookup[alias]
                break
    return resolved


def parse_csv(text: str, dealer_id: str) -> IngestResult:
    reader = csv.DictReader(io.StringIO(text))
    result = IngestResult()
    if not reader.fieldnames:
        result.errors.append(RowError(1, "Arquivo vazio ou sem cabeçalho."))
        return result
    cols = _resolve_headers(reader.fieldnames)
    missing = [k for k in REQUIRED if k not in cols]
    if missing:
        result.errors.append(RowError(1, f"Colunas obrigatórias ausentes: {', '.join(missing)}"))
        return result

    seen: set[str] = set()
    for line, row in enumerate(reader, start=2):
        get = lambda k: (row.get(cols[k]) or "").strip() if k in cols else ""  # noqa: E731
        reg = normalise_reg(get("reg"))
        if not reg:
            result.errors.append(RowError(line, "Sem placa (reg)."))
            continue
        if reg in seen:
            result.errors.append(RowError(line, f"Placa duplicada no arquivo: {reg}."))
            continue
        year, mileage = _int(get("year")), _int(get("mileage"))
        if year is None or not (1950 <= year <= 2100):
            result.errors.append(RowError(line, f"Ano inválido: {get('year')!r}."))
            continue
        if mileage is None:
            result.errors.append(RowError(line, f"Quilometragem inválida: {get('mileage')!r}."))
            continue
        if not get("make") or not get("model"):
            result.errors.append(RowError(line, "Marca/modelo ausentes."))
            continue
        seen.add(reg)
        features = [f.strip() for f in re.split(r"[;|]", get("features")) if f.strip()]
        result.vehicles.append(
            Vehicle(
                dealer_id=dealer_id,
                reg=reg,
                make=canonical_make(get("make")),
                model=get("model").strip(),
                variant=get("variant"),
                year=year,
                price_gbp=_int(get("price_gbp")),
                mileage=mileage,
                fuel=_norm(get("fuel"), FUEL_MAP),
                transmission=_norm(get("transmission"), TRANSMISSION_MAP),
                body=_norm(get("body"), BODY_MAP),
                colour=get("colour").title(),
                doors=_int(get("doors")),
                seats=_int(get("seats")),
                description=get("description"),
                features=features,
            )
        )
    return result


def parse_csv_file(path: Path | str, dealer_id: str) -> IngestResult:
    return parse_csv(Path(path).read_text(encoding="utf-8-sig"), dealer_id)
