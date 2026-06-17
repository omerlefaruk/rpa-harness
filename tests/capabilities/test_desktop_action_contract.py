from harness.rpa.schema import _selector_quality
from harness.verification import validate_workflow
from harness.verification.contract import DESKTOP_ACTIONS


def _desktop_step(action: dict) -> dict:
    return {
        "id": "desktop_contract",
        "name": "Desktop Contract",
        "version": "1.0",
        "type": "desktop",
        "steps": [
            {
                "id": "desktop_step",
                "action": action,
                "success_check": [{"type": "element_exists", "value": "ok"}],
            }
        ],
    }


def test_desktop_action_contract_has_practical_arsenal():
    expected = {
        "desktop.launch",
        "desktop.attach",
        "desktop.click",
        "desktop.type",
        "desktop.clipboard_paste",
        "desktop.press",
        "desktop.menu_select",
        "desktop.wait",
        "desktop.get_text",
        "desktop.ocr_read",
        "desktop.ocr_wait",
        "desktop.screenshot",
        "desktop.dump_tree",
        "desktop.close",
    }

    assert expected.issubset(DESKTOP_ACTIONS)


def test_desktop_action_required_fields_are_validated():
    cases = [
        ({"type": "desktop.attach"}, "requires 'window_title' or 'class_name'"),
        ({"type": "desktop.type"}, "requires 'text'"),
        ({"type": "desktop.clipboard_paste"}, "requires 'text' or 'secret'"),
        ({"type": "desktop.press"}, "requires 'keys'"),
        ({"type": "desktop.menu_select"}, "requires 'path'"),
        ({"type": "desktop.wait"}, "requires selector, 'window_title', or 'text'"),
        ({"type": "desktop.ocr_read"}, "requires selector, 'region', or 'screenshot'"),
        (
            {"type": "desktop.ocr_wait", "region": {"anchor": "window"}},
            "requires 'text'",
        ),
        ({"type": "desktop.ocr_wait", "text": "Ready"}, "requires selector, 'region', or 'screenshot'"),
    ]

    for action, expected in cases:
        errors = validate_workflow(_desktop_step(action))
        assert any(expected in error for error in errors), (action, errors)


def test_desktop_action_required_fields_accept_valid_shapes():
    valid_actions = [
        {"type": "desktop.attach", "window_title": "Legacy ERP"},
        {"type": "desktop.type", "text": "hello"},
        {"type": "desktop.clipboard_paste", "text": "notes"},
        {"type": "desktop.press", "keys": "ctrl+s"},
        {"type": "desktop.menu_select", "path": "File->Save"},
        {"type": "desktop.wait", "text": "Ready"},
        {"type": "desktop.ocr_read", "region": {"anchor": "window"}},
        {"type": "desktop.ocr_wait", "text": "Ready", "region": {"anchor": "window"}},
        {"type": "desktop.screenshot"},
        {"type": "desktop.dump_tree"},
    ]

    for action in valid_actions:
        errors = validate_workflow(_desktop_step(action))
        assert errors == [], (action, errors)


def test_desktop_selector_quality_ladder():
    assert _selector_quality({"selector": {"strategy": "automation_id", "value": "Submit"}}) == "strong"
    assert _selector_quality({"selector": {"strategy": "name+control_type", "name": "OK"}}) == "strong"
    assert _selector_quality({"selector": {"strategy": "win32_control_id", "value": "15"}}) == "medium"
    assert _selector_quality({"selector": {"strategy": "class_name", "value": "Edit"}}) == "medium"
    assert _selector_quality({"selector": {"strategy": "tree_path", "value": "0/1/2"}}) == "weak"
    assert _selector_quality({"selector": {"strategy": "image", "value": "save.png"}}) == "weak"
    assert _selector_quality({"selector": {"strategy": "ocr", "value": "Ready"}}) == "weak"
    assert _selector_quality({"selector": {"strategy": "coordinate", "value": {"x": 1}}}) == "coordinate_fallback"
