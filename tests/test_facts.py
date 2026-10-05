"""Unit tests for facts.py. No model or database needed.

Run:  python tests/test_facts.py   (or: python -m pytest tests/)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from facts import drop_filler, key_facts, small_summary, superlatives_ok  # noqa: E402

# Monthly revenue in SP for 2017 (real values; November is the peak).
MONTHLY_COLS = ["purchase_month", "revenue"]
MONTHLY_ROWS = [(1, 41485.2), (2, 82314.5), (3, 128233.1), (4, 120333.4), (5, 172331.9),
                (6, 151231.7), (7, 185331.0), (8, 197332.6), (9, 205339.8), (10, 226121.73),
                (11, 355815.0), (12, 280099.34)]


def test_small_results_summarised_in_code():
    assert small_summary(["n"], []) == "No matching data was found."
    assert small_summary(["delivered_orders"], [(43428,)]) == "delivered orders: 43,428."
    text = small_summary(["category", "revenue"], [("bed_bath_table", 497970.94), ("watches_gifts", 486519.02)])
    assert "bed_bath_table (revenue 497,970.94)" in text and "watches_gifts (revenue 486,519.02)" in text
    assert small_summary(MONTHLY_COLS, MONTHLY_ROWS) is None  # > 5 rows: the model writes it


def test_small_group_warning():
    text = small_summary(["category", "avg_score", "orders"],
                         [("security_and_services", 2.5, 2), ("pc_gamer", 3.43, 7), ("office_furniture", 3.62, 1262)])
    assert "far fewer orders" in text and "as few as 2" in text


def test_key_facts_use_month_names():
    f = key_facts(MONTHLY_COLS, MONTHLY_ROWS)[0]
    assert f["high"] == ("November", "355,815.00") and f["low"] == ("January", "41,485.20")


def test_superlative_check_catches_wrong_peak():
    facts = key_facts(MONTHLY_COLS, MONTHLY_ROWS)
    wrong = ("Monthly revenue ranged from 41,485.20 in January to a peak of 355,815.00 in November. "
             "The highest recorded figure was 226,121.73 in October.")  # what the model wrote
    right = "Revenue peaked in November at 355,815.00; the lowest month was January at 41,485.20."
    assert not superlatives_ok(wrong, facts)
    assert superlatives_ok(right, facts)
    assert superlatives_ok("The top 3 months were November, December and October.", facts)


def test_drop_filler():
    text = ("In 2017, 43,428 orders were delivered. This figure represents the complete count "
            "found in the result table. No further calculations were made.")
    assert drop_filler(text) == "In 2017, 43,428 orders were delivered."


if __name__ == "__main__":
    tests = [f for name, f in sorted(globals().items()) if name.startswith("test_")]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"{len(tests)} tests passed")
