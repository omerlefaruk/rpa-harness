---
name: windows-ui-automation
description: >
  Windows desktop automation using pywinauto UIA backend.
  Launch apps, walk UIA element trees, discover element names and automation IDs,
  interact with desktop UI elements. Use when automating Windows desktop applications.
hooks: "preflight, compliance, validation, reporting, memory-save, memory-search"
---

# Windows UI Automation

## Pattern: Discover → Select → Act

1. **Attach to window**: Connect by title or class name
2. **Dump tree**: Use `dump_tree(max_depth=3)` to discover elements
3. **Select by stable attribute**: automation_id > name > class_name
4. **Act**: click, type_keys, get_text

## Element Discovery

```python
driver = WindowsUIDriver(config=config)
await driver.launch_app("notepad.exe")

# Dump tree to discover elements
tree = await driver.dump_tree(max_depth=3)

# Find by automation_id (most stable)
await driver.click(automation_id="fileMenu")

# Find by name fallback
await driver.click(name="Save")
```

## Scripts

- `scripts/dump_uia_tree.py` — Full UIA tree dump with filtering
- `scripts/find_element.py` — Search by name/auto_id/class with timeout
- `scripts/validate_selector.py` — Test if a UIA selector works reliably
