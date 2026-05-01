"""
Harness test: Trip.com - The Marmara Taksim recent reviews.

Goal: load the requested Trip.com hotel page, detect whether the browser is
redirected to sign-in, then use public Trip.com review pages for the same hotel
ID to extract reviews posted in the last 30 days.
"""

from __future__ import annotations

import json
import os
import re
from datetime import date, datetime, timedelta
from html import unescape
from pathlib import Path
from typing import Callable
from urllib.error import URLError
from urllib.request import Request, urlopen

from harness import AutomationTestCase, PlaywrightDriver


HOTEL_ID = 744495
HOTEL_NAME = "The Marmara Taksim"
REQUESTED_URL = (
    "https://tr.trip.com/hotels/istanbul-hotel-detail-744495/"
    "the-marmara-taksim/"
)
PRIMARY_REVIEW_URLS = [
    "https://in.trip.com/hotels/istanbul-hotel-detail-744495/"
    "the-marmara-taksim/review.html",
    REQUESTED_URL,
]
FALLBACK_REVIEW_URLS = [
    "https://my.trip.com/hotels/istanbul-hotel-detail-744495/"
    "the-marmara-taksim/review.html",
]
OUTPUT_PATH = Path("runs/browser_recon/the_marmara_taksim_last_30_days_reviews.json")
MAX_SOURCE_ATTEMPTS = 3
PAGE_TIMEOUT_MS = 45000
TEXT_READY_TIMEOUT_MS = 8000
RETRY_DELAY_MS = 500

EN_POSTED_RE = re.compile(
    r"Posted on\s+(?P<date>[A-Za-z]{3,9}\s+\d{1,2},\s+\d{4})"
)
TR_DATE_RE = re.compile(
    r"(?P<date>\d{1,2}\s+"
    r"(?:Ocak|Şubat|Mart|Nisan|Mayıs|Haziran|Temmuz|Ağustos|Eylül|Ekim|Kasım|Aralık)"
    r"\s+\d{4})"
)
RATING_RE = re.compile(r"^\d+(?:\.\d+)?/10$")
TR_MONTHS = {
    "Ocak": 1,
    "Şubat": 2,
    "Mart": 3,
    "Nisan": 4,
    "Mayıs": 5,
    "Haziran": 6,
    "Temmuz": 7,
    "Ağustos": 8,
    "Eylül": 9,
    "Ekim": 10,
    "Kasım": 11,
    "Aralık": 12,
}


class ReviewRecord:
    def __init__(
        self,
        *,
        date: date,
        source_url: str,
        reviewer: str | None,
        room: str | None,
        stay: str | None,
        traveler_type: str | None,
        rating: str | None,
        label: str | None,
        text: str,
        property_response: str | None = None,
    ):
        self.date = date
        self.source_url = source_url
        self.reviewer = reviewer
        self.room = room
        self.stay = stay
        self.traveler_type = traveler_type
        self.rating = rating
        self.label = label
        self.text = text
        self.property_response = property_response

    def to_dict(self) -> dict:
        return {
            "date": self.date.isoformat(),
            "source_url": self.source_url,
            "reviewer": self.reviewer,
            "room": self.room,
            "stay": self.stay,
            "traveler_type": self.traveler_type,
            "rating": self.rating,
            "label": self.label,
            "text": self.text,
            "property_response": self.property_response,
        }


