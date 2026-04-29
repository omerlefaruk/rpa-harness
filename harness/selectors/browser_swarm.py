"""Browser selector swarm discovery and validation utilities."""

from __future__ import annotations

import asyncio
import html
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from harness.security import redact_text, sanitize_url
from harness.selectors.strategies import is_dynamic_selector

SWARM_CONFIG_PATH = Path(".agents/config/browser_selector_swarm.yaml")

INTERACTIVE_QUERY = ",".join(
    [
        "button",
        "a",
        "input",
        "select",
        "textarea",
        "[role]",
        "[data-testid]",
        "[data-test]",
        "[data-qa]",
        "[aria-label]",
        "[name]",
        "[placeholder]",
    ]
)

SCRAPE_SCRIPT = f"""
() => {{
  const query = {json.dumps(INTERACTIVE_QUERY)};
  const clean = (value, max = 120) => String(value || "")
    .replace(/\\s+/g, " ")
    .trim()
    .slice(0, max);
  const attr = (el, name) => el.getAttribute(name) || null;
  const isVisible = (el) => {{
    const style = window.getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style && style.visibility !== "hidden" &&
      style.display !== "none" &&
      rect.width > 0 &&
      rect.height > 0;
  }};
  const labelsFor = (el) => {{
    const labels = [];
    if (el.labels) {{
      for (const label of Array.from(el.labels)) {{
        const text = clean(label.innerText || label.textContent);
        if (text) labels.push(text);
      }}
    }}
    const closestLabel = el.closest ? el.closest("label") : null;
    if (closestLabel) {{
      const text = clean(closestLabel.innerText || closestLabel.textContent);
      if (text) labels.push(text);
    }}
    return Array.from(new Set(labels)).slice(0, 5);
  }};
  const roleFor = (el) => {{
    const explicit = attr(el, "role");
    if (explicit) return explicit;
    const tag = el.tagName.toLowerCase();
    const type = (attr(el, "type") || "").toLowerCase();
    if (tag === "button") return "button";
    if (tag === "a" && attr(el, "href")) return "link";
    if (tag === "select") return "combobox";
    if (tag === "textarea") return "textbox";
    if (tag === "input") {{
      if (type === "checkbox") return "checkbox";
      if (type === "radio") return "radio";
      if (type === "submit" || type === "button") return "button";
      return "textbox";
    }}
    return null;
  }};
  const nameFor = (el) => {{
    const aria = attr(el, "aria-label");
    if (aria) return clean(aria);
    const labels = labelsFor(el);
    if (labels.length) return labels[0];
    const placeholder = attr(el, "placeholder");
    if (placeholder) return clean(placeholder);
    const text = clean(el.innerText || el.textContent);
    if (text) return text;
    return attr(el, "name") || attr(el, "id") || null;
  }};

  const elements = Array.from(document.querySelectorAll(query)).map((el, index) => {{
    const rect = el.getBoundingClientRect();
    return {{
      index,
      tag: el.tagName.toLowerCase(),
      role: roleFor(el),
      accessible_name: nameFor(el),
      text: clean(el.innerText || el.textContent),
      id: attr(el, "id"),
      name: attr(el, "name"),
      type: attr(el, "type"),
      placeholder: attr(el, "placeholder"),
      aria_label: attr(el, "aria-label"),
      data_testid: attr(el, "data-testid"),
      data_test: attr(el, "data-test"),
      data_qa: attr(el, "data-qa"),
      href: el.tagName.toLowerCase() === "a" ? attr(el, "href") : null,
      labels: labelsFor(el),
      visible: isVisible(el),
      disabled: Boolean(el.disabled || attr(el, "aria-disabled") === "true"),
      bounds: {{
        x: Math.round(rect.x),
        y: Math.round(rect.y),
        width: Math.round(rect.width),
        height: Math.round(rect.height)
      }}
    }};
  }});

  const headings = Array.from(document.querySelectorAll("h1,h2,h3,[role='heading']"))
    .map((el) => clean(el.innerText || el.textContent))
    .filter(Boolean)
    .slice(0, 50);

  return {{
    url: window.location.href,
    title: document.title,
    element_count: elements.length,
    elements,
    headings
  }};
}}
"""


@dataclass
class SelectorCandidate:
    selector: dict[str, Any]
    source: str
    score: int
    element_index: int | None = None
    intent_hint: str | None = None
    reasons: list[str] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "selector": self.selector,
            "source": self.source,
            "score": self.score,
            "element_index": self.element_index,
            "intent_hint": self.intent_hint,
            "reasons": self.reasons,
            "risk_flags": self.risk_flags,
        }


