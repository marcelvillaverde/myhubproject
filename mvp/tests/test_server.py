import asyncio

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from hubcarros.server import create_server


def test_tools_registered_and_callable(hub):
    server = create_server(hub)

    async def run():
        tools = {t.name for t in await server.list_tools()}
        assert tools == {"search_vehicles", "get_vehicle", "request_contact", "market_overview", "get_ticker",
                         "create_watcher", "add_watch", "list_watches", "remove_watch", "get_alerts"}
        res = await server.call_tool("search_vehicles", {"query": "hybrid hatchback"})
        assert not res.is_error
        with pytest.raises(ToolError, match="consent"):
            await server.call_tool("request_contact", {"vehicle_id": 1, "name": "X", "consent_contact": False, "email": "x@example.com"})

    asyncio.run(run())


def test_terminal_tools_roundtrip(hub):
    server = create_server(hub)

    async def run():
        created = await server.call_tool("create_watcher", {})
        token = created.structured_content["watcher_token"]
        added = await server.call_tool("add_watch", {"watcher_token": token, "kind": "ticker", "ticker": "HONDA-JAZZ-2020"})
        assert not added.is_error
        ov = await server.call_tool("market_overview", {})
        assert ov.structured_content["active_listings"] > 0
        tk = await server.call_tool("get_ticker", {"ticker": "HONDA-JAZZ-2020"})
        assert tk.structured_content["quote"]["active"] == 1
        with pytest.raises(ToolError, match="Unknown watcher"):
            await server.call_tool("get_alerts", {"watcher_token": "wt_bad"})
        with pytest.raises(ToolError, match="Unknown ticker"):
            await server.call_tool("get_ticker", {"ticker": "NOPE"})

    asyncio.run(run())
