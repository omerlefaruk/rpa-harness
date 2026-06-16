# Legacy Desktop Strategy

Use the most deterministic path available:

1. API or file import/export when authorized.
2. UIAutomation controls.
3. Win32 handles, class names, captions, and menu ids.
4. Menus and keyboard accelerators.
5. Clipboard paste/copy instead of slow typing.
6. Image anchors with OCR verification.
7. Calibrated relative coordinates.

Legacy app steps that rely on image/OCR or coordinates must say so:

```yaml
selector_quality: weak
required_calibration:
  - fixed resolution
  - fixed DPI
  - stable theme
```

If no reliable UIA, Win32, keyboard, image, OCR, or file/API path exists, stop with a blocked discovery result and attach evidence. Do not invent reliable selectors.

Reliability levels:

- Level 1: API automation
- Level 2: Browser DOM/accessibility automation
- Level 3: Desktop UIA/Win32 automation
- Level 4: Keyboard/menu-driven desktop automation
- Level 5: Image/OCR anchor automation
- Level 6: Coordinate automation
