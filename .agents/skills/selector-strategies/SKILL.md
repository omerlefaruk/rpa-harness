---
name: selector-strategies
description: >
  CSS/XPath selector best practices for web automation.
  Priority ladder, dynamic element handling, anti-patterns.
  Use when writing selectors, handling dynamic content,
  or debugging selector failures.
hooks: "preflight, compliance, reporting"
---

# Selector Strategies

## Priority Order

| Attribute | Stability | Notes |
|-----------|-----------|-------|
| `data-testid` | ★★★★★ | Made for testing |
| `aria-label` | ★★★★☆ | Accessibility, rarely changes |
| `name` | ★★★★☆ | Form inputs, stable |
| `id` | ★★★☆☆ | Can be dynamic |
| `class` | ★★☆☆☆ | Changes with CSS refactors |

## Anti-Patterns

```
NEVER: div:nth-child(3)     # Brittle
NEVER: .button:first         # Order-dependent
NEVER: #react-root-12345     # Dynamic ID
NEVER: [class*="active"]     # Too broad
```
