# Verification Contract

Every automation step must prove success. An action executing does not mean it succeeded.

## Rule

A step is successful only when ALL its `success_check` entries pass.

Missing `success_check` fails validation unless the step is `type: no_op` and explicitly sets `allow_without_success_check: true`.

## Supported Check Types

### Browser
| Type | Description | Example value |
|------|-------------|---------------|
| `url_contains` | Current URL contains string | `"/dashboard"` |
| `url_equals` | Current URL matches exactly | `"https://example.com/dashboard"` |
| `visible_text` | Text is visible on page | `"Welcome"` |
| `selector_visible` | Element is visible | selector object |
| `selector_hidden` | Element is not visible | selector object |
| `field_has_value` | Input field has value | selector object + redacted flag |
| `download_exists` | Downloaded file exists | `"report.pdf"` |

### Desktop (Windows UIA)
| Type | Description | Example value |
|------|-------------|---------------|
| `window_exists` | Target window exists | `"Calculator"` |
| `element_exists` | Element found in tree | selector object |
| `element_text_equals` | Element text matches | `"4"` |

### API
| Type | Description | Example value |
|------|-------------|---------------|
| `status_code` | Response status matches | `200` |
| `json_path_equals` | JSON path has value | `{"path": "$.status", "value": "ok"}` |
| `response_contains` | Response body contains text | `"success"` |

### Excel
| Type | Description | Example value |
|------|-------------|---------------|
| `workbook_exists` | Output file exists | `"./output.xlsx"` |
| `sheet_exists` | Sheet exists in workbook | `"Results"` |
| `cell_equals` | Cell value matches | `{"cell": "A1", "value": "OK"}` |

### Generic
| Type | Description | Example value |
|------|-------------|---------------|
| `file_exists` | File exists at path | `"./output/report.pdf"` |
| `variable_has_value` | Variable is not empty/null | `"result_text"` |
| `variable_equals` | Variable equals expected | `{"var": "status", "value": "success"}` |
| `text_contains` | Text contains substring | `"successfully"` |
| `always_pass` | Explicit no-op check | `true` |

## Failure Evidence

Every failed check must capture:
- step id
- timestamp
- error type
- error message
- screenshot (browser/desktop)
- DOM snapshot (browser)
- UIA tree snapshot (desktop)
- input row id (Excel workflows)
- current app/page state

## Anti-Patterns

- Removing `success_check` to make a run pass
- Weakening verification instead of fixing the root cause
- Using `always_pass` for steps that have real requirements
