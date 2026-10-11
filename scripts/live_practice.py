"""Teacher E2E: start practice_server and open COMMA Practice in a browser first.

The model only sees Cua tools. /state is an independent teacher verifier.
"""
import asyncio
import json
from pathlib import Path

import httpx

from common.core.config import load_config
from common.core.experiments import task_by_id
from common.core.mcp_transport import connect_driver
from common.core.policy import structured
from tests.support.cua_verifier import call_tool
from scripts.web_client import web_runner


async def main():
    config = load_config().copy(model="google/gemini-3.8-flash")
    async with connect_driver(config.driver) as session:
        windows = structured(await call_tool(session, "list_windows", {}))["windows"]
        target = next(w for w in windows if "COMMA Practice" in (w.get("title", "") + w.get("window_title", "")))
    config.target_pid, config.target_window = target["pid"], target["window_id"]
    results = []
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8765") as client:
        async with web_runner(config) as runner:
            for task, perception, field in [("form", "hybrid", "form_success"), ("canvas", "vision", "canvas_success")]:
                await client.post("/state", json={field: False})
                await runner.new(config.model, task, perception=perception)
                record = await runner.submit(task_by_id(task).prompt)
                state = (await client.get("/state")).json()
                result = {"model": config.model, "task": task, "perception": perception,
                          "passed": state[field], "status": record["status"], "state": state,
                          "run_id": record["id"], "seconds": record["elapsed_seconds"]}
                results.append(result)
                Path("artifacts/live-practice.json").write_text(json.dumps(results, ensure_ascii=False, indent=2))
                print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