@dataclass
class SelectorValidation:
    candidate: dict[str, Any]
    passed: bool
    count: int = 0
    visible: bool = False
    enabled: bool = False
    action_passed: bool | None = None
    success_check_passed: bool | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate": self.candidate,
            "passed": self.passed,
            "count": self.count,
            "visible": self.visible,
            "enabled": self.enabled,
            "action_passed": self.action_passed,
            "success_check_passed": self.success_check_passed,
            "error": self.error,
        }


def generate_selector_candidates(
    elements: list[dict[str, Any]],
    *,
    include_fallbacks: bool = True,
    intent: str | None = None,
) -> list[dict[str, Any]]:
    """Generate ranked selector candidates from a compact interactive DOM map."""
    candidates: list[SelectorCandidate] = []
    for element in elements:
        if not element.get("visible", True) or not _is_actionable_element(element):
            continue
        index = element.get("index")
        hint = _intent_hint(element)

        for attr_name, strategy, score in [
            ("data_testid", "data-testid", 100),
            ("data_test", "data-test", 98),
            ("data_qa", "data-qa", 96),
        ]:
            value = _clean_value(element.get(attr_name))
            if value:
                candidates.append(
                    _candidate(
                        {"strategy": strategy, "value": value},
                        source=attr_name,
                        score=score,
                        element_index=index,
                        intent_hint=hint,
                        reasons=[f"{strategy} is purpose-built for automation"],
                    )
                )

        role = _clean_value(element.get("role"))
        accessible_name = _clean_value(element.get("accessible_name"))
        if role and accessible_name:
            candidates.append(
                _candidate(
                    {"strategy": "role", "role": role, "name": accessible_name},
                    source="accessibility",
                    score=92,
                    element_index=index,
                    intent_hint=hint,
                    reasons=["role plus accessible name is stable and readable"],
                )
            )

        for label in element.get("labels") or []:
            value = _clean_value(label)
            if value:
                candidates.append(
                    _candidate(
                        {"strategy": "label", "value": value},
                        source="form",
                        score=90,
                        element_index=index,
                        intent_hint=hint,
                        reasons=["label targets the associated control"],
                    )
                )

        for attr_name, strategy, score in [
            ("aria_label", "aria-label", 88),
            ("name", "name", 82),
            ("placeholder", "placeholder", 74),
        ]:
            value = _clean_value(element.get(attr_name))
            if value:
                candidates.append(
                    _candidate(
                        {"strategy": strategy, "value": value},
                        source=attr_name,
                        score=score,
                        element_index=index,
                        intent_hint=hint,
                    )
                )

        text = _clean_value(element.get("text"))
        if text and element.get("tag") in {"button", "a"}:
            candidates.append(
                _candidate(
                    {"strategy": "text", "value": text},
                    source="visible_text",
                    score=68,
                    element_index=index,
                    intent_hint=hint,
                    risk_flags=["text selectors can break on copy changes"],
                )
            )

        value = _clean_value(element.get("id"))
        if value:
            candidates.append(
                _candidate(
                    {"strategy": "id", "value": value},
                    source="id",
                    score=64 if not is_dynamic_selector(value) else 35,
                    element_index=index,
                    intent_hint=hint,
                    risk_flags=["dynamic id"] if is_dynamic_selector(value) else [],
                )
            )

        if include_fallbacks:
            fallback = _css_fallback(element)
            if fallback:
                candidates.append(
                    _candidate(
                        {"strategy": "css", "value": fallback},
                        source="structure",
                        score=35,
                        element_index=index,
                        intent_hint=hint,
                        risk_flags=["structural fallback"],
                    )
                )

    ranked = [candidate.to_dict() for candidate in _dedupe_candidates(candidates)]
    return prioritize_candidates_for_intent(ranked, intent)


def prioritize_candidates_for_intent(
    candidates: list[dict[str, Any]],
    intent: str | None,
) -> list[dict[str, Any]]:
    """Boost and front-load candidates whose evidence matches the requested intent."""
    tokens = [token for token in str(intent or "").lower().split() if token]
    if not tokens:
        return candidates

    matched: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []
    for candidate in candidates:
        haystack = json.dumps(
            {
                "selector": candidate.get("selector"),
                "intent_hint": candidate.get("intent_hint"),
                "source": candidate.get("source"),
            },
            sort_keys=True,
        ).lower()
        copied = dict(candidate)
        copied["reasons"] = list(candidate.get("reasons") or [])
        if all(token in haystack for token in tokens):
            copied["score"] = int(copied.get("score", 0)) + 50
            copied["reasons"].append(f"matches requested intent: {intent}")
            matched.append(copied)
        else:
            unmatched.append(copied)

    if not matched:
        return candidates
    return sorted(matched, key=lambda item: item["score"], reverse=True) + unmatched


