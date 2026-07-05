"""Tiny synchronous wrapper around the MCP streamable-HTTP client.

This module is deliberately Streamlit-free so it can be unit-tested on its own.
It connects to the TTA MCP server (default http://127.0.0.1:8010/mcp), lists
tools and calls them, hiding all the async/session plumbing behind two plain
functions: list_tools() and call_tool().
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

DEFAULT_URL = "http://127.0.0.1:8010/mcp"


def _run(coro):
    """Run one coroutine on a fresh event loop (safe inside Streamlit's thread)."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _first_text(result) -> str:
    for c in result.content:
        if getattr(c, "text", None):
            return c.text
    return ""


async def _list_tools(url: str):
    async with streamablehttp_client(url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            resp = await session.list_tools()
            return [
                {
                    "name": t.name,
                    "title": (getattr(t, "annotations", None) and getattr(t.annotations, "title", None)) or t.name,
                    "description": (t.description or "").strip(),
                    "schema": getattr(t, "inputSchema", None),
                }
                for t in resp.tools
            ]


async def _call_tool(url: str, name: str, args: dict[str, Any] | None):
    async with streamablehttp_client(url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            res = await session.call_tool(name, args or {})
            return _first_text(res), bool(res.isError)


# --------------------------------------------------------------- public API ---
def list_tools(url: str = DEFAULT_URL) -> list[dict]:
    """Return the server's tool catalog: [{name, title, description, schema}]."""
    return _run(_list_tools(url))


def call_tool(name: str, args: dict[str, Any] | None = None, url: str = DEFAULT_URL) -> tuple[Any, bool]:
    """Call a tool. Returns (result, is_error). Result is parsed JSON when the
    tool returned JSON text, otherwise the raw string (e.g. markdown)."""
    text, is_error = _run(_call_tool(url, name, args))
    try:
        return json.loads(text), is_error
    except (json.JSONDecodeError, TypeError):
        return text, is_error


def ping(url: str = DEFAULT_URL) -> tuple[bool, str]:
    """Health check for the UI: (reachable, message)."""
    try:
        tools = list_tools(url)
        return True, f"Connected — {len(tools)} tools available"
    except Exception as e:  # noqa: BLE001 - surface any connection/protocol error to the UI
        return False, f"Cannot reach MCP server at {url} — {type(e).__name__}: {e}"
