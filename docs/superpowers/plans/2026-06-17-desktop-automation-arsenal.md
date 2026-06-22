# Desktop Automation Arsenal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give `rpa-harness` a practical desktop automation arsenal for UIA, Win32, keyboard/menu, clipboard, OCR, evidence storage/server access, governed AI assistance, and last-resort visual/coordinate fallbacks.

**Architecture:** Extend the existing desktop path instead of adding a parallel automation system. UIA remains the default backend; Win32 is a fallback backend selected by selector/backend metadata; OCR, clipboard, AI assistance, image, and coordinates are governed capabilities with explicit success checks, policy gates, and evidence capture.

**Tech Stack:** Python, pytest, pywinauto, pywin32, PIL/ImageGrab, sqlite3, existing dashboard/reporting/evidence code, OCR command integration.

---

## File Structure

- Modify: `harness/verification/contract.py`
  - Own the public desktop action contract and validation.
- Modify: `harness/rpa/yaml_runner.py`
  - Route new desktop YAML actions to existing drivers.
- Modify: `harness/rpa/schema.py`
  - Classify selector quality and reliability levels for desktop fallbacks.
- Modify: `harness/drivers/windows_ui.py`
  - Expose already-present UIA capabilities cleanly to YAML: attach, type, press, wait, screenshot, dump tree.
- Create: `harness/drivers/win32_ui.py`
  - Minimal pywin32 fallback: attach, dump tree, find, click, get text.
- Create: `tools/dump_win32_tree.py`
  - Standalone Win32 inspection artifact generator.
- Modify: `harness/builder.py`
  - Make desktop capture produce UIA/Win32/screenshot evidence when available.
- Modify: `harness/reporting/failure_report.py`
  - Link Win32 tree and desktop screenshots in failure reports.
- Modify: `harness/observability.py`
  - Persist desktop evidence paths and weak-step metadata in the existing SQLite store.
- Modify: `harness/reporting/dashboard.py`
  - Expose desktop evidence through the existing local dashboard server.
- Create: `harness/desktop/__init__.py`
  - Package desktop-specific helpers.
- Create: `harness/desktop/clipboard.py`
  - Safe clipboard paste helper that restores prior clipboard content.
- Create: `harness/desktop/ocr.py`
  - OCR command wrapper for screenshots/regions with explicit blocked output when unavailable.
- Create: `harness/desktop/ai_controller.py`
  - Governed AI desktop assist loop that can inspect/propose/repair and execute only approved deterministic actions.
- Modify: `docs/legacy_desktop_strategy.md`
  - Document the implemented ladder and weak-step rules.
- Test: `tests/capabilities/test_desktop_action_contract.py`
- Test: `tests/capabilities/test_desktop_win32_tools.py`
- Test: `tests/capabilities/test_desktop_clipboard_ocr.py`
- Test: `tests/capabilities/test_desktop_ai_controller.py`
- Test: `tests/capabilities/test_desktop_evidence_store.py`
- Test: `tests/capabilities/test_yaml_excel_desktop_runtime.py`
- Test: `tests/integration/test_windows_desktop_smoke.py`

---

### Task 1: Freeze The Desktop Action Contract

**Files:**
- Modify: `harness/verification/contract.py`
- Modify: `harness/rpa/schema.py`
- Test: `tests/capabilities/test_desktop_action_contract.py`

- [ ] **Step 1: Add the failing contract test**

```python
def test_desktop_action_contract_has_practical_arsenal():
    from harness.verification.contract import DESKTOP_ACTIONS

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
```

Run: `pytest tests/capabilities/test_desktop_action_contract.py -q`

- [ ] **Step 2: Add only those actions to `DESKTOP_ACTIONS`**

Keep the set explicit. No wildcard desktop actions.

- [ ] **Step 3: Validate required fields**

Add validation rules:

- `desktop.attach` requires `window_title` or `class_name`
- `desktop.type` requires `text`; selector optional only when global input fallback is explicitly enabled
- `desktop.clipboard_paste` requires `text` or `secret`
- `desktop.press` requires `keys`
- `desktop.menu_select` requires `path`
- `desktop.wait` requires `selector`, `window_title`, or `text`
- `desktop.ocr_read` requires `selector`, `region`, or `screenshot`
- `desktop.ocr_wait` requires `text` and `selector`, `region`, or `screenshot`
- `desktop.screenshot` has no required target
- `desktop.dump_tree` has no required target