async def scrape_page_map(page: Any) -> dict[str, Any]:
    """Capture a compact selector-oriented page map from a Playwright page."""
    data = await page.evaluate(SCRAPE_SCRIPT)
    return redact_page_map(data)


def redact_page_map(page_map: dict[str, Any]) -> dict[str, Any]:
    """Redact sensitive-looking values without storing form input values."""
    redacted = dict(page_map)
    redacted["url"] = sanitize_url(str(redacted.get("url", "")))
    redacted["title"] = redact_text(redacted.get("title", ""), max_chars=200)
    redacted["headings"] = [
        redact_text(item, max_chars=160) for item in redacted.get("headings", [])
    ]
    redacted_elements = []
    for element in redacted.get("elements", []):
        clean_element: dict[str, Any] = {}
        for key, value in element.items():
            if key in {"bounds", "index", "visible", "disabled"}:
                clean_element[key] = value
            elif key == "href" and value is not None:
                clean_element[key] = redact_text(sanitize_url(str(value)), max_chars=160)
            elif isinstance(value, list):
                clean_element[key] = [redact_text(item, max_chars=120) for item in value]
            elif value is None:
                clean_element[key] = None
            else:
                clean_element[key] = redact_text(value, max_chars=160)
        redacted_elements.append(clean_element)
    redacted["elements"] = redacted_elements
    redacted["element_count"] = len(redacted_elements)
    return redacted


async def validate_selector_candidates(
    page: Any,
    candidates: list[dict[str, Any]],
    *,
    max_candidates: int = 50,
    stop_on_first: bool = True,
    timeout_ms: int = 1000,
    safe_click: bool = False,
    expect_url_contains: str | None = None,
    expect_text: str | None = None,
    restore_wait_until: str = "load",
) -> dict[str, Any]:
    """Validate candidates against the current page using deterministic checks."""
    validations: list[SelectorValidation] = []
    winner: dict[str, Any] | None = None
    start_url = page.url

    for candidate in candidates[:max_candidates]:
        validation = await _validate_one_candidate(
            page,
            candidate,
            start_url=start_url,
            timeout_ms=timeout_ms,
            safe_click=safe_click,
            expect_url_contains=expect_url_contains,
            expect_text=expect_text,
            restore_wait_until=restore_wait_until,
        )
        validations.append(validation)
        if validation.passed and winner is None:
            winner = candidate
            if stop_on_first:
                break

    return {
        "winner": winner,
        "validations": [validation.to_dict() for validation in validations],
        "validated_count": len(validations),
    }


