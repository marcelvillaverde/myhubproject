"""MCP server exposing the buyer-facing tools to ChatGPT/Claude.

Run (stdio):   HUBCARROS_DB=hub.db hubcarros-mcp
Run (HTTP):    HUBCARROS_DB=hub.db hubcarros-mcp --http
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Annotated

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from .db import Database
from .leads import LeadValidationError
from .models import LeadRequest
from .risk import FixtureRiskProvider
from .search import SearchFilters
from .service import Hub

INSTRUCTIONS = """\
You help people in the UK find used cars from independent local dealers.

Rules you must follow:
- Use search_vehicles to find cars. Pass the buyer's own words in `query` AND fill
  any structured filters you can infer (prices in GBP, mileage in miles).
- Use get_vehicle before describing a car in detail. Only state facts returned by
  the tools. Never invent service history, owner count or condition.
- Always show the history-check source, date and disclaimer when you mention a
  "verified" car. If a car is not verified, say so plainly.
- Do NOT calculate, estimate, compare or suggest finance, monthly payments, APR,
  deposits or insurance. If asked, say the dealer can explain finance options.
- Only call request_contact after the buyer has explicitly agreed that the dealer
  may contact them, and pass consent_contact=true. Ask for name and email or phone.
  Never call it on the buyer's behalf without that agreement.
"""


def build_hub() -> Hub:
    db_path = os.environ.get("HUBCARROS_DB", "hubcarros.db")
    fixture = os.environ.get("HUBCARROS_RISK_FIXTURE")
    provider = FixtureRiskProvider(fixture) if fixture and Path(fixture).exists() else None
    return Hub(Database(db_path), provider)


def create_server(hub: Hub) -> MCPServer:
    mcp = MCPServer(name="hubcarros", title="Carros usados verificados", instructions=INSTRUCTIONS, version="0.1.0")
    read_only = ToolAnnotations(read_only_hint=True, open_world_hint=False)
    # Tools are async on purpose: sync tools run in worker threads, and the
    # SQLite connection is bound to the thread that created it. Queries are
    # small and local, so running them on the event loop is fine for the MVP.

    @mcp.tool(annotations=read_only)
    async def search_vehicles(
        query: Annotated[str, Field(description="Buyer's request in their own words, e.g. 'automatic family SUV under £15k'")] = "",
        make: str | None = None,
        model: str | None = None,
        min_price: Annotated[int | None, Field(ge=0, description="GBP")] = None,
        max_price: Annotated[int | None, Field(ge=0, description="GBP")] = None,
        max_mileage: Annotated[int | None, Field(ge=0, description="miles")] = None,
        min_year: int | None = None,
        fuel: Annotated[str | None, Field(description="petrol | diesel | hybrid | plug-in hybrid | electric")] = None,
        transmission: Annotated[str | None, Field(description="manual | automatic")] = None,
        body: Annotated[str | None, Field(description="hatchback | saloon | estate | suv | mpv | coupe | convertible")] = None,
        min_seats: int | None = None,
        near_postcode: Annotated[str, Field(description="UK postcode or outward code to prefer nearby dealers")] = "",
        limit: Annotated[int, Field(ge=1, le=20)] = 10,
    ) -> dict:
        """Search used cars from local independent dealers. Returns summaries with a history-check badge."""
        filters = SearchFilters(
            make=make, model=model, min_price=min_price, max_price=max_price, max_mileage=max_mileage,
            min_year=min_year, fuel=fuel, transmission=transmission, body=body, min_seats=min_seats,
        )
        return hub.search(query=query, filters=filters, near_postcode=near_postcode, limit=limit)

    @mcp.tool(annotations=read_only)
    async def get_vehicle(vehicle_id: int) -> dict:
        """Full details for one car, including the history-check summary and the dealer."""
        result = hub.get_vehicle(vehicle_id)
        if result is None:
            raise ToolError("Vehicle not found or no longer available.")
        return result

    @mcp.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=True))
    async def request_contact(
        vehicle_id: int,
        name: str,
        consent_contact: Annotated[bool, Field(description="Must be true: the buyer explicitly agreed the dealer may contact them")],
        email: str = "",
        phone: Annotated[str, Field(description="UK phone number")] = "",
        message: str = "",
        budget_gbp: Annotated[int | None, Field(ge=0)] = None,
        timeframe_days: Annotated[int | None, Field(ge=0, description="When the buyer intends to buy, in days")] = None,
        wants_test_drive: bool = False,
        has_part_exchange: bool = False,
    ) -> dict:
        """Send the buyer's contact request to the dealer. Only with the buyer's explicit consent."""
        req = LeadRequest(
            vehicle_id=vehicle_id, name=name, consent_contact=consent_contact, email=email, phone=phone,
            message=message, budget_gbp=budget_gbp, timeframe_days=timeframe_days,
            wants_test_drive=wants_test_drive, has_part_exchange=has_part_exchange,
        )
        try:
            return hub.request_contact(req)
        except LeadValidationError as e:
            raise ToolError(str(e)) from e

    return mcp


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    server = create_server(build_hub())
    server.run("streamable-http" if "--http" in argv else "stdio")


if __name__ == "__main__":
    main()
