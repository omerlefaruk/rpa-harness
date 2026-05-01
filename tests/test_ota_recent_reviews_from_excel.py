"""Unit tests for the OTA recent reviews workflow helpers."""

from __future__ import annotations

import importlib.util
import sys
from datetime import date
from pathlib import Path


MODULE_PATH = Path(__file__).parent / "rpa" / "ota_recent_reviews_from_excel.py"
SPEC = importlib.util.spec_from_file_location("ota_recent_reviews_from_excel", MODULE_PATH)
ota_reviews = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = ota_reviews
SPEC.loader.exec_module(ota_reviews)


def test_as_of_date_uses_configured_value():
    assert ota_reviews._as_of_date("2026-04-29") == date(2026, 4, 29)


def test_generic_review_extractor_reads_recent_review_date():
    text = (
        "Guest reviews Excellent stay. Posted by Guest User on Apr 15, 2026. "
        "Review: great hotel and friendly staff. Rating 5/5."
    )

    reviews = ota_reviews.extract_generic_recent_reviews(
        text,
        "https://example.test",
        start_date=date(2026, 3, 30),
        end_date=date(2026, 4, 29),
    )

    assert len(reviews) == 1
    assert reviews[0].date == date(2026, 4, 15)


def test_generic_review_extractor_ignores_property_response_date():
    text = (
        "8,0 Kusursuz Guest review Gym under rehabilitation and good stay. "
        "15 Nisan 2026 tarihinde yazıldı. Dear guest, thank you. "
        "Cevap verilme tarihi: 20 Nisan 2026."
    )

    reviews = ota_reviews.extract_generic_recent_reviews(
        text,
        "https://example.test",
        start_date=date(2026, 3, 30),
        end_date=date(2026, 4, 29),
    )

    assert [review.date for review in reviews] == [date(2026, 4, 15)]


def test_google_maps_reviews_url_adds_reviews_mode():
    url = (
        "https://www.google.com/maps/place/The+Marmara+Taksim/@41.0364342,28.9860905,17z/"
        "data=!4m9!3m8!1s0x14cab764e83b6691:0x424a7b3906d2a73e!"
        "5m2!4m1!1i2!8m2!3d41.0364342!4d28.9860905!16s%2Fg%2F12qhkv305?hl=en"
    )

    reviews_url = ota_reviews.google_maps_reviews_url(url)

    assert "!4m11!3m10" in reviews_url
    assert "!9m1!1b1!16s" in reviews_url


def test_relative_month_review_dates_are_accepted():
    text = (
        "Google review summary All reviews Most relevant "
        "Ezo Smith 5/5 a month ago on Google Booked this trip for my mum and "
        "the hotel team was excellent. Review response from the owner."
    )

    reviews = ota_reviews.extract_generic_recent_reviews(
        text,
        "https://example.test",
        start_date=date(2026, 3, 30),
        end_date=date(2026, 4, 29),
    )

    assert len(reviews) == 1
    assert reviews[0].date == date(2026, 3, 30)


def test_google_review_extractor_splits_adjacent_reviews():
    text = (
        "Google review summary All reviews Most relevant Trip.com Member "
        " 5/5 6 months ago on Trip.com Older third party review. "
        "Ezo Smith 6 reviews · 2 photos  5/5 a month ago on Google "
        "Booked this trip for my mum and the hotel team was excellent. "
        "Response from the owner a month ago Thank you. "
        "AK KA 2 reviews  5/5 a month ago on Google "
        "Had a great stay at the hotel. The rooms were clean and staff was helpful. "
        " Like Share"
    )

    reviews = ota_reviews.extract_google_recent_reviews(
        text,
        "https://maps.google.test/reviews",
        start_date=date(2026, 3, 30),
        end_date=date(2026, 4, 29),
    )

    assert [review.reviewer for review in reviews] == ["Ezo Smith", "AK KA"]
    assert reviews[0].text == "Booked this trip for my mum and the hotel team was excellent."
    assert reviews[1].text == "Had a great stay at the hotel. The rooms were clean and staff was helpful."