async def run_browser_selector_swarm(
    url: str,
    *,
    output_dir: str = "runs/browser_recon",
    browser_name: str = "chromium",
    headless: bool = True,
    wait_until: str = "networkidle",
    timeout_ms: int = 30000,
    max_candidates: int = 50,
    safe_click: bool = False,
    expect_url_contains: str | None = None,
    expect_text: str | None = None,
    save_raw_html: bool = False,
    intent: str | None = None,
) -> dict[str, Any]:
    """Run selector discovery and validation for a URL and write a JSON report."""
    from playwright.async_api import async_playwright

    run_id = time.strftime("%Y%m%d_%H%M%S")
    run_dir = Path(output_dir) / f"selector_swarm_{run_id}"
    run_dir.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as playwright:
        browser_type = getattr(playwright, browser_name)
        browser = await browser_type.launch(headless=headless)
        page = await browser.new_page()
        console_errors: list[dict[str, str]] = []
        failed_requests: list[dict[str, str]] = []

        page.on(
            "console",
            lambda message: console_errors.append(
                {"type": message.type, "text": redact_text(message.text, max_chars=500)}
            )
            if message.type == "error"
            else None,
        )
        page.on(
            "requestfailed",
            lambda request: failed_requests.append(_failed_request_entry(request)),
        )

        await page.goto(url, wait_until=wait_until, timeout=timeout_ms)
        await page.wait_for_load_state(wait_until, timeout=timeout_ms)

        screenshot_path = run_dir / "screenshot.png"
        await page.screenshot(path=str(screenshot_path), full_page=True)

        page_map = await scrape_page_map(page)
        redacted_dom_path: Path | None = None
        if save_raw_html:
            redacted_dom_path = run_dir / "dom_redacted.json"
            redacted_dom_path.write_text(
                json.dumps(page_map, indent=2, default=str),
                encoding="utf-8",
            )
        candidates = generate_selector_candidates(page_map["elements"], intent=intent)
        validation = await validate_selector_candidates(
            page,
            candidates,
            max_candidates=max_candidates,
            timeout_ms=1500,
            safe_click=safe_click,
            expect_url_contains=expect_url_contains,
            expect_text=expect_text,
            restore_wait_until=wait_until,
        )

        report = {
            "status": "passed" if validation["winner"] else "no_winner",
            "url": sanitize_url(page.url),
            "title": page_map.get("title"),
            "artifacts": {
                "run_dir": str(run_dir),
                "screenshot": str(screenshot_path),
                "raw_html": None,
                "redacted_dom": str(redacted_dom_path) if redacted_dom_path else None,
            },
            "summary": {
                "intent": intent,
                "interactive_elements": page_map.get("element_count", 0),
                "candidates": len(candidates),
                "validated": validation["validated_count"],
                "console_errors": len(console_errors),
                "failed_requests": len(failed_requests),
            },
            "page_map": page_map,
            "candidates": candidates,
            "validation": validation,
            "orchestration": build_orchestration_report(
                intent=intent,
                safe_click=safe_click,
                expect_url_contains=expect_url_contains,
                expect_text=expect_text,
                validation=validation,
            ),
            "console_errors": console_errors,
            "failed_requests": failed_requests,
        }

        report_path = run_dir / "selector_swarm_report.json"
        html_path = run_dir / "selector_swarm_report.html"
        report["artifacts"]["report"] = str(report_path)
        report["artifacts"]["html_report"] = str(html_path)
        report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        html_path.write_text(_render_html_report(report), encoding="utf-8")
        await browser.close()
        return report


async def _validate_one_candidate(
    page: Any,
    candidate: dict[str, Any],
    *,
    start_url: str,
    timeout_ms: int,
    safe_click: bool,
    expect_url_contains: str | None,
    expect_text: str | None,
    restore_wait_until: str,
) -> SelectorValidation:
    try:
        if safe_click:
            await _restore_page(page, start_url, timeout_ms, restore_wait_until)

        locator = _locator_from_selector(page, candidate["selector"])
        count = await locator.count()
        visible = False
        enabled = False
        action_passed: bool | None = None
        success_check_passed: bool | None = None

        if count > 0:
            first = locator.first
            visible = await first.is_visible(timeout=timeout_ms)
            enabled = await first.is_enabled(timeout=timeout_ms) if visible else False

        passed = count == 1 and visible and enabled
        if passed and safe_click:
            action_passed = await _safe_click_candidate(
                page,
                candidate["selector"],
                start_url,
                timeout_ms,
                restore_wait_until,
            )
            success_check_passed = await _check_success(
                page,
                expect_url_contains,
                expect_text,
                timeout_ms,
            )
            passed = bool(action_passed and success_check_passed)

        return SelectorValidation(
            candidate=candidate,
            passed=passed,
            count=count,
            visible=visible,
            enabled=enabled,
            action_passed=action_passed,
            success_check_passed=success_check_passed,
        )
    except Exception as exc:
        return SelectorValidation(
            candidate=candidate,
            passed=False,
            error=redact_text(exc, max_chars=500),
        )


async def _safe_click_candidate(
    page: Any,
    selector: dict[str, Any],
    start_url: str,
    timeout_ms: int,
    restore_wait_until: str = "load",
) -> bool:
    await _restore_page(page, start_url, timeout_ms, restore_wait_until)
    locator = _locator_from_selector(page, selector)
    await locator.first.click(timeout=timeout_ms)
    return True


async def _restore_page(
    page: Any,
    start_url: str,
    timeout_ms: int,
    wait_until: str = "load",
) -> None:
    await page.goto(start_url, wait_until=wait_until, timeout=timeout_ms)


async def _check_success(
    page: Any,
    expect_url_contains: str | None,
    expect_text: str | None,
    timeout_ms: int = 1000,
) -> bool:
    if not expect_url_contains and not expect_text:
        return True

    deadline = time.monotonic() + (max(timeout_ms, 0) / 1000)
    while time.monotonic() <= deadline:
        checks = []
        if expect_url_contains:
            checks.append(expect_url_contains in page.url)
        if expect_text:
            try:
                checks.append(
                    await page.get_by_text(expect_text).first.is_visible(timeout=250)
                )
            except Exception:
                checks.append(False)
        if all(checks):
            return True
        await page.wait_for_timeout(100)
    return False


