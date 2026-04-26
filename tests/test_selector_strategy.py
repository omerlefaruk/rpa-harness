"""Tests for selector strategies."""
from harness.selectors.strategies import (
    SELECTOR_PRIORITY,
    generate_selector_variations,
    get_healing_ladder,
    score_selector,
    is_dynamic_selector,
)


def test_selector_priority_ordering():
    scores = [p for _, _, p in SELECTOR_PRIORITY]
    assert scores == sorted(scores, reverse=True)
    assert scores[0] == 5


def test_generate_variations():
    variations = generate_selector_variations("login", "button")
    assert len(variations) > 0
    assert any("login" in v.lower() for v in variations)


def test_healing_ladder():
    ladder = get_healing_ladder("#submit-btn")
    assert len(ladder) > 0


def test_score_selector():
    css_testid = score_selector("[data-testid='submit']")
    aria_label = score_selector("[aria-label='Close']")
    css_id = score_selector("#my-id")
    assert css_testid >= 1
    assert aria_label >= 1
    assert css_id >= 1


def test_is_dynamic():
    assert is_dynamic_selector("div:nth-child(3)")
    assert is_dynamic_selector(".css-abc123def")
    assert not is_dynamic_selector("[data-testid='stable']")
