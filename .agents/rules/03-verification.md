# Verification Rules

Every workflow step must have `success_check`.

## Rule

A step is successful only when ALL `success_check` entries pass.

Steps missing `success_check` fail validation unless `type: no_op` and `allow_without_success_check: true`.

## Check Types

**Browser**: url_contains, url_equals, visible_text, selector_visible, selector_hidden, field_has_value

**Desktop**: window_exists, element_exists, element_text_equals

**API**: status_code, json_path_equals, response_contains

**Excel**: workbook_exists, sheet_exists, cell_equals

**Generic**: file_exists, variable_has_value, variable_equals, text_contains, always_pass

## Evidence on Failure

- step id, timestamp, error type, error message
- screenshot (browser/desktop)
- DOM snapshot (browser)
- UIA tree snapshot (desktop)
- API response (API)
- input row id (Excel)

## Anti-Patterns

- Removing `success_check` to make a run pass
- Weakening verification instead of fixing root cause
- Using `always_pass` for steps with real requirements
- Treating action execution as success
