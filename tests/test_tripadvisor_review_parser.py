from datetime import date

from tests.browser.tripadvisor_marmara_taksim_reviews import parse_tripadvisor_reviews


def test_parse_tripadvisor_reviews_classifies_exact_last_30_day_dates():
    text = """
Maggie wrote a review Apr 7
Amazing stay in Istanbul
The staff were helpful.
Date of stay: April 2026

Shanel P wrote a review March 2026
Incredible Stay!
Date of stay: March 2026

Rached F wrote a review Dec 15, 2025
thumbs-up
Date of stay: December 2025
"""

    reviews = parse_tripadvisor_reviews(text, today=date(2026, 4, 29))

    assert reviews[0]["published_date"] == "2026-04-07"
    assert reviews[0]["in_last_30_days"] is True
    assert reviews[1]["published_date"] is None
    assert reviews[1]["in_last_30_days"] is None
    assert reviews[2]["published_date"] == "2025-12-15"
    assert reviews[2]["in_last_30_days"] is False
