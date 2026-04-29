"""Unit tests for the repeatable Trip.com Marmara Taksim review extraction."""

from __future__ import annotations

import importlib.util
import sys
from datetime import date
from pathlib import Path


MODULE_PATH = Path(__file__).parent / "browser" / "trip_marmara_taksim_reviews.py"
SPEC = importlib.util.spec_from_file_location("trip_marmara_taksim_reviews", MODULE_PATH)
trip_reviews = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = trip_reviews
SPEC.loader.exec_module(trip_reviews)


def test_extract_english_review_records_parses_posted_reviews():
    text = """
    Guest User
    Deluxe Room With City View Non Smoking
    Stayed in Apr 2026
    Business traveler
    4 review
    8.5 / 10
    Very good
    Posted on Apr 27, 2026
    Stayed in hotel for weekend. Location is good, breakfast is average.
    Response from Property : Dear Guest, thank you for your review.
    Guest User
    Corner Room With City View Non Smoking
    Stayed in Apr 2026
    Couple
    6.5 / 10
    Posted on Apr 11, 2026
    Second review text.
    """

    records = trip_reviews.extract_review_records(text, "https://example.test/review.html")

    assert len(records) == 2
    assert records[0].date == date(2026, 4, 27)
    assert records[0].reviewer == "Guest User"
    assert records[0].room == "Deluxe Room With City View Non Smoking"
    assert records[0].rating == "8.5/10"
    assert records[0].label == "Very good"
    assert records[0].traveler_type == "Business traveler"
    assert "Location is good" in records[0].text
    assert "Second review text" not in records[0].text
    assert "thank you" in records[0].property_response
    assert "Corner Room" not in records[0].property_response


def test_extract_turkish_summary_reviews_parses_public_hotel_snippets():
    text = """
    Misafirler ne diyor? M‍i‍s‍a‍f‍i‍r‍ ‍K‍u‍l‍l‍a‍n‍ı‍c‍ı
    30 Mart 2026
    Harika bir deneyimde. En ufak bir olumsuzluk olmadı. Tavsiye ederim.
    M‍i‍s‍a‍f‍i‍r‍ ‍K‍u‍l‍l‍a‍n‍ı‍c‍ı
    29 Ocak 2026
    Merkezi konum giriş çıkış saatleri temizliği karşılamada güzel yüzlü personel iyiydi
    Hizmetler ve Olanaklar
    """

    records = trip_reviews.extract_review_records(text, "https://example.test/hotel")

    assert records[0].date == date(2026, 3, 30)
    assert "Harika bir deneyimde" in records[0].text


def test_filter_recent_reviews_sorts_and_deduplicates():
    records = [
        trip_reviews.ReviewRecord(
            date=date(2026, 4, 4),
            source_url="a",
            reviewer=None,
            room=None,
            stay=None,
            traveler_type=None,
            rating=None,
            label=None,
            text="same",
        ),
        trip_reviews.ReviewRecord(
            date=date(2026, 4, 27),
            source_url="a",
            reviewer=None,
            room=None,
            stay=None,
            traveler_type=None,
            rating=None,
            label=None,
            text="new",
        ),
        trip_reviews.ReviewRecord(
            date=date(2026, 4, 4),
            source_url="b",
            reviewer=None,
            room=None,
            stay=None,
            traveler_type=None,
            rating=None,
            label=None,
            text="same",
        ),
    ]

    recent = trip_reviews.filter_recent_reviews(
        records,
        date(2026, 3, 30),
        date(2026, 4, 29),
    )

    assert [record.date for record in recent] == [date(2026, 4, 27), date(2026, 4, 4)]


def test_fetch_public_text_with_status_retries_transient_failure(monkeypatch):
    calls = {"count": 0}

    def fake_fetch(_url):
        calls["count"] += 1
        if calls["count"] == 1:
            raise TimeoutError("temporary timeout")
        return "<html>The Marmara Taksim 30 Mart 2026 iyi</html>"

    monkeypatch.setattr(trip_reviews, "fetch_public_text_once", fake_fetch)

    text, status = trip_reviews.fetch_public_text_with_status("https://example.test")

    assert "The Marmara Taksim" in text
    assert status["status"] == "loaded"
    assert status["attempts"] == 2


def test_fetch_public_text_with_status_reports_failure(monkeypatch):
    def fake_fetch(_url):
        raise TimeoutError("network did not settle")

    monkeypatch.setattr(trip_reviews, "fetch_public_text_once", fake_fetch)

    text, status = trip_reviews.fetch_public_text_with_status("https://example.test")

    assert text == ""
    assert status["status"] == "failed"
    assert status["attempts"] == trip_reviews.MAX_SOURCE_ATTEMPTS
    assert "network did not settle" in status["error"]
