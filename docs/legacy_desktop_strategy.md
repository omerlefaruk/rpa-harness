# Legacy Desktop Strategy

Old desktop apps may expose weak or no UIAutomation tree. The harness should degrade honestly instead of pretending fragile selectors are strong.

## Fallback ladder

1. Attach by process/window/title/class.
2. Stabilize window size, DPI/scaling, theme, language, and starting screen.
3. Try UIA.
4. Try Win32 controls, classes, handles, menus, and command IDs.
5. Prefer menus and keyboard accelerators.
6. Prefer keyboard navigation and clipboard paste/copy.
7. Prefer file import/export or authorized backend/API paths.
8. Use image anchors.
9. Use OCR for verification.
10. Use calibrated relative coordinates only as last resort.

## Reliability levels

- Level 1: API automation.
- Level 2: Browser DOM/accessibility automation.
- Level 3: Desktop UIA/Win32 automation.
- Level 4: Keyboard/menu-driven desktop automation.
- Level 5: Image/OCR anchor automation.
- Level 6: Coordinate automation.

Reports should identify weak steps, required calibration, and verification method.
