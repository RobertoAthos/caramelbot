from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

server_params = StdioServerParameters(
    command="npx",
    args=["-y", "@modelcontextprotocol/server-playwright"],
)


@asynccontextmanager
async def open_session() -> AsyncIterator[ClientSession]:
    """Open a persistent MCP Playwright session over stdio."""
    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            yield session


async def get_tool_definitions(session: ClientSession) -> list[dict]:
    """Fetch MCP tools and convert them to OpenAI function-calling format."""
    result = await session.list_tools()
    tools = []
    for tool in result.tools:
        tools.append({
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description or "",
                "parameters": tool.inputSchema,
            },
        })
    return tools


async def call_tool(session: ClientSession, tool_name: str, arguments: dict) -> str:
    """Call an MCP tool and return the result as a string."""
    result = await session.call_tool(tool_name, arguments)
    if result.isError:
        return f"Error: {result.content}"
    parts = []
    for block in result.content:
        if hasattr(block, "text"):
            parts.append(block.text)
        else:
            parts.append(str(block))
    return "\n".join(parts) if parts else "OK"
