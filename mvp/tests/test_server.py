import asyncio

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from hubcarros.server import create_server


def test_tools_registered_and_callable(hub):
    server = create_server(hub)

    async def run():
        tools = {t.name for t in await server.list_tools()}
        assert tools == {"search_vehicles", "get_vehicle", "request_contact"}
        res = await server.call_tool("search_vehicles", {"query": "hybrid hatchback"})
        assert not res.is_error
        with pytest.raises(ToolError, match="consent"):
            await server.call_tool("request_contact", {"vehicle_id": 1, "name": "X", "consent_contact": False, "email": "x@example.com"})

    asyncio.run(run())
