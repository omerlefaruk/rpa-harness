"""Tripadvisor - The Marmara Taksim recent review collection.

This test makes the process repeatable through the RPA harness:
1. Run browser selector swarm against the Tripadvisor hotel page.
2. If Tripadvisor blocks automation, save explicit blocked evidence.
3. If the page is accessible, parse exact-date reviews from the last 30 days.
"""

from __future__ import annotations

import json
import os
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from harness import AutomationTestCase, PlaywrightDriver
from harness.selectors.browser_swarm import run_browser_selector_swarm


TARGET_URL = (
    "https://www.tripadvisor.com/Hotel_Review-g293974-d1924287-Reviews-"
    "The_Marmara_Taksim-Istanbul.html"
)
ARTIFACT_PATH = Path("runs/browser_recon/marmara_taksim_tripadvisor_latest_reviews.json")


class TripadvisorMarmaraTaksimReviewsTest(AutomationTestCase):
    name = "tripadvisor_marmara_taksim_recent_reviews"
    tags = [
        "browser",
        "external",
        "public-site",
        "tripadvisor",
        "reviews",
        "marmara-taksim",
        "swarm",
    ]

    async def setup(self):
        self.driver = None

    async def run(self):
        today = _today()
        start = today - timedelta(days=30)

        self.step("Run selector swarm on Tripadvisor hotel page")
        swarm_report = await run_browser_selector_swarm(
            TARGET_URL,
            output_dir="runs/browser_recon",
            wait_until="domcontentloaded",
            timeout_ms=45000,
            max_candidates=40,
            intent="Most recent reviews sort control",
            use_subagents=True,
            subagent_policy="auto",
            save_raw_html=True,
        )

        self.result.metadata["swarm_report"] = swarm_report["artifacts"]["report"]
        self.result.metadata["swarm_screenshot"] = swarm_report["artifacts"]["screenshot"]

        if _tripadvisor_blocked(swarm_report):
            self.step("Record Tripadvisor access restriction")
            artifact = _write_artifact(
                {
                    "hotel": "The Marmara Taksim",
                    "source": "Tripadvisor",
                    "source_url": TARGET_URL,
                    "requested_sort": "Most recent",
                    "last_30_days_window": {
                        "start": start.isoformat(),
                        "end": today.isoformat(),
                    },
                    "status": "blocked_by_tripadvisor_access_restriction",
                    "last_30_days_reviews": [],
                    "last_30_days_review_count": 0,
                    "swarm": {
                        "status": swarm_report["status"],
                        "report": swarm_report["artifacts"]["report"],
                        "screenshot": swarm_report["artifacts"]["screenshot"],
                        "reasons": swarm_report["summary"].get(
                            "subagent_escalation_reasons", []
                        ),
                        "console_errors": swarm_report.get("console_errors", []),
                    },
                }
            )
            self.result.metadata["review_artifact"] = str(artifact)
            self.expect(artifact.exists(), "Expected blocked-evidence artifact to be written")
            return

        self.step("Load accessible Tripadvisor page for review text")
        self.driver = await PlaywrightDriver.launch(config=self.config)
        await self.driver.goto(TARGET_URL, wait_until="domcontentloaded", timeout=45000)
        body_text = await self.driver.page.locator("body").inner_text(timeout=10000)

        self.step("Parse exact-date reviews in last 30 days")
        reviews = parse_tripadvisor_reviews(body_text, today=today)
        exact_reviews = [review for review in reviews if review["in_last_30_days"] is True]
        uncertain_reviews = [review for review in reviews if review["in_last_30_days"] is None]

        artifact = _write_artifact(
            {
                "hotel": "The Marmara Taksim",
                "source": "Tripadvisor",
                "source_url": TARGET_URL,
                "requested_sort": "Most recent",
                "last_30_days_window": {
                    "start": start.isoformat(),
                    "end": today.isoformat(),
                },
                "status": "reviews_extracted",
                "last_30_days_reviews": exact_reviews,
                "last_30_days_review_count": len(exact_reviews),
                "uncertain_month_only_reviews": uncertain_reviews,
                "swarm": {
                    "status": swarm_report["status"],
                    "report": swarm_report["artifacts"]["report"],
                    "screenshot": swarm_report["artifacts"]["screenshot"],
                },
            }
        )
        self.result.metadata["review_artifact"] = str(artifact)
        self.result.metadata["review_count"] = len(exact_reviews)
        self.expect(artifact.exists(), "Expected review artifact to be written")

    async def teardown(self):
        if self.driver:
            await self.driver.close()