- [ ] **Step 4: Classify selector quality**

Update `harness/rpa/schema.py` so:

- `automation_id`, `name+control_type`, `win32_control_id` are strong/medium
- `class_name`, `class_name+control_type`, `tree_path` are medium/weak
- `image` is weak
- `ocr` is weak
- `coordinate` is `coordinate_fallback`

- [ ] **Step 5: Run focused validation**

Run:

```bash
pytest tests/capabilities/test_desktop_action_contract.py tests/test_workflow_schema.py -q
```

Expected: pass.

---

### Task 2: Add Win32 Discovery Without Runtime Risk

**Files:**
- Create: `tools/dump_win32_tree.py`
- Test: `tests/capabilities/test_desktop_win32_tools.py`

- [ ] **Step 1: Add a mocked Win32 dump test**

The output shape must be stable:

```python
def test_dump_win32_tree_output_shape():
    result = {
        "status": "ok",
        "backend": "win32",
        "window": {"title": "Untitled - Notepad", "class_name": "Notepad"},
        "elements": [
            {
                "hwnd": 1001,
                "text": "Edit",
                "class_name": "Edit",
                "control_id": 15,
                "rect": [0, 0, 500, 300],
            }
        ],
    }

    assert result["backend"] == "win32"
    assert {"hwnd", "text", "class_name", "control_id", "rect"}.issubset(result["elements"][0])
```

- [ ] **Step 2: Implement `tools/dump_win32_tree.py`**

Use only stdlib plus `pywin32`:

- `win32gui.EnumWindows`
- `win32gui.EnumChildWindows`
- `win32gui.GetWindowText`
- `win32gui.GetClassName`
- `win32gui.GetWindowRect`
- `win32gui.GetDlgCtrlID`

Non-Windows output:

```json
{"status":"skipped","reason":"Windows only - pywin32 required"}
```

- [ ] **Step 3: Run the tool test**

Run: `pytest tests/capabilities/test_desktop_win32_tools.py -q`

Expected: pass on non-Windows and Windows.

---

### Task 3: Expose Existing UIA Driver Capabilities In YAML

**Files:**
- Modify: `harness/drivers/windows_ui.py`
- Modify: `harness/rpa/yaml_runner.py`
- Test: `tests/capabilities/test_yaml_excel_desktop_runtime.py`

- [ ] **Step 1: Add fake-driver YAML tests**

Cover:

- `desktop.attach`
- `desktop.type`
- `desktop.press`
- `desktop.wait`
- `desktop.screenshot`
- `desktop.dump_tree`

The tests should use a fake desktop driver so they run without Windows.

- [ ] **Step 2: Add `_execute_desktop_action` cases**

Map actions to existing driver methods:

- `desktop.attach` -> `connect_to_app`
- `desktop.type` -> `type_keys`
- `desktop.press` -> `press_keys`
- `desktop.wait` -> `find_element` or `connect_to_app`
- `desktop.screenshot` -> `screenshot`
- `desktop.dump_tree` -> `dump_tree`

- [ ] **Step 3: Keep coordinate fallback gated**

Only allow `selector.strategy: coordinate` if `config.allow_coordinate_fallback` is true. Return selector quality as `coordinate_fallback`.

- [ ] **Step 4: Run focused tests**

Run:

```bash
pytest tests/capabilities/test_yaml_excel_desktop_runtime.py tests/capabilities/test_desktop_action_contract.py -q
```

Expected: pass.

---

### Task 4: Add Minimal Win32 Runtime Fallback

**Files:**
- Create: `harness/drivers/win32_ui.py`
- Modify: `harness/rpa/yaml_runner.py`
- Test: `tests/capabilities/test_yaml_excel_desktop_runtime.py`

- [ ] **Step 1: Add fake Win32 driver tests**

Supported selector strategies:

- `win32_control_id`
- `hwnd`
- `class_name+name`
- `class_name+control_type`

Workflow syntax:

```yaml
selector:
  backend: win32
  strategy: win32_control_id
  value: "15"
```

- [ ] **Step 2: Implement `Win32UIDriver`**

Keep the API tiny:

- `connect_to_app(title=None, class_name=None, timeout=10)`
- `dump_tree(max_depth=3)`
- `find_element(...)`
- `click(...)`
- `get_text(...)`
- `close_app()`

