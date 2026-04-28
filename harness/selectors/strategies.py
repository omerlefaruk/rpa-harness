"""
Selector strategy module — priority ladder for robust element selection.
Adapted from CasareRPA selector-strategies skill patterns.
"""

import re
from typing import List, Optional, Tuple


SELECTOR_PRIORITY = [
    ("data-testid", "data-testid='{}'", 5),
    ("data-test", "data-test='{}'", 5),
    ("data-qa", "data-qa='{}'", 5),
    ("aria-label", "[aria-label='{}']", 4),
    ("name", "[name='{}']", 4),
    ("role + accessible name", "[role='{}'][aria-label='{}']", 4),
    ("id", "#{}", 3),
    ("text contains", ":has-text('{}')", 3),
    ("placeholder", "[placeholder='{}']", 3),
    ("CSS class (specific)", ".{}", 2),
    ("tag + text", "{}:has-text('{}')", 2),
    ("button text", "button:has-text('{}')", 2),
    ("link text", "a:has-text('{}')", 2),
    ("CSS class (partial)", "[class*='{}']", 1),
    ("generic XPath", "//*[contains(text(), '{}')]", 1),
    ("generic tag", "{}", 1),
]

ELEMENT_SYNONYMS = {
    "button": ["btn", "click", "submit", "action"],
    "input": ["textbox", "field", "entry", "text"],
    "dropdown": ["select", "combo", "picker", "menu"],
    "link": ["anchor", "hyperlink", "navigation"],
    "checkbox": ["check", "toggle", "switch"],
    "table": ["grid", "datagrid", "spreadsheet"],
    "dialog": ["modal", "popup", "window", "overlay"],
    "tab": ["panel", "section", "pane"],
}


def generate_selector_variations(element_description: str, element_type: str = "element") -> List[str]:
    variations = []

    name = element_description.strip().lower()
    name_original = element_description.strip()

    # Find synonyms for the element type
    synonyms = ELEMENT_SYNONYMS.get(element_type, [element_type])

    for strategy_name, template, priority in SELECTOR_PRIORITY:
        if priority < 3:
            continue

        if "role" in strategy_name:
            for syn in synonyms:
                variations.append(template.format(syn, name_original))
        elif "tag" in strategy_name:
            for syn in synonyms:
                variations.append(template.format(syn, name_original))
        elif "{}" in template:
            variations.append(template.format(name_original))
            variations.append(template.format(name))

    variations = list(dict.fromkeys(variations))
    variations.sort(key=lambda s: len(s), reverse=True)

    return variations


def get_healing_ladder(original_selector: str) -> List[str]:
    ladder = []

    sel = original_selector.strip()

    if sel.startswith("#"):
        clean = sel[1:]
        ladder.extend([
            f"[id='{clean}']",
            f"[data-testid='{clean}']",
            f"[name='{clean}']",
            f"[aria-label='{clean}']",
        ])

    if sel.startswith("[") or sel.startswith("."):
        clean = sel.lstrip("#.[]")
        parts = clean.split("=")
        if len(parts) > 1:
            val = parts[1].strip("'\" ").rstrip("']")
            ladder.extend([
                f"[data-testid='{val}']",
                f"[aria-label='{val}']",
                f"[name='{val}']",
            ])

    if "has-text" not in sel:
        ladder.append(f":has-text('{sel}')")
        ladder.append(f"text={sel}")

    ladder.extend([
        f"//*[contains(@id, '{sel}')]",
        f"//*[contains(@class, '{sel}')]",
        f"//*[contains(text(), '{sel}')]",
    ])

    return list(dict.fromkeys(ladder))


def score_selector(selector: str) -> int:
    normalized = selector.strip()

    if any(key in normalized for key in ("data-testid", "data-test", "data-qa")):
        return 5
    if normalized.startswith("[aria-label=") or normalized.startswith("[name="):
        return 4
    if normalized.startswith("[role="):
        return 4
    if is_dynamic_selector(normalized):
        return 1
    if normalized.startswith("#"):
        return 3
    if normalized.startswith("[placeholder="):
        return 3
    if normalized.startswith("text=") or ":has-text(" in normalized:
        return 3
    if re.match(r"^\.[A-Za-z0-9_-]+$", normalized):
        return 2
    if normalized.startswith("xpath=") or normalized.startswith("//"):
        return 1
    if normalized:
        return 2
    return 1


def is_dynamic_selector(selector: str) -> bool:
    patterns = [
        r'[a-f0-9]{8,}',  # long hex strings
        r'(?:emotion|styled|css)-[a-z0-9]+',  # CSS-in-JS
        r'__\w+_\d+',  # BEM mutations
        r':nth-',  # positional
        r':first',  # positional
    ]
    return any(re.search(p, selector) for p in patterns)


def suggest_better_selector(selector: str, element_type: str = "element") -> Optional[str]:
    if is_dynamic_selector(selector):
        return f"[data-testid='{element_type}']"
    return None