def _locator_from_selector(page: Any, selector: dict[str, Any]) -> Any:
    strategy = str(selector.get("strategy", "")).lower()
    value = selector.get("value")
    if strategy in {"data-testid", "testid"}:
        return page.get_by_test_id(str(value))
    if strategy == "data-test":
        return page.locator(f"[data-test={json.dumps(str(value))}]")
    if strategy == "data-qa":
        return page.locator(f"[data-qa={json.dumps(str(value))}]")
    if strategy == "role":
        role = selector.get("role") or value
        name = selector.get("name")
        return page.get_by_role(str(role), name=str(name)) if name else page.get_by_role(str(role))
    if strategy == "label":
        return page.get_by_label(str(value))
    if strategy == "placeholder":
        return page.get_by_placeholder(str(value))
    if strategy == "text":
        return page.get_by_text(str(value))
    if strategy == "id":
        return page.locator(f"[id={json.dumps(str(value))}]")
    if strategy == "name":
        return page.locator(f"[name={json.dumps(str(value))}]")
    if strategy == "aria-label":
        return page.locator(f"[aria-label={json.dumps(str(value))}]")
    if strategy == "css":
        return page.locator(str(value))
    if strategy == "xpath":
        return page.locator(str(value) if str(value).startswith("xpath=") else f"xpath={value}")
    raise ValueError(f"Unsupported selector strategy: {strategy}")


def _failed_request_entry(request: Any) -> dict[str, str]:
    failure = getattr(request, "failure", "")
    if callable(failure):
        failure = failure()
    error = failure.get("errorText", "") if isinstance(failure, dict) else str(failure or "")
    return {
        "url": sanitize_url(request.url),
        "method": request.method,
        "error": redact_text(error, max_chars=300),
    }


def _candidate(
    selector: dict[str, Any],
    *,
    source: str,
    score: int,
    element_index: int | None,
    intent_hint: str | None,
    reasons: list[str] | None = None,
    risk_flags: list[str] | None = None,
) -> SelectorCandidate:
    risks = list(risk_flags or [])
    selector_value = json.dumps(selector, sort_keys=True)
    if is_dynamic_selector(selector_value):
        risks.append("dynamic selector")
    return SelectorCandidate(
        selector=selector,
        source=source,
        score=score,
        element_index=element_index,
        intent_hint=intent_hint,
        reasons=reasons or [],
        risk_flags=list(dict.fromkeys(risks)),
    )


def _dedupe_candidates(candidates: list[SelectorCandidate]) -> list[SelectorCandidate]:
    best_by_key: dict[str, SelectorCandidate] = {}
    for candidate in candidates:
        key = json.dumps(candidate.selector, sort_keys=True)
        existing = best_by_key.get(key)
        if existing is None or candidate.score > existing.score:
            best_by_key[key] = candidate
    return sorted(
        best_by_key.values(),
        key=lambda item: (item.score, -len(json.dumps(item.selector, sort_keys=True))),
        reverse=True,
    )


def _intent_hint(element: dict[str, Any]) -> str | None:
    for key in ("accessible_name", "text", "aria_label", "placeholder", "name", "id"):
        value = _clean_value(element.get(key))
        if value:
            tag = element.get("tag") or "element"
            return f"{tag}: {value}"
    return None


def _is_actionable_element(element: dict[str, Any]) -> bool:
    tag = str(element.get("tag") or "").lower()
    role = str(element.get("role") or "").lower()
    return tag in {"button", "a", "input", "select", "textarea"} or role in {
        "button",
        "checkbox",
        "combobox",
        "link",
        "menuitem",
        "option",
        "radio",
        "searchbox",
        "slider",
        "spinbutton",
        "switch",
        "tab",
        "textbox",
    }


def _clean_value(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).replace("\n", " ").strip()
    while "  " in text:
        text = text.replace("  ", " ")
    return text[:120] if text else None


def _css_fallback(element: dict[str, Any]) -> str | None:
    tag = _clean_value(element.get("tag"))
    element_id = _clean_value(element.get("id"))
    name = _clean_value(element.get("name"))
    if tag and element_id and not is_dynamic_selector(element_id):
        return f"{tag}[id={json.dumps(element_id)}]"
    if tag and name:
        return f"{tag}[name={json.dumps(name)}]"
    return tag


