"""Unit tests for checks.py. No model or database needed.

Run:  python tests/test_checks.py   (or: python -m pytest tests/)
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from checks import cannot_error, clarify_error, outside_coverage, small_talk_reply  # noqa: E402

FIRST, LAST = date(2016, 9, 4), date(2018, 9, 3)


def test_small_talk():
    for msg in ["hello", "Hi!", "hey there", "Thanks", "thank you so much", "Olá", "what can you do?"]:
        assert small_talk_reply(msg, FIRST, LAST), msg
    for msg in ["hello, what was revenue in 2017?", "top sellers", "thanks, now break it down by state",
                "How many orders?"]:
        assert not small_talk_reply(msg, FIRST, LAST), msg


def test_outside_coverage():
    years = {2016, 2017, 2018}
    assert outside_coverage("What was our revenue in 2020?", years, FIRST, LAST)
    assert outside_coverage("Orders in 2015 vs 2019", years, FIRST, LAST)
    assert not outside_coverage("Revenue in 2017", years, FIRST, LAST)
    assert not outside_coverage("Compare 2018 with 2019", years, FIRST, LAST)  # 2018 exists
    assert not outside_coverage("Top categories by revenue", years, FIRST, LAST)


def test_clarify_allowed_for_vague_rankings():
    for q in ["Who are our best sellers?", "Which products are most popular?",
              "What are our top categories?", "Which states perform best?",
              "Show me the worst sellers"]:
        assert clarify_error(q) == "", q


def test_clarify_blocked_when_measure_given():
    for q in ["Top 3 sellers by number of orders", "Which categories have the worst reviews?",
              "Best sellers by revenue", "Top products by units sold",
              "Who are our best sellers? (Clarification: most orders)",
              "Which states have the lowest review scores?", "Top states by amount paid"]:
        assert "already says what to measure" in clarify_error(q), q


def test_clarify_blocked_when_not_a_ranking():
    for q in ["List the price of every item in order abc", "How did São Paulo do last quarter?",
              "Monthly orders in 2017"]:
        assert clarify_error(q), q


def test_cannot_accepted_for_missing_data():
    for q in ["What was our profit margin last year?", "What is the age distribution of customers?",
              "How much did we spend on marketing?", "Forecast revenue for next year",
              "What is our website traffic?", "How much inventory do sellers hold?", "hello there"]:
        assert cannot_error(q) == "", q


def test_cannot_rechecked_when_data_exists():
    for q in ["Total amount paid by payment type", "List the price of every item in order abc",
              "Average review score by category", "How many deliveries were late?",
              "Which sellers have the most orders?"]:
        assert cannot_error(q).startswith("This looks answerable"), q
    assert "payment_type" in cannot_error("Total amount paid by payment type")


if __name__ == "__main__":
    tests = [f for name, f in sorted(globals().items()) if name.startswith("test_")]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"{len(tests)} tests passed")
