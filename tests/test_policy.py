import pytest
from common.core.policy import filter_result, prepare_arguments, tools_for_mode
from common.core.types import ToolSpec


def observation():
    return {"content": [{"type": "image", "data": "aW1hZ2U=", "mimeType": "image/png"},
                        {"type": "text", "text": "RAW_TREE_SECRET"}],
            "structuredContent": {"pid": 1, "window_id": 2, "capture_id": "capture",
                                  "elements": [{"role": "AXButton", "label": "TREE_SECRET"},
                                               {"role": "AXMenuBar"}, {"label": "PRIVATE_RECENT"}],
                                  "tree_markdown": '- AXWindow\n  - TREE_SECRET\n- AXMenuBar\n  - PRIVATE_RECENT',
                                  "unknown_future_field": "SECRET"}}


@pytest.mark.parametrize("mode,images,tree", [("vision", True, False), ("tree", False, True), ("hybrid", True, True)])
def test_observation_isolation(mode, images, tree):
    args = prepare_arguments("get_window_state", {"pid": 1, "window_id": 2}, mode)
    assert args["include_screenshot"] == images
    assert args["include_accessibility_tree"] == tree
    result = filter_result("get_window_state", observation(), mode)
    assert bool(result.images) == images
    assert ("TREE_SECRET" in result.text) == tree
    assert "PRIVATE_RECENT" not in result.text
    assert "unknown_future_field" not in result.text
    assert "RAW_TREE_SECRET" not in result.text


def test_other_tool_results_do_not_leak_observations():
    for mode in ["vision", "tree", "hybrid"]:
        result = filter_result("click", observation(), mode)
        assert not result.images
        assert "SECRET" not in result.text


def test_schemas_remove_bypass_routes():
    native = [ToolSpec("get_window_state", "", {"type": "object", "properties": {
        "pid": {"type": "integer"}, "window_id": {"type": "integer"},
        "include_accessibility_tree": {"type": "boolean"}, "screenshot_out_file": {"type": "string"}}}),
        ToolSpec("browser_evaluate", "", {}), ToolSpec("bash", "", {}), ToolSpec("click", "", {"properties": {
            "element_token": {"type": "string"}, "x": {"type": "number"}}})]
    vision = tools_for_mode(native, "vision")
    assert [s.name for s in vision] == ["get_window_state", "click"]
    assert "include_accessibility_tree" not in vision[0].parameters["properties"]
    assert "element_token" not in vision[1].parameters["properties"]
    assert vision[0].parameters["additionalProperties"] is False


def test_missing_modality_does_not_fall_back():
    raw = observation()
    raw["content"] = []
    assert filter_result("get_window_state", raw, "vision").is_error
    raw["structuredContent"] = {}
    assert filter_result("get_window_state", raw, "tree").is_error


def test_action_refusal_and_unconfirmed_delivery_are_preserved():
    assert filter_result("click", {"structuredContent": {"effect": "refused"}}, "vision").is_error
    raw = {"structuredContent": {"effect": "unverifiable", "route": "synthetic_events",
                                "escalation": {"target": "foreground"}, "summary": "TREE_SECRET"}}
    result = filter_result("click", raw, "vision")
    assert "unverifiable" in result.text and "foreground" in result.text
    assert "TREE_SECRET" not in result.text
