"""Tests for browser selector swarm candidate generation."""

import pytest

from harness.selectors.browser_swarm import (
    _check_success,
    _css_fallback,
    _failed_request_entry,
    _locator_from_selector,
    _safe_click_candidate,
    generate_selector_candidates,
    prioritize_candidates_for_intent,
    redact_page_map,
)


def test_generate_selector_candidates_prioritizes_testid_and_role():
    elements = [
        {
            "index": 0,
            "tag": "button",
            "role": "button",
            "accessible_name": "Save",
            "text": "Save",
            "data_testid": "submit-button",
            "visible": True,
            "disabled": False,
            "labels": [],
        }
    ]

    candidates = generate_selector_candidates(elements)

    assert candidates[0]["selector"] == {
        "strategy": "data-testid",
        "value": "submit-button",
    }
    assert any(
        candidate["selector"] == {"strategy": "role", "role": "button", "name": "Save"}
        for candidate in candidates
    )


def test_generate_selector_candidates_skips_hidden_elements():
    elements = [
        {
            "index": 0,
            "tag": "button",
            "text": "Hidden",
            "data_testid": "hidden-button",
            "visible": False,
        }
    ]

    assert generate_selector_candidates(elements) == []


def test_generate_selector_candidates_skips_non_actionable_wrappers():
    elements = [
        {
            "index": 0,
            "tag": "div",
            "role": "alert",
            "text": "Error",
            "data_testid": "status",
            "visible": True,
        },
        {
            "index": 1,
            "tag": "button",
            "role": "button",
            "accessible_name": "Submit",
            "text": "Submit",
            "visible": True,
            "labels": [],
        },
    ]

    candidates = generate_selector_candidates(elements)

    assert candidates
    assert all(candidate["element_index"] == 1 for candidate in candidates)


def test_prioritize_candidates_for_intent_front_loads_matches():
    candidates = [
        {
            "selector": {"strategy": "data-testid", "value": "heading"},
            "score": 100,
            "intent_hint": "h1: Capability Form",
            "source": "data_testid",
            "reasons": [],
        },
        {
            "selector": {"strategy": "data-testid", "value": "submit-button"},
            "score": 100,
            "intent_hint": "button: Save",
            "source": "data_testid",
            "reasons": [],
        },
    ]

    prioritized = prioritize_candidates_for_intent(candidates, "Save")

    assert prioritized[0]["selector"]["value"] == "submit-button"
    assert prioritized[0]["score"] > candidates[1]["score"]


def test_generate_selector_candidates_marks_dynamic_id_as_risky():
    elements = [
        {
            "index": 0,
            "tag": "input",
            "role": "textbox",
            "id": "css-a1b2c3d4e5",
            "visible": True,
            "labels": [],
        }
    ]

    candidates = generate_selector_candidates(elements, include_fallbacks=False)
    id_candidate = next(
        candidate for candidate in candidates if candidate["selector"]["strategy"] == "id"
    )

    assert "dynamic selector" in id_candidate["risk_flags"]
    assert id_candidate["score"] < 64


def test_redact_page_map_sanitizes_url_and_sensitive_text():
    page_map = {
        "url": "https://example.com/login?token=secret#frag",
        "title": "Login token=secret",
        "headings": ["Welcome"],
        "elements": [
            {
                "index": 0,
                "tag": "input",
                "name": "api_key",
                "placeholder": "token=secret",
                "href": "https://example.com/reset?session_id=abc123&email=a@example.com",
                "visible": True,
                "bounds": {"x": 1},
            }
        ],
    }

    redacted = redact_page_map(page_map)

    assert redacted["url"] == "https://example.com/login"
    assert "[REDACTED]" in redacted["title"]
    assert redacted["elements"][0]["placeholder"] == "token=[REDACTED]"
    assert redacted["elements"][0]["href"] == "https://example.com/reset"


def test_failed_request_entry_accepts_playwright_string_failure():
    class Request:
        url = "https://example.test/path?token=secret"
        method = "GET"
        failure = "net::ERR_FAILED token=secret"

    entry = _failed_request_entry(Request())

    assert entry == {
        "url": "https://example.test/path",
        "method": "GET",
        "error": "net::ERR_FAILED token=[REDACTED]",
    }


def test_id_locator_uses_literal_attribute_selector():
    class Page:
        def __init__(self):
            self.selector = ""

        def locator(self, selector):
            self.selector = selector
            return object()

    page = Page()

    _locator_from_selector(page, {"strategy": "id", "value": "ctl00:Main.login"})

    assert page.selector == '[id="ctl00:Main.login"]'


def test_css_fallback_uses_literal_id_attribute_selector():
    fallback = _css_fallback({"tag": "input", "id": "login:email"})

    assert fallback == 'input[id="login:email"]'


@pytest.mark.asyncio
async def test_safe_click_restores_page_before_click():
    class Locator:
        @property
        def first(self):
            return self

        async def click(self, timeout):
            self.timeout = timeout

    class Page:
        def __init__(self):
            self.url = "https://example.test/mutated"
            self.goto_calls = []
            self.locator_value = ""
            self.locator_obj = Locator()

        async def goto(self, url, *, wait_until, timeout):
            self.goto_calls.append((url, wait_until, timeout))
            self.url = url

        def locator(self, selector):
            self.locator_value = selector
            return self.locator_obj

        async def wait_for_timeout(self, _timeout):
            return None

    page = Page()

    result = await _safe_click_candidate(
        page,
        {"strategy": "id", "value": "submit:button"},
        "https://example.test/start",
        1234,
    )

    assert result is True
    assert page.goto_calls == [("https://example.test/start", "load", 1234)]
    assert page.locator_value == '[id="submit:button"]'


@pytest.mark.asyncio
async def test_check_success_polls_until_expected_url_matches():
    class Page:
        def __init__(self):
            self.url = "https://example.test/start"
            self.polls = 0

        async def wait_for_timeout(self, _timeout):
            self.polls += 1
            if self.polls == 2:
                self.url = "https://example.test/done"

    page = Page()

    assert await _check_success(page, "done", None, timeout_ms=1000) is True
