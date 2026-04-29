"""Tests for browser selector swarm candidate generation."""

import inspect

import pytest

from harness.selectors.browser_swarm import (
    _check_success,
    _css_fallback,
    _failed_request_entry,
    _has_actionable_page_evidence,
    _parse_subagent_json,
    _normalize_subagent_policy,
    _selected_subagents_for_policy,
    _subagent_escalation_reasons,
    _locator_from_selector,
    _safe_click_candidate,
    validate_selector_candidates,
    generate_selector_candidates,
    merge_subagent_candidates,
    prioritize_candidates_for_intent,
    redact_page_map,
    run_browser_selector_swarm,
    run_selector_subagents,
    scrape_page_map,
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


def test_browser_selector_swarm_defaults_to_domcontentloaded():
    signature = inspect.signature(run_browser_selector_swarm)

    assert signature.parameters["wait_until"].default == "domcontentloaded"


@pytest.mark.asyncio
async def test_scrape_page_map_retries_navigation_context_reset():
    class Page:
        def __init__(self):
            self.calls = 0
            self.waits = 0

        async def evaluate(self, _script):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("Execution context was destroyed")
            return {"url": "https://example.test", "title": "Ready", "elements": []}

        async def wait_for_load_state(self, _state, *, timeout):
            self.waits += 1

        async def wait_for_timeout(self, _timeout):
            return None

    page = Page()

    page_map = await scrape_page_map(page)

    assert page_map["title"] == "Ready"
    assert page.calls == 2
    assert page.waits == 1


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


def test_merge_subagent_candidates_front_loads_valid_proposals():
    deterministic = [
        {
            "selector": {"strategy": "text", "value": "Learn more"},
            "score": 68,
            "source": "visible_text",
        }
    ]
    subagent_results = [
        {
            "name": "accessibility_mapper",
            "proposed_candidates": [
                {
                    "selector": {"strategy": "role", "role": "link", "name": "Learn more"},
                    "score": 95,
                    "intent_hint": "a: Learn more",
                    "reasons": ["role/name is stable"],
                }
            ],
        }
    ]

    merged = merge_subagent_candidates(deterministic, subagent_results)

    assert merged[0]["selector"]["strategy"] == "role"
    assert merged[0]["source"] == "subagent:accessibility_mapper"


def test_merge_subagent_candidates_tolerates_non_numeric_scores():
    merged = merge_subagent_candidates(
        [{"selector": {"strategy": "text", "value": "Save"}, "score": "unknown"}],
        [
            {
                "name": "accessibility_mapper",
                "summary": "fallback",
                "proposed_candidates": [
                    {
                        "selector": {"strategy": "role", "role": "button", "name": "Save"},
                        "score": "high",
                        "reasons": "stable accessible name",
                    }
                ],
            }
        ],
    )

    assert merged[0]["score"] == 75
    assert merged[0]["reasons"] == ["stable accessible name"]


def test_parse_subagent_json_handles_non_json_text():
    parsed = _parse_subagent_json("not json")

    assert parsed["candidates"] == []
    assert "not json" in parsed["summary"]


def test_subagent_policy_off_when_not_enabled():
    assert _normalize_subagent_policy(False, "all") == "off"
    assert _normalize_subagent_policy(True, "focused") == "focused"


def test_auto_policy_skips_when_deterministic_validation_passes():
    reasons = _subagent_escalation_reasons(
        policy="auto",
        deterministic_validation={"winner": {"selector": {"strategy": "role"}}},
        deterministic_candidates=[{"selector": {"strategy": "role"}}],
    )

    assert reasons == []


def test_auto_policy_escalates_on_failed_validation():
    reasons = _subagent_escalation_reasons(
        policy="auto",
        deterministic_validation={"winner": None},
        deterministic_candidates=[{"selector": {"strategy": "css"}}],
    )

    assert "deterministic validation did not prove a selector" in reasons
    assert "top deterministic candidates are fallback selectors" in reasons


def test_auto_policy_marks_unusable_page_evidence_before_subagents():
    page_map = {
        "elements": [
            {
                "tag": "meta",
                "name": "viewport",
                "visible": False,
            }
        ]
    }

    reasons = _subagent_escalation_reasons(
        policy="auto",
        deterministic_validation={"winner": None},
        deterministic_candidates=[],
        page_map=page_map,
    )

    assert "insufficient actionable page evidence" in reasons
    assert _has_actionable_page_evidence(page_map) is False


def test_focused_policy_selects_small_agent_set():
    selected = _selected_subagents_for_policy("focused", ["subagent policy is focused"])

    assert selected == ["accessibility_mapper", "form_mapper", "selector_scorer"]


def test_all_policy_includes_debug_agent_set():
    selected = _selected_subagents_for_policy("all", ["subagent policy is all"])

    assert "workflow_planner" in selected
    assert "candidate_validator" not in selected


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


@pytest.mark.asyncio
async def test_validate_candidates_uses_provided_start_url_for_safe_click():
    class FirstLocator:
        async def is_visible(self, timeout):
            return True

        async def is_enabled(self, timeout):
            return True

        async def click(self, timeout):
            return None

    class Locator:
        @property
        def first(self):
            return FirstLocator()

        async def count(self):
            return 1

    class Page:
        def __init__(self):
            self.url = "https://example.test/after-click"
            self.goto_calls = []

        async def goto(self, url, *, wait_until, timeout):
            self.goto_calls.append(url)
            self.url = "https://example.test/done"

        def get_by_role(self, role, name=None):
            return Locator()

        async def wait_for_timeout(self, _timeout):
            return None

    page = Page()

    result = await validate_selector_candidates(
        page,
        [{"selector": {"strategy": "role", "role": "link", "name": "Done"}}],
        safe_click=True,
        expect_url_contains="done",
        start_url="https://example.test/start",
    )

    assert result["winner"] is not None
    assert page.goto_calls == ["https://example.test/start"]


@pytest.mark.asyncio
async def test_run_selector_subagents_disabled_reports_not_sent():
    results = await run_selector_subagents(
        page_map={"url": "https://example.test", "elements": []},
        candidates=[],
        intent="Save",
        enabled=False,
    )

    assert results
    assert all(result["status"] == "not_sent" for result in results)
    assert all(result["sent"] is False for result in results)


@pytest.mark.asyncio
async def test_run_selector_subagents_unavailable_reports_codex_cli_issue(monkeypatch):
    from harness.selectors import browser_swarm

    monkeypatch.setattr(browser_swarm, "_find_codex_cli", lambda: None)

    results = await run_selector_subagents(
        page_map={"url": "https://example.test", "elements": []},
        candidates=[],
        intent="Save",
        enabled=True,
    )

    assert results
    assert all(result["status"] == "unavailable" for result in results)
    assert all(result["sent"] is False for result in results)
    assert all(result["attempted"] is True for result in results)
