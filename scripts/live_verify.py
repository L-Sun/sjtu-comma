"""Teacher-only opt-in E2E. Calls paid APIs; --desktop controls Calculator.

Run: uv run python scripts/live_verify.py [--desktop]
Each run goes through the browser HTTP API and runtime (no browser automation).
"""
import argparse
import asyncio
import json
from pathlib import Path
import re

from scripts.web_client import web_runner
from common.core.config import load_config
from common.core.experiments import task_by_id
from common.core.mcp_transport import connect_driver
from common.core.policy import structured
from tests.support.cua_verifier import call_tool


def calculator_display(tree):
    # macOS exposes the expression first and the result second. Never concatenate
    # expression digits (128×37 -> 12837) and mistake them for the result.
    subtree = tree.split("AXToolbar", 1)[0]
    values = re.findall(r'AXStaticText\s*=\s*"([^"]*)"', subtree)
    return re.sub(r"[^0-9.\-]", "", values[-1]) if values else None


async def calculator(config, *, reset=False):
    async with connect_driver(config.driver) as session:
        windows = structured(await call_tool(session, "list_windows", {}))["windows"]
        target = next(w for w in windows if w.get("app_name") == "Calculator")
        args = {"pid": target["pid"], "window_id": target["window_id"]}
        snap = structured(await call_tool(session, "get_window_state", dict(args, include_screenshot=False)))
        if reset:
            button = next(e for e in snap["elements"] if e.get("label") in {"All Clear", "Clear"} or "AllClear" in str(e))
            await call_tool(session, "click", dict(args, element_token=button["element_token"], delivery_mode="foreground"))
            await asyncio.sleep(.4)
            snap = structured(await call_tool(session, "get_window_state", dict(args, include_screenshot=False)))
            # Clear can clear only the current operand. Escape resets the complete
            # expression and a fresh observation must confirm the precondition.
            await call_tool(session, "press_key", dict(args, key="escape", delivery_mode="foreground"))
            await asyncio.sleep(.4)
            snap = structured(await call_tool(session, "get_window_state", dict(args, include_screenshot=False)))
        display = calculator_display(snap.get("tree_markdown", ""))
        if reset:
            assert display == "0", f"Calculator reset failed: {display}"
        return target, display


async def main(desktop=False, desktop_only=False, model=None, tasks=None):
    config = load_config()
    if model:
        config = config.copy(model=model, models=(model,))
    results = []
    async with web_runner(config) as runner:
        for chosen_model in (() if desktop_only else config.models):
            for task_id in (tasks or ["format", "constraints", "quoted", "tool-order", "code-edit"]):
                await runner.new(chosen_model, task_id)
                record = await runner.submit(task_by_id(task_id).prompt)
                result = {"model": chosen_model, "task": task_id, "status": record["status"],
                          "grade": record["grade"], "run_id": record["id"], "seconds": record["elapsed_seconds"]}
                results.append(result)
                print(json.dumps(result, ensure_ascii=False), flush=True)
            await runner.new(chosen_model)
            await runner.submit("请记住课堂暗号是 MARBLE-42。只回答已记住。")
            record = await runner.submit("课堂暗号是什么？只回答暗号。")
            answer = [e["data"]["text"] for e in record["events"] if e["kind"] == "assistant"][-1]
            result = {"model": chosen_model, "task": "multi-turn", "passed": answer.strip() == "MARBLE-42",
                      "run_id": record["id"]}
            results.append(result)
            print(json.dumps(result), flush=True)
        if desktop:
            for perception in ["vision", "tree", "hybrid"]:
                target, before = await calculator(config, reset=True)
                config.target_pid, config.target_window = target["pid"], target["window_id"]
                await runner.new(config.models[0], 'calculator', perception=perception)
                record = await runner.submit(task_by_id("calculator").prompt)
                _, after = await calculator(config)
                observed = [e for e in record["events"] if e["kind"] == "tool_end" and e["data"]["name"] == "get_window_state"]
                images = sum(e["data"]["result"]["image_count"] for e in observed)
                result = {"model": config.models[0], "task": "calculator", "perception": perception,
                          "before": before, "display": after, "passed": after == "4736",
                          "status": record["status"], "observations": len(observed), "images": images,
                          "run_id": record["id"]}
                results.append(result)
                print(json.dumps(result, ensure_ascii=False), flush=True)
    Path("artifacts").mkdir(exist_ok=True)
    Path("artifacts/live-results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--desktop", action="store_true")
    parser.add_argument("--desktop-only", action="store_true")
    parser.add_argument("--model")
    parser.add_argument("--task", action="append", choices=["format", "constraints", "quoted", "tool-order", "code-edit"])
    args = parser.parse_args()
    asyncio.run(main(args.desktop or args.desktop_only, args.desktop_only, args.model, args.task))