def build_orchestration_report(
    *,
    intent: str | None,
    safe_click: bool,
    expect_url_contains: str | None,
    expect_text: str | None,
    validation: dict[str, Any],
    config_path: Path = SWARM_CONFIG_PATH,
) -> dict[str, Any]:
    """Return report-safe orchestration details without exposing hidden reasoning."""
    config = _load_swarm_config(config_path)
    model_profiles = config.get("model_profiles", {})
    subagent_config = config.get("subagents", {})
    recommended_dispatch = config.get("recommended_dispatch", {})

    deterministic_roles = {
        "page_stabilizer",
        "dom_scraper",
        "accessibility_mapper",
        "form_mapper",
        "text_mapper",
        "structure_mapper",
        "network_mapper",
        "state_mapper",
        "selector_scorer",
        "candidate_validator",
    }
    executed_agents = []
    configured_agents = []

    for name, subagent in subagent_config.items():
        profile_name = subagent.get("model_profile")
        profile = model_profiles.get(profile_name, {}) if profile_name else {}
        row = {
            "name": name,
            "sent": False,
            "runtime": subagent.get("runtime") or "codex",
            "model_profile": profile_name,
            "model": profile.get("model"),
            "reasoning_effort": profile.get("reasoning_effort"),
            "max_parallel": subagent.get("max_parallel"),
            "timeout_seconds": subagent.get("timeout_seconds"),
            "owns": subagent.get("owns", []),
            "output_schema": subagent.get("output_schema"),
        }
        if name in deterministic_roles:
            row["sent"] = True
            row["runtime"] = subagent.get("runtime") or "deterministic_python"
            row["decision_summary"] = _decision_summary_for_agent(
                name,
                intent=intent,
                safe_click=safe_click,
                winner=validation.get("winner"),
            )
            executed_agents.append(row)
        configured_agents.append(row)

    orchestrator_profile = model_profiles.get("planner", {})
    decision_trace = [
        "Loaded selector swarm configuration.",
        "Opened the target page with Playwright and waited for page stability.",
        "Captured screenshot, console errors, failed requests, and compact interactive DOM map.",
        "Generated selector candidates from test ids, accessibility data, labels, text, ids, and structural fallbacks.",
        "Boosted candidates matching the requested intent." if intent else "No explicit intent was provided, so candidates kept base ranking.",
        "Validated candidates with deterministic Playwright checks.",
    ]
    if safe_click:
        checks = []
        if expect_url_contains:
            checks.append(f"url contains {expect_url_contains}")
        if expect_text:
            checks.append(f"text visible {expect_text}")
        decision_trace.append(
            "Safe-click validation was enabled with success check: "
            + ", ".join(checks)
        )
    else:
        decision_trace.append("Safe-click validation was disabled; proof stopped at selector presence/visibility/enabled checks.")

    return {
        "execution_mode": "deterministic_selector_swarm",
        "codex_subagents_invoked": False,
        "hidden_chain_of_thought_recorded": False,
        "thinking_process_note": (
            "Report exposes configuration, reasoning_effort, and decision summaries. "
            "It does not expose private chain-of-thought."
        ),
        "orchestrator": {
            "name": "browser_selector_swarm_orchestrator",
            "runtime": "harness.selectors.browser_swarm.run_browser_selector_swarm",
            "model_profile": "planner",
            "model": orchestrator_profile.get("model"),
            "reasoning_effort": orchestrator_profile.get("reasoning_effort"),
            "model_used_in_this_run": False,
            "decision_summary": (
                "The current implementation used deterministic Python and Playwright. "
                "The planner model is the configured model for future LLM planning handoff."
            ),
        },
        "recommended_dispatch": recommended_dispatch,
        "executed_agents": executed_agents,
        "configured_agents": configured_agents,
        "decision_trace": decision_trace,
    }