Use `SendMessage`/`BM_CLICK` only for known button controls. For generic clicks, use calibrated center-of-rect input and mark it weak.

- [ ] **Step 3: Route backend selection**

In `YamlWorkflowRunner`, choose Win32 when:

- `action.backend == "win32"`
- or `selector.backend == "win32"`
- or selector strategy starts with `win32_`

Default stays UIA.

- [ ] **Step 4: Run focused tests**

Run:

```bash
pytest tests/capabilities/test_yaml_excel_desktop_runtime.py -q
```

Expected: pass.

---

### Task 5: Builder Capture Artifacts

**Files:**
- Modify: `harness/builder.py`
- Modify: `harness/reporting/failure_report.py`
- Test: `tests/test_workflow_schema.py`

- [ ] **Step 1: Extend desktop capture output**

`python main.py --capture-desktop "Legacy ERP" --capture-session-dir builder_sessions/x` should write:

- `task_spec.md`
- `assumptions.md`
- `discovery_session.json`
- `uia_tree.json` when UIA is available
- `win32_tree.json` when pywin32 is available
- `screenshot.png` when desktop screenshot is available
- `unresolved_risks.md`

- [ ] **Step 2: Keep blocked output honest**

If evidence cannot be captured, write a blocked discovery result. Do not invent selectors.

- [ ] **Step 3: Link desktop artifacts in failure reports**

Failure report evidence keys:

- `uia_tree`
- `win32_tree`
- `screenshot`
- `desktop.window_title`
- `desktop.backend`
- `desktop.selector_quality`

- [ ] **Step 4: Run focused tests**

Run:

```bash
pytest tests/test_workflow_schema.py tests/capabilities/test_reporting_evidence.py -q
```

Expected: pass.

---

### Task 6: Keyboard And Menu Fallback

**Files:**
- Modify: `harness/drivers/windows_ui.py`
- Modify: `harness/drivers/win32_ui.py`
- Modify: `harness/rpa/yaml_runner.py`
- Test: `tests/capabilities/test_yaml_excel_desktop_runtime.py`

- [ ] **Step 1: Add `desktop.menu_select` tests**

Workflow syntax:

```yaml
action:
  type: desktop.menu_select
  path: "File->Save As"
success_check:
  - type: window_exists
    value: "Save As"
```

- [ ] **Step 2: Implement menu select**

UIA path:

- call pywinauto `window.menu_select(path)` when a window is attached

Win32 path:

- use menu handles only when available
- otherwise fail with a clear unsupported message

- [ ] **Step 3: Use clipboard paste as an explicit action only**

Clipboard paste is allowed through `desktop.clipboard_paste`, not as a hidden fallback inside `desktop.type`.

Workflow syntax:

```yaml
action:
  type: desktop.clipboard_paste
  selector:
    strategy: automation_id
    value: "notesField"
  text: "${inputs.notes}"
success_check:
  - type: text_contains
    value: "${inputs.notes}"
```

The implementation must save the previous clipboard value, paste the requested value, then restore the previous clipboard value before returning.

---

### Task 7: Weak Visual And Coordinate Fallbacks

**Files:**
- Modify: `harness/rpa/yaml_runner.py`
- Modify: `harness/rpa/schema.py`
- Modify: `docs/legacy_desktop_strategy.md`
- Test: `tests/capabilities/test_desktop_action_contract.py`

- [ ] **Step 1: Support coordinate selector only behind config**

Workflow syntax:

```yaml
selector:
  strategy: coordinate
  value:
    x_ratio: 0.42
    y_ratio: 0.71
    anchor: window
```

Rules:

- absolute screen coordinates are rejected
- ratio coordinates require a window rect
- the step must have a success check

- [ ] **Step 2: Add OCR runtime as a weak verified action**

Workflow syntax:

```yaml
action:
  type: desktop.ocr_read
  region:
    anchor: window
    x_ratio: 0.1
    y_ratio: 0.2
    width_ratio: 0.8
    height_ratio: 0.2
  output: status_text
success_check:
  - type: text_contains
    value: "Ready"
```

OCR is weak. Every OCR action must save the screenshot/region used and must have a success check.

- [ ] **Step 3: Document weak-step reporting**

Every weak fallback report must say:

- fallback type
- calibration basis
- screenshot artifact
- verification method

---

### Task 8: Windows Smoke Matrix

**Files:**
- Create: `tests/integration/test_windows_desktop_smoke.py`

