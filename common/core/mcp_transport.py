"""Teacher-owned transport lifecycle. No tool discovery/execution solution here."""
from contextlib import asynccontextmanager
from datetime import timedelta
import os
import tempfile

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


@asynccontextmanager
async def connect_driver(command: str):
    # The subprocess must never inherit the model API key.
    env = {key: value for key, value in os.environ.items()
           if key in {"PATH", "HOME", "USERPROFILE", "SYSTEMROOT", "WINDIR",
                      "TEMP", "TMP", "LOCALAPPDATA", "APPDATA"}}
    env["CUA_TELEMETRY_ENABLED"] = "false"
    # Keep driver output away from the interactive terminal.
    with tempfile.TemporaryFile(mode="w+") as errors:
        async with stdio_client(StdioServerParameters(
            command=command, args=["mcp"], env=env,
        ), errlog=errors) as (read, write):
            async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=30)) as session:
                await session.initialize()
                yield session
