# Selector Strategy

Browser selector priority:

1. `data-testid`
2. role and accessible name
3. label
4. placeholder
5. visible text
6. stable id
7. CSS
8. XPath

Desktop selector priority:

1. `automation_id`
2. name and control type
3. class name and control type
4. tree path
5. image anchor
6. coordinate fallback

Coordinates are last resort. XPath, image, OCR, and coordinates are weak unless backed by stable context and explicit success checks.

Selector evidence should answer:

- What selector failed?
- What candidates were found?
- Why were candidates ranked?
- Which artifact proves the current page/window state?
- Was the candidate validated before use?

Runtime should not silently auto-apply selector repairs in production. Patch the workflow, rerun validation, then rerun the relevant phase or record.

Production repair command:

```bash
python main.py --repair-selector RUN_ID
python main.py --repair-selector RUN_ID --repair-approve
```

The command applies a selector only when repair evidence contains a validated structured candidate and `--repair-approve` is present. Without both, it writes `selector_repair_decision.json` and blocks.