class TripMarmaraTaksimReviewsTest(AutomationTestCase):
    name = "trip_marmara_taksim_reviews"
    tags = ["browser", "external", "public-site", "trip", "reviews", "marmara-taksim"]

    async def setup(self):
        try:
            import playwright.async_api  # noqa: F401
        except ModuleNotFoundError:
            self.driver = None
            self.skip(
                "Playwright is not installed. Install with: "
                "python3 -m pip install playwright && python3 -m playwright install chromium"
            )
            return
        self.driver = await PlaywrightDriver.launch(config=self.config)

    async def run(self):
        as_of = _as_of_date()
        start_date = as_of - timedelta(days=30)
        self.step(f"Use review window {start_date.isoformat()} to {as_of.isoformat()}")

        self.step("Open requested Turkish Trip.com hotel page")
        requested_status = await self._open_requested_page()
        requested_final_url = requested_status.get("final_url", "")
        requested_title = requested_status.get("title", "")
        requested_redirected_to_signin = "/account/signin" in requested_final_url

        if requested_redirected_to_signin:
            self.step("Requested hotel page redirected to Trip.com sign-in")
        else:
            self.step(f"Requested hotel page status: {requested_status['status']}")

        extracted: list[ReviewRecord] = []
        source_statuses: list[dict] = []
        await self._load_sources(PRIMARY_REVIEW_URLS, extracted, source_statuses)

        primary_had_failure = any(status["status"] != "loaded" for status in source_statuses)
        if primary_had_failure or not extracted:
            self.step("Primary review sources were incomplete; trying fallback sources")
            await self._load_sources(FALLBACK_REVIEW_URLS, extracted, source_statuses)

        reviews = filter_recent_reviews(extracted, start_date, as_of)
        self.step(f"Extracted {len(reviews)} reviews posted in the last 30 days")

        screenshot_path = await self.driver.screenshot(
            name="the_marmara_taksim_recent_reviews.png",
            full_page=True,
        )
        self.result.screenshots.append(screenshot_path)

        result = {
            "hotel": HOTEL_NAME,
            "hotel_id": HOTEL_ID,
            "requested_url": REQUESTED_URL,
            "requested_final_url": requested_final_url,
            "requested_title": requested_title,
            "requested_redirected_to_signin": requested_redirected_to_signin,
            "requested_status": requested_status,
            "last_30_days_window": {
                "start": start_date.isoformat(),
                "end": as_of.isoformat(),
            },
            "source_statuses": source_statuses,
            "last_30_days_review_count": len(reviews),
            "reviews": [review.to_dict() for review in reviews],
            "screenshot": screenshot_path,
        }
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_PATH.write_text(
            json.dumps(result, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        self.result.metadata["review_data"] = result
        self.result.metadata["review_output"] = str(OUTPUT_PATH)

        self.step("Verify public review sources were reachable")
        self.expect(
            any(status["status"] == "loaded" for status in source_statuses),
            "Expected at least one public Trip.com review source to load",
        )
        self.step("Verify dated reviews were parsed")
        self.expect(extracted, "Expected at least one dated review to be parsed")
        self.step("Verify output artifact was written")
        self.expect(OUTPUT_PATH.exists(), f"Expected output file: {OUTPUT_PATH}")

    async def _load_sources(
        self,
        source_urls: list[str],
        extracted: list[ReviewRecord],
        source_statuses: list[dict],
    ) -> None:
        for source_url in source_urls:
            self.step(f"Extract public review text from {source_url}")
            try:
                text, status = await self._load_source_text(source_url)
            except Exception as exc:
                text = ""
                status = {
                    "url": source_url,
                    "method": "unknown",
                    "status": "failed",
                    "final_url": source_url,
                    "text_length": 0,
                    "attempts": MAX_SOURCE_ATTEMPTS,
                    "error": sanitize_error(exc),
                }
            source_statuses.append(status)
            if text:
                extracted.extend(extract_review_records(text, source_url))

    async def _open_requested_page(self) -> dict:
        last_error = None
        for attempt in range(1, MAX_SOURCE_ATTEMPTS + 1):
            try:
                await self.driver.goto(
                    REQUESTED_URL,
                    wait_until="domcontentloaded",
                    timeout=PAGE_TIMEOUT_MS,
                )
                await wait_for_body_text(
                    self.driver.page,
                    lambda text: bool(text.strip()),
                    timeout_ms=TEXT_READY_TIMEOUT_MS,
                )
                final_url = await self.driver.get_url()
                return {
                    "url": REQUESTED_URL,
                    "method": "playwright",
                    "status": "signin_redirect" if "/account/signin" in final_url else "loaded",
                    "final_url": final_url,
                    "title": await self.driver.get_title(),
                    "attempts": attempt,
                }
            except Exception as exc:
                last_error = exc
                await self.driver.page.wait_for_timeout(RETRY_DELAY_MS * attempt)
        return {
            "url": REQUESTED_URL,
            "method": "playwright",
            "status": "failed",
            "final_url": "",
            "title": "",
            "attempts": MAX_SOURCE_ATTEMPTS,
            "error": sanitize_error(last_error),
        }

    async def _load_source_text(self, source_url: str) -> tuple[str, dict]:
        if source_url == REQUESTED_URL:
            text, status = fetch_public_text_with_status(source_url)
            status["url"] = source_url
            return text, {
                "url": source_url,
                "method": "http_public_html",
                "status": "loaded" if text else status["status"],
                "final_url": source_url,
                "text_length": len(text),
                "attempts": status["attempts"],
                **({"error": status["error"]} if status.get("error") else {}),
            }

        http_text, http_status = fetch_public_text_with_status(source_url)
        if http_text and extract_review_records(http_text, source_url):
            return http_text, {
                "url": source_url,
                "method": "http_public_html",
                "status": "loaded",
                "final_url": source_url,
                "text_length": len(http_text),
                "attempts": http_status["attempts"],
            }

        last_error = None
        for attempt in range(1, MAX_SOURCE_ATTEMPTS + 1):
            try:
                await self.driver.goto(
                    source_url,
                    wait_until="domcontentloaded",
                    timeout=PAGE_TIMEOUT_MS,
                )
                final_url = await self.driver.get_url()
                if "/account/signin" in final_url:
                    return "", {
                        "url": source_url,
                        "method": "playwright",
                        "status": "signin_redirect",
                        "final_url": final_url,
                        "text_length": 0,
                        "attempts": attempt,
                    }
                text = await wait_for_body_text(
                    self.driver.page,
                    is_review_source_text_ready,
                    timeout_ms=TEXT_READY_TIMEOUT_MS,
                )
                return text, {
                    "url": source_url,
                    "method": "playwright",
                    "status": "loaded",
                    "final_url": final_url,
                    "text_length": len(text),
                    "attempts": attempt,
                }
            except Exception as exc:
                last_error = exc
                await self.driver.page.wait_for_timeout(RETRY_DELAY_MS * attempt)

        return "", {
            "url": source_url,
            "method": "playwright",
            "status": "failed",
            "final_url": source_url,
            "text_length": 0,
            "attempts": MAX_SOURCE_ATTEMPTS,
            "error": sanitize_error(last_error),
            "http_fallback_status": http_status["status"],
        }

    async def teardown(self):
        if self.driver:
            await self.driver.close()


def _as_of_date() -> date:
    configured = os.getenv("TRIP_REVIEW_AS_OF_DATE")
    if configured:
        return date.fromisoformat(configured)
    return datetime.now().date()


async def wait_for_body_text(
    page,
    predicate: Callable[[str], bool],
    *,
    timeout_ms: int,
    poll_ms: int = 250,
) -> str:
    deadline = datetime.now().timestamp() + (timeout_ms / 1000)
    last_text = ""
    while datetime.now().timestamp() <= deadline:
        try:
            last_text = await page.locator("body").inner_text(timeout=1000)
            if predicate(last_text):
                return last_text
        except Exception:
            pass
        await page.wait_for_timeout(poll_ms)
    raise TimeoutError("Timed out waiting for expected Trip.com page text")


def is_review_source_text_ready(text: str) -> bool:
    return bool(
        text
        and HOTEL_NAME in text
        and (
            "Posted on" in text
            or "Ulasan" in text
            or "Yorum" in text
            or "Misafirler ne diyor" in text
        )
    )


def fetch_public_text_with_status(url: str) -> tuple[str, dict]:
    last_error = None
    for attempt in range(1, MAX_SOURCE_ATTEMPTS + 1):
        try:
            text = fetch_public_text_once(url)
            if text:
                return text, {"status": "loaded", "attempts": attempt, "error": None}
        except (TimeoutError, URLError, OSError) as exc:
            last_error = exc
    return "", {
        "status": "failed",
        "attempts": MAX_SOURCE_ATTEMPTS,
        "error": sanitize_error(last_error),
    }


def fetch_public_text_once(url: str) -> str:
    request = Request(url, headers=public_request_headers())
    with urlopen(request, timeout=20) as response:
        html = response.read().decode("utf-8", "replace")
    return html_to_text(html)


def public_request_headers() -> dict[str, str]:
    return {
        "User-Agent": "Mozilla/5.0 (compatible; RPAHarness/1.0)",
        "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
    }


def html_to_text(html: str) -> str:
    text = re.sub(r"<(script|style)[\s\S]*?</\1>", "\n", html, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "\n", text)
    return normalize_text(unescape(text))


def extract_review_records(text: str, source_url: str) -> list[ReviewRecord]:
    normalized = normalize_text(text)
    records = extract_english_review_records(normalized, source_url)
    records.extend(extract_turkish_summary_reviews(normalized, source_url))
    return dedupe_reviews(records)


def extract_english_review_records(text: str, source_url: str) -> list[ReviewRecord]:
    matches = list(EN_POSTED_RE.finditer(text))
    records: list[ReviewRecord] = []
    for index, match in enumerate(matches):
        try:
            review_date = datetime.strptime(match.group("date"), "%b %d, %Y").date()
        except ValueError:
            continue
        start = max(0, match.start() - 260)
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        prefix = text[start:match.start()]
        suffix = text[match.end():end]
        text_body, response = split_review_response(suffix)
        metadata = parse_english_metadata(prefix)
        if not text_body:
            continue
        records.append(
            ReviewRecord(
                date=review_date,
                source_url=source_url,
                reviewer=metadata.get("reviewer"),
                room=metadata.get("room"),
                stay=metadata.get("stay"),
                traveler_type=metadata.get("traveler_type"),
                rating=metadata.get("rating"),
                label=metadata.get("label"),
                text=text_body,
                property_response=response,
            )
        )
    return records


def extract_turkish_summary_reviews(text: str, source_url: str) -> list[ReviewRecord]:
    records: list[ReviewRecord] = []
    matches = list(TR_DATE_RE.finditer(text))
    for index, match in enumerate(matches):
        try:
            review_date = parse_turkish_date(match.group("date"))
        except (KeyError, ValueError):
            continue
        next_start = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[match.end():next_start]
        body = re.split(r"\b(?:Restoran|Hizmetler ve Olanaklar|Sürdürülebilirlik)\b", body)[0]
        body = normalize_text(body)
        if not body or not looks_like_review_text(body):
            continue
        reviewer_window = normalize_text(text[max(0, match.start() - 100):match.start()])
        reviewer = reviewer_window.split()[-1] if reviewer_window else None
        records.append(
            ReviewRecord(
                date=review_date,
                source_url=source_url,
                reviewer=reviewer,
                room=None,
                stay=None,
                traveler_type=None,
                rating=None,
                label=None,
                text=body[:1200],
            )
        )
    return records


def parse_english_metadata(prefix: str) -> dict[str, str | None]:
    tail = normalize_text(prefix).split()
    compact = " ".join(tail[-45:])
    compact = trim_to_review_metadata(compact)

    room = None
    stay = None
    traveler_type = None
    rating = None
    label = None
    reviewer = None

    stayed = re.search(r"Stayed in\s+([A-Za-z]{3,9}\s+\d{4})", compact)
    if stayed:
        stay = stayed.group(1)
        before_stay = compact[:stayed.start()].strip()
        parts = before_stay.split(" Show More ")
        candidate = parts[-1].strip() if parts else before_stay
        reviewer = infer_reviewer(before_stay)
        room = strip_reviewer_from_room(candidate, reviewer) or None

    rating_search = re.search(r"(\d+(?:\.\d+)?)\s*/\s*10", compact)
    if rating_search:
        rating = f"{rating_search.group(1)}/10"
        after = compact[rating_search.end():].strip()
        label = parse_rating_label(after)

    traveler = re.search(
        r"\b(Couple|Business traveler|Solo traveler|Family|Traveling with friends)\b",
        compact,
    )
    if traveler:
        traveler_type = traveler.group(1)

    return {
        "reviewer": reviewer,
        "room": room,
        "stay": stay,
        "traveler_type": traveler_type,
        "rating": rating,
        "label": label,
    }


def trim_to_review_metadata(value: str) -> str:
    cleaned = normalize_text(value)
    markers = [" Guest User ", " Show More ", " Response from Property "]
    best = -1
    marker_len = 0
    for marker in markers:
        idx = cleaned.rfind(marker)
        if idx > best:
            best = idx
            marker_len = len(marker) if marker.strip() != "Guest User" else 1
    if best >= 0:
        cleaned = cleaned[best + marker_len:].strip()
    if cleaned.startswith("Guest User"):
        return cleaned
    return cleaned


def infer_reviewer(text: str) -> str | None:
    cleaned = normalize_text(text)
    if "Show More" in cleaned:
        cleaned = cleaned.rsplit("Show More", 1)[-1].strip()
    if cleaned.startswith("Guest User"):
        return "Guest User"
    words = cleaned.split()
    if not words:
        return None
    return " ".join(words[:3]).strip() or None


def strip_reviewer_from_room(value: str, reviewer: str | None) -> str:
    room = normalize_text(value)
    if reviewer and room.startswith(reviewer):
        room = room[len(reviewer):].strip()
    return room


def parse_rating_label(value: str) -> str | None:
    cleaned = normalize_text(value)
    for label in ("Very good", "Outstanding", "Great", "Good", "Average", "Poor"):
        if cleaned.startswith(label):
            return label
    return cleaned.split()[0] if cleaned else None


def split_review_response(text: str) -> tuple[str, str | None]:
    cleaned = normalize_text(text)
    match = re.search(r"\bResponse from Property\s*:\s*", cleaned)
    if not match:
        return trim_review_text(cleaned), None
    review_text = cleaned[:match.start()]
    response = trim_property_response(cleaned[match.end():])
    return trim_review_text(review_text), response


def trim_property_response(text: str) -> str:
    cleaned = normalize_text(text)
    next_guest = cleaned.find(" Guest User ")
    if next_guest >= 0:
        cleaned = cleaned[:next_guest]
    for marker in ("Guest Relations Manager", "Misafir İlişkileri Müdürü", "Guest Services"):
        idx = cleaned.find(marker)
        if idx >= 0:
            cleaned = cleaned[:idx + len(marker)]
            break
    return trim_review_text(cleaned)


def trim_review_text(text: str) -> str:
    text = normalize_text(text)
    text = re.split(r"\bShow More\b", text)[0].strip()
    return text[:1800]


def parse_turkish_date(value: str) -> date:
    day, month_name, year = value.split()
    return date(int(year), TR_MONTHS[month_name], int(day))


def filter_recent_reviews(
    records: list[ReviewRecord],
    start_date: date,
    end_date: date,
) -> list[ReviewRecord]:
    recent = [record for record in records if start_date <= record.date <= end_date]
    return sorted(dedupe_reviews(recent), key=lambda record: record.date, reverse=True)


def dedupe_reviews(records: list[ReviewRecord]) -> list[ReviewRecord]:
    seen: set[tuple[str, str]] = set()
    unique: list[ReviewRecord] = []
    for record in records:
        key = (record.date.isoformat(), normalize_text(record.text)[:160])
        if key in seen:
            continue
        seen.add(key)
        unique.append(record)
    return unique


def looks_like_review_text(text: str) -> bool:
    lowered = text.lower()
    reject = ["otel yıldız puanı", "öneriler", "havalimanı", "metro"]
    if any(term in lowered for term in reject):
        return False
    return len(text) >= 12


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def sanitize_error(error: object) -> str:
    if error is None:
        return ""
    return normalize_text(str(error))[:300]