def parse_tripadvisor_reviews(text: str, *, today: date | None = None) -> list[dict]:
    today = today or _today()
    start = today - timedelta(days=30)
    review_markers = list(
        re.finditer(
            r"(?P<reviewer>[^\n]{1,120}?)\s+wrote a review\s+"
            r"(?P<date>"
            r"[A-Z][a-z]{2,8}\s+\d{1,2}(?!\d)(?:,\s+\d{4})?"
            r"|[A-Z][a-z]{2,8}\s+\d{4}"
            r")",
            text,
        )
    )
    reviews: list[dict] = []

    for index, marker in enumerate(review_markers):
        next_start = review_markers[index + 1].start() if index + 1 < len(review_markers) else len(text)
        block = text[marker.end():next_start]
        published_raw = marker.group("date").strip()
        published = _parse_review_date(published_raw, today=today)
        in_window: Optional[bool]
        reason = None
        if published is None:
            in_window = None
            reason = "Exact review day was not present in the source text."
        else:
            in_window = start <= published <= today

        reviews.append(
            {
                "reviewer": marker.group("reviewer").strip(),
                "published_date": published.isoformat() if published else None,
                "published_date_raw": published_raw,
                "title": _first_non_empty_line(block),
                "date_of_stay": _match_optional(block, r"Date of stay:\s*([^\n]+)"),
                "trip_type": _match_optional(block, r"Trip type:\s*([^\n]+)"),
                "text_preview": _text_preview(block),
                "in_last_30_days": in_window,
                "reason": reason,
            }
        )

    return reviews


def _tripadvisor_blocked(report: dict) -> bool:
    summary = report.get("summary", {})
    reasons = summary.get("subagent_escalation_reasons", [])
    if "insufficient actionable page evidence" in reasons:
        return True
    errors = " ".join(item.get("text", "") for item in report.get("console_errors", []))
    return summary.get("interactive_elements", 0) <= 1 and "403" in errors


def _parse_review_date(raw: str, *, today: date) -> Optional[date]:
    cleaned = raw.replace(",", "").strip()
    parts = cleaned.split()
    if len(parts) == 2 and parts[1].isdigit() and len(parts[1]) == 4:
        return None
    formats = ["%B %d %Y", "%b %d %Y", "%B %d", "%b %d"]
    for fmt in formats:
        candidate = cleaned
        if "%Y" not in fmt:
            candidate = f"{candidate} {today.year}"
            fmt = f"{fmt} %Y"
        try:
            return datetime.strptime(candidate, fmt).date()
        except ValueError:
            continue
    return None


def _first_non_empty_line(text: str) -> str:
    for line in text.splitlines():
        value = line.strip()
        if value and not value.startswith("Date of stay:") and not value.startswith("Trip type:"):
            return value[:200]
    return ""


def _match_optional(text: str, pattern: str) -> Optional[str]:
    match = re.search(pattern, text)
    return match.group(1).strip() if match else None


def _text_preview(text: str) -> str:
    cleaned = " ".join(line.strip() for line in text.splitlines() if line.strip())
    return cleaned[:500]


def _write_artifact(payload: dict) -> Path:
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return ARTIFACT_PATH


def _today() -> date:
    raw = os.getenv("RPA_REVIEW_TODAY")
    if raw:
        return date.fromisoformat(raw)
    return date.today()