- [ ] **Step 1: Add Windows-only Calculator UIA smoke**

Skip unless `sys.platform.startswith("win")`.

Proof:

- launch Calculator
- click `num2Button`
- click `plusButton`
- click `num2Button`
- click `equalButton`
- read `CalculatorResults`
- assert contains `4`

- [ ] **Step 2: Add Windows-only Notepad keyboard/menu smoke**

Proof:

- launch Notepad
- type `rpa-harness smoke`
- press `ctrl+a`
- get text or copy/read local evidence where possible
- close without saving

- [ ] **Step 3: Add Win32 dump manual command**

Document:

```bash
python tools/dump_win32_tree.py --window-title "Notepad" --max-depth 3
python tools/dump_uia_tree.py --window-title "Notepad" --max-depth 3
```

- [ ] **Step 4: Run full focused suite**

Run:

```bash
pytest tests/capabilities/test_desktop_action_contract.py tests/capabilities/test_desktop_win32_tools.py tests/capabilities/test_yaml_excel_desktop_runtime.py -q
```

On Windows, also run:

```bash
pytest tests/integration/test_windows_desktop_smoke.py -q
```

Expected: pass or explicit Windows-only skip.

---

### Task 9: Safe Clipboard Paste Runtime

**Files:**
- Create: `harness/desktop/__init__.py`
- Create: `harness/desktop/clipboard.py`
- Modify: `harness/rpa/yaml_runner.py`
- Test: `tests/capabilities/test_desktop_clipboard_ocr.py`

- [ ] **Step 1: Add clipboard unit tests**

Test cases:

- pastes requested text through `ctrl+v`
- restores previous clipboard text after success
- restores previous clipboard text after failure
- redacts secret values in result payloads and errors

Minimal test shape:

```python
def test_clipboard_restore_after_paste(fake_clipboard):
    from harness.desktop.clipboard import ClipboardPaste

    fake_clipboard.set_text("before")
    paste = ClipboardPaste(clipboard=fake_clipboard, send_hotkey=lambda keys: None)

    paste.paste_text("new value")

    assert fake_clipboard.get_text() == "before"
```

- [ ] **Step 2: Implement `ClipboardPaste`**

Use `win32clipboard` on Windows. On non-Windows, return a clear blocked error. Keep the helper small:

- `get_text()`
- `set_text(value)`
- `paste_text(value)`
- `restore()`

- [ ] **Step 3: Wire `desktop.clipboard_paste`**

In `YamlWorkflowRunner._execute_desktop_action`, focus the selector when present, paste the text, and return:

```python
{
    "clipboard_paste": True,
    "selector_visible": True,
    "secret_redacted": True,
}
```

- [ ] **Step 4: Run focused tests**

Run:

```bash
pytest tests/capabilities/test_desktop_clipboard_ocr.py tests/capabilities/test_yaml_excel_desktop_runtime.py -q
```

Expected: pass.

---

### Task 10: OCR Runtime

**Files:**
- Create: `harness/desktop/ocr.py`
- Modify: `harness/rpa/yaml_runner.py`
- Modify: `harness/reporting/failure_report.py`
- Test: `tests/capabilities/test_desktop_clipboard_ocr.py`

- [ ] **Step 1: Add OCR wrapper tests**

Test cases:

- returns blocked result when OCR command is not configured
- redacts OCR text before reports when secret canaries appear
- writes screenshot/region artifact path into action result
- supports `desktop.ocr_read` and `desktop.ocr_wait`

Minimal blocked-result assertion:

```python
def test_ocr_without_command_is_blocked(tmp_path):
    from harness.desktop.ocr import OcrEngine

    result = OcrEngine(command=None).read_image(tmp_path / "missing.png")

    assert result["status"] == "blocked"
    assert "OCR command is not configured" in result["reason"]
```

- [ ] **Step 2: Implement command-backed OCR**

Use an explicit command from config/env, for example `RPA_OCR_COMMAND`. The command receives an image path and returns text on stdout.

Do not bundle a hidden cloud OCR call. If no command is configured, produce a blocked result.

- [ ] **Step 3: Wire YAML actions**

`desktop.ocr_read`:

- capture screenshot or crop configured region
- run OCR command
- store output
- return `text`, `ocr_text`, `screenshot`, `region`

`desktop.ocr_wait`:

- repeat OCR until expected text appears or timeout expires
- write every attempt to timeline/evidence

