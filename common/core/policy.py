"""Teacher-owned experimental controls: model-visible tools and observations.

No DOM, shell, clipboard, file reading, browser JS, or unfiltered native tools.
This is an experimental boundary, not a sandbox against malicious student code.
"""
from __future__ import annotations
import copy
import json
import re
from common.core.types import Image, ToolResult, ToolSpec

FIELDS = {
    "list_windows": {"pid", "on_screen_only"},
    "get_window_state": {"pid", "window_id"},
    "click": {"pid", "window_id", "x", "y", "element_token", "capture_id", "button", "delivery_mode"},
    "type_text": {"pid", "window_id", "text", "element_token", "x", "y", "delivery_mode"},
    "press_key": {"pid", "window_id", "key", "modifiers", "element_token", "delivery_mode"},
    "hotkey": {"pid", "window_id", "keys", "element_token", "delivery_mode"},
    "scroll": {"pid", "window_id", "direction", "amount", "x", "y", "element_token", "delivery_mode"},
}
DESCRIPTIONS = {
    "list_windows": "List open application windows to obtain pid and window_id. Ask the user to open the app if absent.",
    "get_window_state": "Observe one window. Observe before acting and again to verify results. Coordinates are window-local screenshot pixels.",
    "click": "Click an observed location. In vision mode use x,y and capture_id. A capture_id is SINGLE USE: observe again before each pixel click. In tree/hybrid use element_token matching the element label, never confuse element_index with displayed digit.",
    "type_text": "Type text into the selected window or observed element. Verify by observing again.",
    "press_key": "Press one key (return, tab, escape, up, down). Optional modifiers: cmd, ctrl, shift, alt.",
    "hotkey": "Press a key combination, for example keys=[\"cmd\",\"a\"].",
    "scroll": "Scroll the selected window up/down/left/right. amount is wheel notches, 1 to 50.",
}
META = {"window_id", "pid", "window_bounds", "screenshot_scale", "screenshot_width",
        "screenshot_height", "capture_id", "app_name", "window_title", "snapshot_id",
        "degraded_reason", "truncated", "truncation_reason", "elements_complete"}
WINDOW_META = {"window_id", "pid", "app_name", "title", "window_title", "bounds", "on_screen"}


def tools_for_mode(native: list[ToolSpec], mode: str) -> list[ToolSpec]:
    if mode not in {"vision", "tree", "hybrid"}:
        raise ValueError("Unknown perception mode")
    result = []
    for spec in native:
        if spec.name not in FIELDS:
            continue
        allowed = FIELDS[spec.name].copy()
        if mode == "vision":
            allowed.discard("element_token")
        schema = copy.deepcopy(spec.parameters)
        schema["properties"] = {k: v for k, v in schema.get("properties", {}).items() if k in allowed}
        schema["required"] = [k for k in schema.get("required", []) if k in allowed]
        schema["additionalProperties"] = False
        # No opaque target object: the three conditions share window-scoped actions.
        if spec.name not in {"list_windows"}:
            schema["required"] = list(dict.fromkeys([*schema["required"], "pid", "window_id"]))
        result.append(ToolSpec(spec.name, DESCRIPTIONS[spec.name], schema))
    return result


def prepare_arguments(name: str, arguments: dict, mode: str) -> dict:
    args = dict(arguments)
    if name == "get_window_state":
        args.update(include_screenshot=mode != "tree", include_accessibility_tree=mode != "vision",
                    max_image_dimension=1280, max_elements=200, max_depth=15)
    return args


def structured(raw: dict) -> dict:
    value = raw.get("structuredContent")
    if isinstance(value, dict):
        return value
    for block in raw.get("content", []):
        if block.get("type") == "text":
            try:
                parsed = json.loads(block["text"])
                if isinstance(parsed, dict):
                    return parsed
                if isinstance(parsed, list):
                    return {"windows": parsed}
            except (ValueError, KeyError):
                pass
    return {}


def filter_result(name: str, raw: dict, mode: str) -> ToolResult:
    data = structured(raw)
    if (raw.get("isError") or data.get("is_error") or data.get("error") or data.get("ok") is False
            or data.get("refusal") or data.get("effect") in {"refused", "suspected_noop"}
            or data.get("status") in {"error", "refused", "failed"}):
        # Do not pass arbitrary rich error content (which can embed observations).
        error = data.get("error")
        code = error.get("code") if isinstance(error, dict) else data.get("code") or data.get("effect")
        return ToolResult(json.dumps({"error": code or "driver_error", "hint":
            "操作失败。检查目标窗口、权限或重新观察；不能宣称完成。"}, ensure_ascii=False), is_error=True)
    if name == "list_windows":
        windows = data.get("windows", [])
        return ToolResult(json.dumps({"windows": [
            {k: v for k, v in win.items() if k in WINDOW_META}
            for win in windows if isinstance(win, dict)]}, ensure_ascii=False))
    if name != "get_window_state":
        # Preserve operational feedback without leaking rich observations through
        # action results. In particular, 'unverifiable' is not confirmed success.
        result = {"hint": "Observe the window to verify the actual effect."}
        if data.get("effect") in {"confirmed", "partial", "unverifiable"}:
            result["effect"] = data["effect"]
        if data.get("route") in {"accessibility", "synthetic_events", "global_input", "system_api", "dom", "trusted_input"}:
            result["route"] = data["route"]
        escalation = data.get("escalation") or {}
        if isinstance(escalation, dict) and escalation.get("target") in {"pixel", "foreground", "page", "session"}:
            result["suggested_escalation"] = escalation["target"]
        return ToolResult(json.dumps(result))
    clean = {k: v for k, v in data.items() if k in META}
    images = []
    if mode != "vision":
        # macOS snapshots also contain the global menu bar (including Recent Items).
        # Keep the requested window's subtree; don't send unrelated recent files/apps.
        elements = []
        for element in data.get("elements", []):
            if element.get("role") in {"AXMenuBar", "MenuBar"}:
                break
            elements.append(element)
        clean["elements"] = elements
        clean["tree_markdown"] = re.split(r"\n- (?:\[\d+\] )?(?:AX)?MenuBar", data.get("tree_markdown", ""))[0]
        clean["element_count"] = len(elements)
    if mode != "tree":
        for block in raw.get("content", []):
            if block.get("type") == "image":
                images.append(Image(block["data"], block.get("mimeType", "image/png")))
    if mode == "vision" and not images:
        return ToolResult("No screenshot returned. Check screen recording permissions. No accessibility fallback is allowed in vision mode.", is_error=True)
    if mode == "tree" and not data.get("elements") and not data.get("tree_markdown"):
        return ToolResult("No accessibility elements returned. This app may not expose a tree. No image fallback is allowed in tree mode.", is_error=True)
    if mode == "hybrid" and (not images or not (data.get("elements") or data.get("tree_markdown"))):
        clean["observation_warning"] = "Hybrid observation is incomplete; report the missing modality."
    return ToolResult(json.dumps(clean, ensure_ascii=False), images)
