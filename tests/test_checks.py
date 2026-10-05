"""Unit tests for checks.py. No model or database needed.

Run:  python tests/test_checks.py   (or: python -m pytest tests/)
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from checks import (cannot_error, check_sql, clarify_error, duplicates_suspicious,  # noqa: E402
                    find_reference, outside_coverage, previous_year_anchor, repeated_measures,
                    resolve_reference, small_talk_reply, empty_period_column, unknown_values,
                    wrong_result_shape)

FIRST, LAST = date(2016, 9, 4), date(2018, 9, 3)


def test_small_talk():
    for msg in ["hello", "Hi!", "hey there", "Thanks", "thank you so much", "Olá", "what can you do?",
                "heey how are you", "hiii", "good morning", "what's up", "thanks a lot!", "bye"]:
        assert small_talk_reply(msg, FIRST, LAST), msg
    assert small_talk_reply("heey how are you", FIRST, LAST).startswith("Hey! I'm doing great")
    assert small_talk_reply("good morning", FIRST, LAST).startswith("Good morning!")
    assert small_talk_reply("thanks a lot", FIRST, LAST).startswith("You're welcome")
    # Anything about the data, and answers to clarifying questions, are not small talk.
    for msg in ["hello, what was revenue in 2017?", "top sellers", "thanks, now break it down by state",
                "How many orders?", "how are sales doing in SP?", "yes", "ok", "no"]:
        assert not small_talk_reply(msg, FIRST, LAST), msg


def test_sql_must_read_a_table():
    # Real failure: "heey how are you" produced SELECT 1 AS greeting, shown as "greeting: 1".
    assert "reads no table" in check_sql("SELECT 1 AS greeting", "heey how are you")


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


# ---- SQL structure: real queries the model wrote in earlier eval runs ----------

FANOUT_AVG_PAID = """SELECT f.customer_state, ROUND(AVG(f.payment_total), 2) AS avg_amount_paid
FROM order_facts f JOIN sales s ON f.order_id = s.order_id
WHERE f.is_sale = TRUE GROUP BY f.customer_state ORDER BY avg_amount_paid DESC"""

REVIEWS_BY_SELLER_STATE = """SELECT s.seller_state, ROUND(AVG(f.review_score), 2) AS avg_score,
       COUNT(f.review_score) AS orders
FROM (SELECT DISTINCT order_id, seller_state FROM sales) s
JOIN order_facts f ON f.order_id = s.order_id
GROUP BY s.seller_state ORDER BY avg_score DESC"""

CHAIN_TURN3_OK = """WITH top_categories AS (
    SELECT category FROM sales WHERE purchase_year = 2017
    GROUP BY category ORDER BY SUM(revenue) DESC LIMIT 5)
SELECT c.category, s.customer_state, ROUND(SUM(s.revenue), 2) AS revenue
FROM sales s JOIN top_categories c ON s.category = c.category
JOIN order_facts f ON s.order_id = f.order_id
WHERE s.purchase_year = 2017 AND f.is_delivered = true
GROUP BY c.category, s.customer_state ORDER BY revenue DESC"""

SELLERS_BY_STATE = """SELECT seller_state, COUNT(DISTINCT order_id) AS orders
FROM sales GROUP BY seller_state ORDER BY orders DESC"""

SELLERS_BY_ID = """SELECT seller_id, seller_state, COUNT(DISTINCT order_id) AS orders
FROM sales GROUP BY seller_id, seller_state ORDER BY orders DESC LIMIT 10"""

CHAIN_TURN4_ROWS = """SELECT category, customer_state, purchase_year, ROUND(SUM(revenue), 2) AS revenue
FROM sales WHERE is_delivered AND purchase_year IN (2017, 2018)
GROUP BY category, customer_state, purchase_year ORDER BY category, customer_state, purchase_year"""

CHAIN_TURN4_COLUMNS = """SELECT category, customer_state,
       ROUND(SUM(CASE WHEN purchase_year = 2017 THEN revenue END), 2) AS revenue_2017,
       ROUND(SUM(CASE WHEN purchase_year = 2018 THEN revenue END), 2) AS revenue_2018
FROM sales WHERE is_delivered AND purchase_year IN (2017, 2018)
  AND category IN (SELECT category FROM sales WHERE purchase_year = 2017
                   GROUP BY category ORDER BY SUM(revenue) DESC LIMIT 5)
