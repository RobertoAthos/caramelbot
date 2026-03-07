from __future__ import annotations

import os

import httpx

MCP_URL = os.getenv("PLAYWRIGHT_MCP_URL", "http://localhost:3000")


async def call_mcp_tool(tool_name: str, arguments: dict | None = None) -> dict:
    """Call a tool on the MCP Playwright server via JSON-RPC."""
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments or {},
        },
    }
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(MCP_URL, json=payload)
        resp.raise_for_status()
        return resp.json()


async def navigate(url: str) -> dict:
    return await call_mcp_tool("browser_navigate", {"url": url})


async def click(selector: str) -> dict:
    return await call_mcp_tool("browser_click", {"selector": selector})


async def fill(selector: str, value: str) -> dict:
    return await call_mcp_tool("browser_fill", {"selector": selector, "value": value})


async def screenshot() -> dict:
    return await call_mcp_tool("browser_screenshot", {})


async def get_text(selector: str = "body") -> dict:
    return await call_mcp_tool("browser_get_text", {"selector": selector})
