from datetime import date
from pathlib import Path

import pytest

from hubcarros.db import Database
from hubcarros.ingest import parse_csv_file
from hubcarros.models import Dealer
from hubcarros.risk import FixtureRiskProvider
from hubcarros.service import Hub

DEMO = Path(__file__).resolve().parents[1] / "data" / "demo"
TODAY = date(2026, 11, 16)


@pytest.fixture
def provider():
    return FixtureRiskProvider(DEMO / "risk_fixture.json", today=TODAY)


@pytest.fixture
def hub(provider):
    h = Hub(Database(":memory:"), provider, today=TODAY)
    h.register_dealer(Dealer("demo-northgate", "Northgate Motors (demo)", "LS6 1AA"))
    h.register_dealer(Dealer("demo-riverside", "Riverside Car Sales (demo)", "WF1 2BB"))
    h.ingest("demo-northgate", parse_csv_file(DEMO / "northgate_stock.csv", "demo-northgate"))
    h.ingest("demo-riverside", parse_csv_file(DEMO / "riverside_stock.csv", "demo-riverside"))
    return h