GROUP BY category, customer_state ORDER BY revenue_2018 DESC"""

TOP3_LIMIT_WRONG = """SELECT category, purchase_quarter, ROUND(SUM(revenue), 2) AS revenue
FROM sales WHERE purchase_year = 2018
GROUP BY category, purchase_quarter ORDER BY category, revenue DESC LIMIT 3"""

TOP3_SUBQUERY_OK = """SELECT category, purchase_quarter, ROUND(SUM(revenue), 2) AS revenue
FROM sales WHERE purchase_year = 2018 AND category IN (
    SELECT category FROM sales WHERE purchase_year = 2018
    GROUP BY category ORDER BY SUM(revenue) DESC LIMIT 3)
GROUP BY category, purchase_quarter ORDER BY category, purchase_quarter"""

ITEM_PRICES = "SELECT order_item_id, revenue FROM sales WHERE order_id = 'abc'"


def test_existing_guardrails_unchanged():
    assert "raw table" in check_sql("SELECT * FROM order_items")
    assert "Do not join sales with payments" in check_sql(
        "SELECT payment_type, SUM(revenue) FROM sales JOIN payments USING (order_id) GROUP BY 1")


def test_fanout_join_rejected():
    q = "Average amount paid per order by customer state, excluding canceled orders"
    assert "repeats each order" in check_sql(FANOUT_AVG_PAID, q)
    assert check_sql(REVIEWS_BY_SELLER_STATE, "Average review score by seller state") == ""
    assert check_sql(CHAIN_TURN3_OK, "Top 5 categories in 2017 by customer state, delivered only") == ""


def test_seller_grouping():
    q = "Who are our best sellers? (Clarification: most orders)"
    assert "individual sellers" in check_sql(SELLERS_BY_STATE, q)
    assert check_sql(SELLERS_BY_ID, q) == ""
    assert check_sql(SELLERS_BY_STATE, "Number of orders by seller state") == ""


def test_side_by_side():
    q = ("Compare the top 5 product categories by revenue in 2017, broken down by customer "
         "state and only counting delivered orders, with 2018 compared side by side.")
    assert "side by side" in check_sql(CHAIN_TURN4_ROWS, q)
    assert check_sql(CHAIN_TURN4_COLUMNS, q) == ""
    assert check_sql(CHAIN_TURN4_ROWS, "Revenue by category, state and year") == ""


def test_top_n_breakdown():
    q = "Top 3 categories by revenue in 2018, broken down by quarter"
    assert "subquery" in check_sql(TOP3_LIMIT_WRONG, q)
    assert check_sql(TOP3_SUBQUERY_OK, q) == ""
    assert check_sql(TOP3_LIMIT_WRONG, "Top 3 category-quarter combinations by revenue in 2018") == ""


def test_duplicates_only_suspicious_with_joins():
    assert not duplicates_suspicious(ITEM_PRICES)
    assert not duplicates_suspicious(CHAIN_TURN3_OK)          # has GROUP BY
    assert duplicates_suspicious("SELECT s.category FROM sales s JOIN order_facts f USING (order_id)")



def test_repeated_measures():
    grouped = "SELECT category, customer_state, SUM(a), SUM(b) FROM sales GROUP BY 1, 2"
    # Chain turn 4 bug: every state got the category's national totals.
    wrong = [("health_beauty", st, 473833.0, 755724.5) for st in ("RN", "AC", "PR", "RR")]
    right = [("bed_bath_table", "SP", 204224.73, 267983.44), ("bed_bath_table", "RJ", 77829.48, 90000.1),
             ("watches_gifts", "SP", 175097.73, 200000.0)]
    assert repeated_measures(grouped, wrong)
    assert not repeated_measures(grouped, right)
    # Small groups sharing one average are normal; so are identical row-level prices.
    assert not repeated_measures("SELECT category, AVG(s), COUNT(*) FROM t GROUP BY 1",
                                 [("a", 5.0, 1), ("b", 5.0, 2), ("c", 5.0, 1)])
    assert not repeated_measures(ITEM_PRICES, [(1, 21.33), (2, 21.33), (3, 21.33)])



# ---- references to the previous answer -------------------------------------------

TOP5_COLS = ["category", "revenue"]
TOP5_ROWS = [("bed_bath_table", 497970.94), ("watches_gifts", 486519.02), ("health_beauty", 481142.73),
             ("sports_leisure", 447546.59), ("computers_accessories", 400490.61)]
WORST_COLS = ["category", "avg_score", "orders"]
WORST_ROWS = [("security_and_services", 2.5, 2), ("pc_gamer", 3.43, 7), ("office_furniture", 3.62, 1262)]


def test_find_reference():
    assert find_reference("How many orders did it have?")["kind"] == "pointer"
    assert find_reference("What was its revenue?")["kind"] == "pointer"
    assert find_reference("How many orders did that seller have?")["kind"] == "pointer"
    assert find_reference("Average score for that category")["kind"] == "pointer"
    r = find_reference("What was the average review score of the second one?")
    assert r["kind"] == "ordinal" and r["n"] == 2
    assert find_reference("and the last one?")["n"] == -1
    assert find_reference("what about #3")["n"] == 3
    # "it" meaning the whole previous question is not an item reference.
    for msg in ["Break it down by customer state.", "Compare it with 2018", "How about this year?",
                "Only count orders that were actually delivered.", "Top 5 categories by revenue in 2017"]:
        assert find_reference(msg) is None, msg


def test_resolve_ordinal():
    kind, desc, values, filters = resolve_reference({"kind": "ordinal", "n": 2, "text": "second one"},
                                           TOP5_COLS, TOP5_ROWS, "Top 5 categories by revenue in 2017")
    assert kind == "resolved" and values == ["watches_gifts"] and "category watches_gifts" in desc
    assert filters == ["category = 'watches_gifts'"]
    assert resolve_reference({"kind": "ordinal", "n": -1, "text": "last one"},
                             TOP5_COLS, TOP5_ROWS, "x")[2] == ["computers_accessories"]
    assert resolve_reference({"kind": "ordinal", "n": 5, "text": "#5"}, WORST_COLS, WORST_ROWS, "x")[0] == "clarify"


def test_resolve_pointer():
    it = {"kind": "pointer", "text": "did it"}
    # A question asking for one item: "it" is the first row.
    assert resolve_reference(it, WORST_COLS, WORST_ROWS,
                             "Which category had the worst reviews?")[2] == ["security_and_services"]
    assert resolve_reference(it, ["seller_id", "revenue"], [("4869f7a5dfa277a7dca6462dcf3b52b2", 229237.63)],
                             "Which seller has the highest revenue?")[2] == ["4869f7a5dfa277a7dca6462dcf3b52b2"]
    # A list: "that category" is ambiguous, so ask, naming the options.
    kind, question, _, _ = resolve_reference({"kind": "pointer", "text": "that category"},
                                          TOP5_COLS, TOP5_ROWS, "Top 5 categories by revenue in 2017")
    assert kind == "clarify" and "watches_gifts" in question and "category watches" not in question
    # A single total has no item to point at.
    assert resolve_reference(it, ["revenue"], [(6108492.27,)], "What was our revenue in 2017?") is None


def test_previous_year_anchor():
    from datetime import date
    f, l = date(2016, 9, 4), date(2018, 9, 3)
    assert previous_year_anchor("What about the previous year?", "Top 3 categories by revenue in 2018", f, l) \
        == ("resolved", '"previous year" = 2017', ["2017"], ["purchase_year = 2017"])
    assert previous_year_anchor("And the year before?", "Which category had the worst reviews?", f, l)[0] == "clarify"
    assert previous_year_anchor("previous year?", "Compare 2017 with 2018", f, l)[0] == "clarify"
    assert previous_year_anchor("What was revenue last year?", "Revenue in 2018", f, l) is None  # data-relative



def test_empty_period_column():
    q = "Top 3 categories by revenue in 2017 compared side by side with 2018"
    cols = ["category", "revenue_2017", "revenue_2018"]
    # Real failure: LIMIT 3 on category-year rows kept only 2018 rows.
    assert "revenue_2017" in empty_period_column(q, cols, [("watches_gifts", 0.0, 708305.95),
                                                            ("health_beauty", 0.0, 770002.81)])
    assert empty_period_column(q, cols, [("bed_bath_table", 497970.94, 537514.13)]) == ""
    assert empty_period_column("Revenue by category", cols, [("x", 0.0, 1.0)]) == ""



def test_unknown_values():
    known = {"category": {"toys", "health_beauty"}, "customer_state": {"SP", "RJ"}}
    assert "Did you mean 'toys'" in unknown_values("SELECT 1 FROM sales s WHERE s.category = 'Toys'", known)
    assert "Did you mean 'health_beauty'" in unknown_values(
        "SELECT 1 FROM sales WHERE category IN ('toys', 'helth_beauty')", known)
    assert "'Sao Paulo' is not a value of customer_state" in unknown_values(
        "SELECT 1 FROM sales WHERE customer_state = 'Sao Paulo'", known)
    assert unknown_values("SELECT 1 FROM sales WHERE customer_state = 'SP' AND category = 'toys'", known) == ""



def test_grouping_by_an_aggregated_column():
    # Real failure: the average score per score value is just the score itself.
    bad = """SELECT ROUND(AVG(f.review_score), 2) AS avg_review_score, COUNT(f.review_score) AS orders
