"""Deterministic synthetic UK used-car market, for demos and load tests.

Everything here is invented: dealers, registrations and prices. Dealer names
end in "(synthetic)" so the data can never be mistaken for real listings.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field
from datetime import date, timedelta

from .ingest import IngestResult
from .models import Dealer, RiskReport, Vehicle
from .service import Hub

# make, model, body, fuels, transmission, seats, approx. new price (GBP)
MODELS = [
    ("Ford", "Fiesta", "hatchback", ("petrol",), "manual", 5, 21000),
    ("Ford", "Focus", "hatchback", ("petrol", "diesel"), "manual", 5, 26000),
    ("Ford", "Kuga", "suv", ("petrol", "plug-in hybrid"), "automatic", 5, 34000),
    ("Vauxhall", "Corsa", "hatchback", ("petrol", "electric"), "manual", 5, 20000),
    ("Vauxhall", "Astra", "hatchback", ("petrol", "diesel"), "manual", 5, 25000),
    ("Volkswagen", "Polo", "hatchback", ("petrol",), "manual", 5, 22000),
    ("Volkswagen", "Golf", "hatchback", ("petrol", "diesel"), "manual", 5, 29000),
    ("Volkswagen", "Tiguan", "suv", ("petrol", "diesel"), "automatic", 5, 36000),
    ("Toyota", "Yaris", "hatchback", ("hybrid",), "automatic", 5, 23000),
    ("Toyota", "Corolla", "hatchback", ("hybrid",), "automatic", 5, 30000),
    ("Toyota", "RAV4", "suv", ("hybrid",), "automatic", 5, 38000),
    ("Nissan", "Qashqai", "suv", ("petrol",), "manual", 5, 30000),
    ("Kia", "Sportage", "suv", ("petrol", "hybrid"), "automatic", 5, 32000),
    ("Kia", "Niro", "suv", ("hybrid", "electric"), "automatic", 5, 33000),
    ("Hyundai", "Tucson", "suv", ("petrol", "hybrid"), "automatic", 5, 33000),
    ("BMW", "3 Series", "saloon", ("diesel", "petrol"), "automatic", 5, 40000),
    ("Mercedes-Benz", "A-Class", "hatchback", ("petrol", "diesel"), "automatic", 5, 33000),
    ("Audi", "A3", "hatchback", ("petrol", "diesel"), "manual", 5, 31000),
    ("Skoda", "Octavia", "estate", ("diesel", "petrol"), "manual", 5, 28000),
    ("Peugeot", "5008", "suv", ("diesel", "petrol"), "automatic", 7, 36000),
    ("Tesla", "Model 3", "saloon", ("electric",), "automatic", 5, 42000),
    ("Mini", "Hatch", "hatchback", ("petrol",), "manual", 4, 24000),
]
AREAS = ["LS1", "M1", "B1", "G1", "EH1", "CF10", "BS1", "NG1", "S1", "L1", "NE1", "SO14", "PL1", "LE1",
         "CV1", "BT1", "AB10", "E1", "N1", "SE1", "NW1", "RG1", "MK9", "YO1", "HU1", "PE1", "NR1", "EX1"]
COLOURS = ["Black", "White", "Grey", "Silver", "Blue", "Red"]
FEATURES = ["Sat nav", "Bluetooth", "Apple CarPlay", "Heated seats", "Reversing camera", "Cruise control",
            "Parking sensors", "LED lights", "DAB radio", "Keyless entry"]


def _h(text: str) -> int:
    return int(hashlib.sha256(text.encode()).hexdigest()[:8], 16)


class SyntheticRiskProvider:
    """Deterministic fake history checks: mostly clear, a few write-offs and finance markers."""

    name = "simulated provider (synthetic data)"

    def __init__(self, today: date):
        self.today = today

    def check(self, reg: str) -> RiskReport:
        h = _h(reg)
        return RiskReport(
            reg=reg, source=self.name, checked_at=self.today.isoformat(),
            outstanding_finance=h % 100 == 0,
            write_off_category="N" if h % 40 == 1 else ("S" if h % 90 == 2 else None),
            previous_keepers=1 + h % 4,
            mot_expiry=(self.today + timedelta(days=30 + h % 330)).isoformat(),
        )


@dataclass
class _Car:
    vehicle: Vehicle
    value: float  # underlying market value at listing
    listed_on: date


@dataclass
class _Dealer:
    dealer: Dealer
    target: int
    markup: float
    stock: list[_Car] = field(default_factory=list)


class SyntheticMarket:
    def __init__(self, seed: int = 7, n_dealers: int = 30, end: date | None = None, days: int = 60):
        self.rng = random.Random(seed)
        self.end = end or date.today()
        self.start = self.end - timedelta(days=days)
        # slow per-model trend (% per day), e.g. EVs softening, hybrids firming
        self.trend = {m[1]: self.rng.uniform(-0.08, 0.05) / 100 for m in MODELS}
        for m in MODELS:
            if "electric" in m[3] and len(m[3]) == 1:
                self.trend[m[1]] = self.rng.uniform(-0.15, -0.06) / 100
        self.dealers = [
            _Dealer(
                Dealer(f"syn-{i:03d}", f"{self.rng.choice(['Northern', 'City', 'Premier', 'Family', 'Motorway', 'Station'])} "
                       f"{self.rng.choice(['Motors', 'Cars', 'Autos', 'Car Sales'])} {i:03d} (synthetic)",
                       f"{self.rng.choice(AREAS)} {self.rng.randint(1, 9)}{self.rng.choice('ABDEFGHJ')}{self.rng.choice('LNPQRSTU')}"),
                target=self.rng.randint(8, 30), markup=self.rng.uniform(0.96, 1.06))
            for i in range(1, n_dealers + 1)
        ]
        self._regs: set[str] = set()

    def _reg(self, year: int) -> str:
        while True:
            age_code = (year % 100) + (50 if self.rng.random() < 0.5 else 0)
            letters = "ABCDEFGHJKLMNOPRSTUVWXY"
            reg = (self.rng.choice(letters) + self.rng.choice(letters) + f"{age_code:02d}"
                   + "".join(self.rng.choice(letters) for _ in range(3)))
            if reg not in self._regs:
                self._regs.add(reg)
                return reg

    def _value(self, model: tuple, year: int, mileage: int, day: date) -> float:
        age = max(0, self.end.year - year)
        base = model[6] * (0.9 ** age) * max(0.4, 1 - mileage / 400_000)
        drift = (1 + self.trend[model[1]]) ** (day - self.start).days
        return base * drift

    def _new_car(self, d: _Dealer, day: date) -> _Car:
        model = self.rng.choice(MODELS)
        year = self.rng.randint(self.end.year - 9, self.end.year - 1)
        mileage = int(max(1000, (self.end.year - year) * self.rng.uniform(5000, 12000)) // 100 * 100)
        value = self._value(model, year, mileage, day)
        price = int(round(value * d.markup * self.rng.uniform(0.93, 1.08), -1) - 5)
        reg = self._reg(year)
        risk = SyntheticRiskProvider(day).check(reg)
        fuel = self.rng.choice(model[3])
        desc = f"{year} {model[0]} {model[1]}, {mileage:,} miles. Price includes all fees."
        if risk.write_off_category:
            desc += f" Recorded Cat {risk.write_off_category}, professionally repaired."
        v = Vehicle(d.dealer.id, reg, model[0], model[1], year, price, mileage, fuel=fuel,
                    transmission=model[4], body=model[2], colour=self.rng.choice(COLOURS),
                    doors=5 if model[5] >= 5 else 3, seats=model[5], description=desc,
                    features=self.rng.sample(FEATURES, 4))
        return _Car(v, value, day)

    def _step(self, d: _Dealer, day: date) -> None:
        keep = []
        for car in d.stock:
            v = car.vehicle
            model = next(m for m in MODELS if m[1] == v.model and m[0] == v.make)
            fair = self._value(model, v.year, v.mileage, day)
            cheapness = (fair - v.price_gbp) / fair
            if self.rng.random() < (1 / 35) * (1 + max(-0.8, cheapness * 8)):
                continue  # sold
            age = (day - car.listed_on).days
            if age > 20 and self.rng.random() < 0.06:
                v.price_gbp = int(round(v.price_gbp * self.rng.uniform(0.94, 0.98), -1) - 5)
            keep.append(car)
        d.stock = keep
        while len(d.stock) < d.target and self.rng.random() < 0.6:
            d.stock.append(self._new_car(d, day))

    def run(self, hub: Hub, progress=None) -> dict:
        for d in self.dealers:
            hub.register_dealer(d.dealer)
            d.stock = [self._new_car(d, self.start) for _ in range(d.target)]
        day = self.start
        total = 0
        while day <= self.end:
            hub.risk = SyntheticRiskProvider(day)
            for d in self.dealers:
                if day > self.start:
                    self._step(d, day)
                snapshot = [Vehicle(**{**c.vehicle.__dict__, "features": list(c.vehicle.features), "id": None})
                            for c in d.stock]
                hub.ingest(d.dealer.id, IngestResult(vehicles=snapshot), observed_on=day, allow_empty=True)
                total += len(snapshot)
            if progress:
                progress(day)
            day += timedelta(days=1)
        return {"dealers": len(self.dealers), "days": (self.end - self.start).days + 1, "listing_observations": total}