def _load_swarm_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        import yaml

        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _decision_summary_for_agent(
    name: str,
    *,
    intent: str | None,
    safe_click: bool,
    winner: dict[str, Any] | None,
) -> str:
    summaries = {
        "page_stabilizer": "Reached the page and captured stable-page evidence.",
        "dom_scraper": "Extracted a compact inventory of interactive elements and headings.",
        "accessibility_mapper": "Generated role/name candidates from inferred accessible names.",
        "form_mapper": "Generated label, name, and placeholder candidates for form controls.",
        "text_mapper": "Generated text fallback candidates for links and buttons.",
        "structure_mapper": "Generated low-priority CSS fallbacks while flagging structural risk.",
        "network_mapper": "Captured failed request evidence and supported URL-based success checks.",
        "state_mapper": "Captured safe route/title metadata only; no raw app secrets or cookies.",
        "selector_scorer": "Merged candidates, removed duplicates, ranked stability, and applied intent boosts.",
        "candidate_validator": "Used Playwright to prove uniqueness, visibility, enabled state, and optional action success.",
    }
    summary = summaries.get(name, "Configured for future selector-swarm handoff.")
    if name == "selector_scorer" and intent:
        summary += f" Intent boost was applied for: {intent}."
    if name == "candidate_validator" and winner:
        summary += f" Winner: {json.dumps(winner.get('selector'), sort_keys=True)}."
    if name == "candidate_validator" and safe_click:
        summary += " Safe-click proof was enabled."
    return summary