FROM order_facts f JOIN (SELECT DISTINCT order_id, category FROM sales WHERE category = 'watches_gifts') s
ON f.order_id = s.order_id GROUP BY f.review_score ORDER BY avg_review_score DESC"""
    assert "Remove review_score from GROUP BY" in check_sql(bad, "average review score of watches_gifts")
    assert check_sql(REVIEWS_BY_SELLER_STATE, "Average review score by seller state") == ""



def test_wrong_result_shape():
    q = "Top 3 categories by revenue in 2017 compared side by side with 2018"
    cols = ["category", "revenue_2017", "revenue_2018"]
    # Real failure: both columns were SUM(revenue) over both years.
    assert "identical in every row" in wrong_result_shape(q, cols, [
        ("health_beauty", 1251145.54, 1251145.54), ("watches_gifts", 1194824.97, 1194824.97)])
    assert wrong_result_shape(q, cols, [("bed_bath_table", 497970.94, 537514.13)]) == ""
    # Real failure: GROUP BY order_id gave one row per order, each COUNT = 1.
    per_order = [(5.0, 1)] * 6
    assert "unique id" in wrong_result_shape("Average review score of watches_gifts in 2017",
                                             ["avg_review_score", "orders"], per_order)
    assert wrong_result_shape("List each order with its review count", ["avg", "orders"], per_order) == ""
    assert wrong_result_shape("Orders by state", ["state", "orders"], [("AC", 1), ("AP", 3)]) == ""



def test_counting_items_as_orders():
    q = "How many orders did watches_gifts have in 2018 compared side by side with 2017?"
    # Real failure (Ollama run): SUM(CASE ... THEN 1) on sales counted items.
    bad = """SELECT SUM(CASE WHEN purchase_year = 2017 THEN 1 ELSE 0 END) AS orders_2017,
       SUM(CASE WHEN purchase_year = 2018 THEN 1 ELSE 0 END) AS orders_2018
