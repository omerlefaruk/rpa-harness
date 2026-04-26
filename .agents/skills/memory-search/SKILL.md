---
name: memory-search
description: >
  Search RPA Harness persistent memory for past selectors,
  workflow sessions, error patterns, and cached observations.
  Use 3-layer progressive disclosure: index → context → details.
  Use when searching for previously successful selectors,
  debugging flaky tests with history, or retrieving past session context.
hooks: "preflight, compliance, reporting, memory-search"
---

# Memory Search

## 3-Layer Search

### Layer 1: Index (compact)
`GET /memory/search?q=login+selector&type=selector&limit=5`
Returns: [{type, selector, success_rate}, ...]

### Layer 2: Context
`GET /memory/context/{obs_id}?window=5`
Returns: {session, observation, before[], after[]}

### Layer 3: Details
`POST /memory/observations` with `[id1, id2, ...]`
Returns: Full observation data with screenshots, timing, errors

## Search Types

| Type | What it finds |
|------|--------------|
| `selector` | Cached selectors with success rates |
| `workflow` | Past session observations matching query |
| `error` | Error patterns with recovery strategies |
| `all` | Combined results from all types |

## When to Use

- Before clicking: search for cached selectors for this URL
- Before retrying: check error patterns for recovery strategy
- Before planning: find similar workflows from past sessions