def _render_html_report(report: dict[str, Any]) -> str:
    winner = report.get("validation", {}).get("winner")
    validations = report.get("validation", {}).get("validations", [])
    candidates = report.get("candidates", [])
    artifacts = report.get("artifacts", {})
    html_report = Path(str(artifacts.get("html_report") or "selector_swarm_report.html"))
    screenshot = Path(str(artifacts.get("screenshot") or ""))
    screenshot_src = str(screenshot)
    if screenshot.exists():
        try:
            screenshot_src = str(screenshot.relative_to(html_report.parent))
        except ValueError:
            screenshot_src = str(screenshot)

    def esc(value: Any) -> str:
        return html.escape(str(value if value is not None else ""))

    def selector_text(candidate: dict[str, Any]) -> str:
        selector = candidate.get("selector", candidate)
        return esc(json.dumps(selector, sort_keys=True, default=str))

    validation_rows = "\n".join(
        "<tr>"
        f"<td>{esc(index + 1)}</td>"
        f"<td><code>{selector_text(item.get('candidate', {}))}</code></td>"
        f"<td>{esc(item.get('passed'))}</td>"
        f"<td>{esc(item.get('count'))}</td>"
        f"<td>{esc(item.get('visible'))}</td>"
        f"<td>{esc(item.get('enabled'))}</td>"
        f"<td>{esc(item.get('action_passed'))}</td>"
        f"<td>{esc(item.get('success_check_passed'))}</td>"
        f"<td>{esc(item.get('error'))}</td>"
        "</tr>"
        for index, item in enumerate(validations[:100])
    )
    candidate_rows = "\n".join(
        "<tr>"
        f"<td>{esc(index + 1)}</td>"
        f"<td><code>{selector_text(item)}</code></td>"
        f"<td>{esc(item.get('score'))}</td>"
        f"<td>{esc(item.get('source'))}</td>"
        f"<td>{esc(item.get('intent_hint'))}</td>"
        f"<td>{esc(', '.join(item.get('risk_flags') or []))}</td>"
        "</tr>"
        for index, item in enumerate(candidates[:100])
    )
    winner_class = "winner" if winner else "no-winner"
    winner_json = esc(json.dumps(winner, indent=2, default=str))
    summary = report.get("summary", {})
    orchestration = report.get("orchestration", {})
    orchestrator = orchestration.get("orchestrator", {})
    executed_agents = orchestration.get("executed_agents", [])
    configured_agents = orchestration.get("configured_agents", [])
    decision_trace = orchestration.get("decision_trace", [])

    executed_agent_rows = "\n".join(
        "<tr>"
        f"<td>{esc(agent.get('name'))}</td>"
        f"<td>{esc(agent.get('sent'))}</td>"
        f"<td>{esc(agent.get('runtime'))}</td>"
        f"<td>{esc(agent.get('model'))}</td>"
        f"<td>{esc(agent.get('reasoning_effort'))}</td>"
        f"<td>{esc(agent.get('decision_summary'))}</td>"
        "</tr>"
        for agent in executed_agents
    )
    configured_agent_rows = "\n".join(
        "<tr>"
        f"<td>{esc(agent.get('name'))}</td>"
        f"<td>{esc(agent.get('runtime'))}</td>"
        f"<td>{esc(agent.get('model'))}</td>"
        f"<td>{esc(agent.get('reasoning_effort'))}</td>"
        f"<td>{esc(agent.get('max_parallel'))}</td>"
        f"<td>{esc(agent.get('timeout_seconds'))}</td>"
        f"<td>{esc(', '.join(agent.get('owns') or []))}</td>"
        "</tr>"
        for agent in configured_agents
    )
    trace_items = "\n".join(f"<li>{esc(item)}</li>" for item in decision_trace)

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Browser Selector Swarm Report</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 32px; color: #1f2933; }}
    h1, h2 {{ margin-bottom: 8px; }}
    .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin: 20px 0; }}
    .metric {{ border: 1px solid #d7dde5; border-radius: 8px; padding: 12px; background: #f8fafc; }}
    .metric b {{ display: block; font-size: 13px; color: #52606d; margin-bottom: 4px; }}
    .winner {{ border: 1px solid #8bd3a8; background: #effaf3; border-radius: 8px; padding: 14px; }}
    .no-winner {{ border: 1px solid #f5b7b1; background: #fff5f3; border-radius: 8px; padding: 14px; }}
    img {{ max-width: 100%; border: 1px solid #d7dde5; border-radius: 8px; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 12px; font-size: 13px; }}
    th, td {{ border: 1px solid #d7dde5; padding: 8px; vertical-align: top; }}
    th {{ background: #eef2f7; text-align: left; }}
    code, pre {{ font-family: "SFMono-Regular", Consolas, monospace; }}
    pre {{ white-space: pre-wrap; word-break: break-word; margin: 0; }}
  </style>
</head>
<body>
  <h1>Browser Selector Swarm Report</h1>
  <p><b>URL:</b> {esc(report.get("url"))}</p>
  <p><b>Title:</b> {esc(report.get("title"))}</p>
  <div class="summary">
    <div class="metric"><b>Status</b>{esc(report.get("status"))}</div>
    <div class="metric"><b>Intent</b>{esc(summary.get("intent"))}</div>
    <div class="metric"><b>Interactive Elements</b>{esc(summary.get("interactive_elements"))}</div>
    <div class="metric"><b>Candidates</b>{esc(summary.get("candidates"))}</div>
    <div class="metric"><b>Validated</b>{esc(summary.get("validated"))}</div>
    <div class="metric"><b>Console Errors</b>{esc(summary.get("console_errors"))}</div>
    <div class="metric"><b>Failed Requests</b>{esc(summary.get("failed_requests"))}</div>
  </div>

  <h2>Winner</h2>
  <div class="{winner_class}">
    <pre>{winner_json}</pre>
  </div>

  <h2>Orchestrator</h2>
  <div class="metric">
    <b>{esc(orchestrator.get("name"))}</b>
    Runtime: {esc(orchestrator.get("runtime"))}<br>
    Configured planner model: {esc(orchestrator.get("model"))}<br>
    Configured thinking level: {esc(orchestrator.get("reasoning_effort"))}<br>
    Model used in this run: {esc(orchestrator.get("model_used_in_this_run"))}<br>
    {esc(orchestrator.get("decision_summary"))}
  </div>
  <p>{esc(orchestration.get("thinking_process_note"))}</p>

  <h2>Decision Trace</h2>
  <ol>{trace_items}</ol>

  <h2>Executed Workers</h2>
  <table>
    <thead>
      <tr><th>Agent/Worker</th><th>Sent</th><th>Runtime</th><th>Model</th><th>Thinking Level</th><th>Decision Summary</th></tr>
    </thead>
    <tbody>{executed_agent_rows}</tbody>
  </table>

  <h2>Configured Subagents</h2>
  <table>
    <thead>
      <tr><th>Subagent</th><th>Runtime</th><th>Model</th><th>Thinking Level</th><th>Max Parallel</th><th>Timeout</th><th>Owns</th></tr>
    </thead>
    <tbody>{configured_agent_rows}</tbody>
  </table>

  <h2>Screenshot</h2>
  <img src="{esc(screenshot_src)}" alt="Browser screenshot">

  <h2>Validation Results</h2>
  <table>
    <thead>
      <tr><th>#</th><th>Selector</th><th>Passed</th><th>Count</th><th>Visible</th><th>Enabled</th><th>Action</th><th>Success Check</th><th>Error</th></tr>
    </thead>
    <tbody>{validation_rows}</tbody>
  </table>

  <h2>Top Candidates</h2>
  <table>
    <thead>
      <tr><th>#</th><th>Selector</th><th>Score</th><th>Source</th><th>Intent Hint</th><th>Risk Flags</th></tr>
    </thead>
    <tbody>{candidate_rows}</tbody>
  </table>
</body>
</html>
"""


def run_browser_selector_swarm_sync(url: str, **kwargs: Any) -> dict[str, Any]:
    """Synchronous wrapper for scripts and tests."""
    return asyncio.run(run_browser_selector_swarm(url, **kwargs))