FROM sales WHERE category = 'watches_gifts'"""
    good = """SELECT COUNT(DISTINCT CASE WHEN purchase_year = 2017 THEN order_id END) AS orders_2017,
       COUNT(DISTINCT CASE WHEN purchase_year = 2018 THEN order_id END) AS orders_2018
FROM sales WHERE category = 'watches_gifts'"""
    assert "counts items, not orders" in check_sql(bad, q)
    assert check_sql(good, q) == ""
    assert "counts items" in check_sql("SELECT COUNT(*) FROM sales WHERE purchase_year = 2017",
                                       "How many orders in 2017?")
    assert check_sql("SELECT COUNT(*) FROM order_facts WHERE purchase_year = 2017", "How many orders in 2017?") == ""
    assert check_sql("SELECT COUNT(*) FROM sales WHERE purchase_year = 2017", "How many items were sold in 2017?") == ""



def test_top_n_dropped():
    # Real failure: "top 5 ... broken down by customer state" returned every category.
    q = "Top 5 categories by revenue in 2017, broken down by customer state"
    no_limit = """SELECT category, s.customer_state, ROUND(SUM(s.revenue), 2) AS revenue
FROM sales s WHERE s.purchase_year = 2017 GROUP BY category, s.customer_state ORDER BY revenue DESC"""
    assert "returns every row" in check_sql(no_limit, q)
    assert check_sql(CHAIN_TURN3_OK, q) == ""
    assert check_sql(no_limit, "Revenue by category and customer state in 2017") == ""


if __name__ == "__main__":
    tests = [f for name, f in sorted(globals().items()) if name.startswith("test_")]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"{len(tests)} tests passed")