- [ ] **Step 4: Run focused tests**

Run:

```bash
pytest tests/capabilities/test_desktop_clipboard_ocr.py -q
```

Expected: pass.

---

### Task 11: Desktop Evidence Database And Local Server Access

**Files:**
- Modify: `harness/observability.py`
- Modify: `harness/reporting/dashboard.py`
- Modify: `harness/reporting/failure_report.py`
- Test: `tests/capabilities/test_desktop_evidence_store.py`
- Test: `tests/test_dashboard.py`

- [ ] **Step 1: Add evidence storage tests**

Expected persisted fields:

- run id
- step id
- backend: `uia`, `win32`, `ocr`, `image`, `coordinate`
- selector quality
- screenshot path
- UIA tree path
- Win32 tree path
- OCR artifact path
- weak-step reason
- verification method

- [ ] **Step 2: Extend the existing SQLite schema**

Add nullable desktop evidence columns to the existing observability database. Keep raw artifacts on disk; store paths and redacted summaries in SQLite.

- [ ] **Step 3: Add local dashboard endpoints**

Expose read-only local endpoints:

- `GET /api/desktop/evidence?run_id=...`
- `GET /api/desktop/evidence/<evidence_id>`

Responses must not inline screenshots or raw OCR text containing canaries. Return artifact paths and redacted previews.

- [ ] **Step 4: Run focused tests**

Run:

```bash
pytest tests/capabilities/test_desktop_evidence_store.py tests/test_dashboard.py -q
```

Expected: pass.

---

### Task 12: Governed AI Desktop Controller

**Files:**
- Create: `harness/desktop/ai_controller.py`
- Modify: `main.py`
- Modify: `harness/builder.py`
- Test: `tests/capabilities/test_desktop_ai_controller.py`

- [ ] **Step 1: Add controller policy tests**

The controller must refuse to execute when:

- no discovery evidence exists
- proposed action is not in the desktop contract
- action has no success check
- action is external write/destructive without approval
- selector is coordinate/image/OCR without weak-step metadata

Minimal test shape:

```python
def test_ai_controller_rejects_action_without_success_check():
    from harness.desktop.ai_controller import DesktopAIController

    controller = DesktopAIController(policy={"allow_execute": True})
    result = controller.validate_proposal({"type": "desktop.click", "selector": {"strategy": "name", "value": "Submit"}})

    assert result["status"] == "blocked"
    assert "success_check" in result["reason"]
```

- [ ] **Step 2: Implement controller modes**

Modes:

- `inspect`: read UIA/Win32/screenshot/OCR evidence and propose selectors
- `draft`: create deterministic YAML steps
- `repair`: propose replacement selectors from failure evidence
- `execute-approved`: execute only validated deterministic actions with success checks

No free-form desktop control mode.

- [ ] **Step 3: Add CLI entrypoint**

Add:

```bash
python main.py --desktop-ai-assist builder_sessions/<SESSION_ID> --mode inspect
python main.py --desktop-ai-assist builder_sessions/<SESSION_ID> --mode execute-approved
```

`execute-approved` requires an approved proposal file in the session directory.

- [ ] **Step 4: Store AI decisions as evidence**

Write:

- `ai_desktop_proposals.json`
- `ai_desktop_policy_decision.json`
- `ai_desktop_repair_packet.md`

All outputs must be redacted before persistence.

- [ ] **Step 5: Run focused tests**

Run:

```bash
pytest tests/capabilities/test_desktop_ai_controller.py tests/test_authoring_reporting.py -q
```

Expected: pass.

---

## Execution Order

1. Task 1: contract first.
2. Task 2: Win32 discovery tool.
3. Task 3: UIA YAML runtime basics.
4. Task 4: Win32 runtime fallback.
5. Task 5: builder/reporting evidence.
6. Task 6: keyboard/menu fallback.
7. Task 7: coordinate and visual guardrails.
8. Task 8: Windows smoke proof.
9. Task 9: clipboard paste.
10. Task 10: OCR runtime.
11. Task 11: evidence database and local server access.
12. Task 12: governed AI desktop controller.

## Guardrails

- No capability in this plan is skipped.
- AI assistance is allowed, but only through inspect/draft/repair/execute-approved modes.
- Clipboard and OCR are production actions, but they are explicit actions with success checks.
- Evidence is stored in the existing SQLite/reporting path; raw secrets are never stored.
