"""Code-level checks on the model's decisions.

A 4B model decides badly between answering, asking a clarifying question and
refusing: it reacts to trigger words ("top", "amount paid") instead of the
whole rule, and every prompt edit moves the line. These functions make those
decisions checkable in code. They use general sales vocabulary, not phrases
from the eval questions, and they need no model call.

Each check returns '' (fine) or a short error message that is sent back to the
model so it can retry.
"""
import re
import unicodedata

YEAR = re.compile(r"\b(?:19|20)\d{2}\b")


def plain(text: str) -> str:
    """Lowercase, accents removed, so 'São Paulo' and 'sao paulo' match."""
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()


# ---- small talk -----------------------------------------------------------

SMALL_TALK = re.compile(
    r"^(hi|hello|hey|hiya|hola|ola|good (morning|afternoon|evening)|thanks?( you)?|thank you|"
    r"thx|cheers|bye|goodbye|how are you|who are you|what can you do|help)"
    r"( there| everyone| so much| very much)?$"
)


def small_talk_reply(message: str, first_date, last_date) -> str:
    """A fixed reply for greetings and thanks, so they never reach SQL generation."""
    words = re.sub(r"[^a-z ]", " ", plain(message))
    if not SMALL_TALK.match(" ".join(words.split())):
        return ""
    return ("I answer questions about Olist's sales data: orders, revenue, product categories, "
            f"sellers, customers, deliveries, payments and reviews, from {first_date} to "
            f"{last_date}. For example: \"Top 5 categories by revenue in 2017\" or "
            "\"Average review score by customer state\".")


# ---- years the data does not cover ----------------------------------------

def outside_coverage(question: str, years: set[int], first_date, last_date) -> str:
    """Refuse in code when every year the question names is outside the data."""
    asked = {int(y) for y in YEAR.findall(question)}
    if not asked or asked & years:
        return ""
    missing = ", ".join(str(y) for y in sorted(asked))
    return (f"The data only covers {first_date} to {last_date}, so there is no data for "
            f"{missing}.")


# ---- clarifying questions ---------------------------------------------------

# A clarifying question is only justified for a vague ranking...
VAGUE_RANKING = re.compile(
    r"\b(best|top|worst|biggest|largest|smallest|leading|strongest|weakest|"
    r"(most|least) popular|popular|performing|performers?|performance)\b"
)
# ...that does not already say what to measure.
MEASURE = re.compile(
    r"\bby (revenue|sales|orders|units|volume|value|reviews?|ratings?|scores?|price|payments?)\b"
    r"|\b(revenue|turnover|units sold|sold|number of|how many|count of|order count|"
    r"(most|fewest|more|fewer) orders|reviews?|review scores?|ratings?|rated|"
    r"paid|payments?|installments?|freight|deliver\w*|late|prices?)\b"
)


def clarify_error(question: str) -> str:
    """Error if a clarifying question is not justified, else ''."""
    q = plain(question)
    if MEASURE.search(q):
        return ("Do not ask a clarifying question: the question already says what to "
                "measure. Reply with SQL.")
    if not VAGUE_RANKING.search(q):
        return ("Do not ask a clarifying question: this is not a vague ranking. Answer it "
                "directly with SQL, using all available data for anything not specified.")
    return ""


# ---- refusals -----------------------------------------------------------------

# Topics the data really does not have: a refusal for these is accepted at once.
OUT_OF_SCOPE = re.compile(
    r"\b(profit\w*|margins?|costs?|expenses?|marketing|advertis\w*|campaigns?|ad spend|"
    r"traffic|visits?|visitors?|clicks?|sessions?|conversions?|ages?|gender|income|"
    r"inventory|stock|warehouses?|forecast\w*|predict\w*|projections?|future|"
    r"employees?|salar\w*|weather)\b"
)
# Things the data does have, with where to find them (sent back as a hint).
IN_DATA = [
    (r"\b(payments?|paid|pay|installments?|boleto|credit card|voucher)\b",
     "payments (payment_type, payment_installments, payment_value) and "
     "order_facts.payment_total"),
    (r"\b(reviews?|ratings?|rated|scores?)\b", "order_facts.review_score"),
    (r"\b(deliver\w*|late|on time|shipping|ship\w*)\b",
     "order_facts (delivery_status, delivery_days, is_delivered)"),
    (r"\b(prices?|items?|revenue|sales|sold|units?)\b",
     "sales (revenue = item price, one row per order item)"),
    (r"\bsellers?\b", "sales (seller_id, seller_state, seller_city)"),
    (r"\bcustomers?\b", "sales / order_facts (customer_unique_id, customer_state)"),
    (r"\b(categor\w*|products?)\b", "sales (category, product_id)"),
    (r"\bfreight\b", "sales.freight_value and order_facts.freight"),
    (r"\b(orders?|status|cancel\w*)\b", "order_facts (order_status, is_canceled)"),
]


def cannot_error(question: str) -> str:
    """Error if a refusal looks wrong because the data has what was asked, else ''."""
    q = plain(question)
    if OUT_OF_SCOPE.search(q):
        return ""
    hints = [hint for pattern, hint in IN_DATA if re.search(pattern, q)]
    if not hints:
        return ""
    return ("This looks answerable from the data: " + "; ".join(dict.fromkeys(hints))
            + ". Reply with SQL unless it truly needs data that does not exist.")


# ---- SQL structure ------------------------------------------------------------
# The prompt states these rules too, but a 4B model follows them only sometimes.
# Mistakes guarded here are rejected on every attempt: a wrong query must not
# turn into a confident wrong number.

# Raw tables that the cleaned views replace. Querying them bypasses the
# data-quality rules (e.g. joining customers on customer_unique_id fans out).
RAW_TABLES = {"customers", "products", "sellers", "order_items",
              "category_translation", "reviews"}
TABLE_REF = re.compile(r"\b(?:from|join)\s+([a-z_][a-z0-9_]*)", re.IGNORECASE)

# order_facts columns holding one value per order. Joined to sales (one row
# per item) they repeat once per item unless order ids are de-duplicated first.
PER_ORDER_VALUES = re.compile(
    r"\b(payment_total|review_score|delivery_days|freight|order_revenue|n_items)\b", re.I)
COMPARE = re.compile(r"side by side|\bcompar\w*|\bversus\b|\bvs\b")
TOP_N = re.compile(r"\btop \d+\b")
BREAKDOWN = re.compile(r"broken down|break\w* (it |that |this )?down|"
                       r"\b(per|for each|each) (quarter|month|year|state|category)\b")


def _main_group_by(sql: str) -> str:
    """The last GROUP BY clause (the outer query's, in practice), lowercased."""
    parts = re.split(r"\bgroup\s+by\b", sql, flags=re.I)
    if len(parts) < 2:
        return ""
    return re.split(r"\b(order\s+by|having|limit|qualify)\b|\)", parts[-1], flags=re.I)[0].lower()


def check_sql(sql: str, question: str = "") -> str:
    """Return an error message if the SQL breaks a guardrail, else ''."""
    used = {t.lower() for t in TABLE_REF.findall(sql)}
    q = plain(question)
    low = sql.lower()
    group_by = _main_group_by(sql)

    raw = sorted(used & RAW_TABLES)
    if raw:
        return (f"Do not use the raw table(s) {', '.join(raw)}. Use the sales view "
                "(it already has customer, seller and category columns) or order_facts "
                "(one row per order, with delivery, payment and review columns).")
    if "sales" in used and "payments" in used:
        return ("Do not join sales with payments: an order with several items and several "
                "payments multiplies rows and inflates totals. For payment questions use "
                "payments joined to order_facts (for dates and status) only.")
    if ("sales" in used and "order_facts" in used and PER_ORDER_VALUES.search(sql)
            and not re.search(r"distinct\s+order_id", low)):
        return ("Joining sales (one row per item) to order_facts repeats each order's values "
                "once per item and skews totals and averages. Use order_facts alone, or join "
                "it to (SELECT DISTINCT order_id, <column> FROM sales).")
    if (re.search(r"\bsellers?\b", q) and not re.search(r"\b(states?|cit(y|ies)|regions?)\b", q)
            and re.search(r"\bseller_(state|city)\b", group_by) and "seller_id" not in low):
        return ("'Sellers' means individual sellers: group by seller_id (you may add "
                "seller_state as an extra column), not by seller_state or seller_city.")
    if (COMPARE.search(q) and len(set(YEAR.findall(q))) >= 2
            and re.search(r"\bpurchase_year\b", group_by)):
        return ("Show the periods side by side: one column per period using conditional "
                "aggregation (e.g. SUM(CASE WHEN purchase_year = 2017 THEN revenue END) AS "
                "revenue_2017), and do not group by purchase_year. Order by the latest "
                "period's value, highest first.")
    if (TOP_N.search(q) and BREAKDOWN.search(q) and low.count("select") == 1
            and re.search(r"\blimit\b", low) and "," in group_by):
        return ("LIMIT on the broken-down rows keeps the wrong rows. First pick the top N in a "
                "subquery (WHERE x IN (SELECT x ... ORDER BY ... LIMIT N)), then group by both "
                "columns without a LIMIT.")
    return ""


def duplicates_suspicious(sql: str) -> bool:
    """Duplicate result rows only suggest a bad join when there is a join and nothing
    (GROUP BY, DISTINCT) that should have made the rows unique."""
    low = sql.lower()
    return bool(re.search(r"\bjoin\b", low)) and not re.search(r"\bgroup\s+by\b|\bdistinct\b", low)


def repeated_measures(sql: str, rows: list[tuple]) -> bool:
    """True when a grouped result repeats the same measures under different labels.

    E.g. every customer state showing the category's national total: the grouping
    column was joined on too few keys. Needs 2+ decimal values per row, so small
    groups that happen to share one average (say 5.00) do not trigger it.
    """
    if not re.search(r"\bgroup\s+by\b", sql, re.I):
        return False
    seen: dict[tuple, int] = {}
    for row in rows:
        measures = tuple(v for v in row if isinstance(v, float) and v)
        if len(measures) >= 2:
            seen[measures] = seen.get(measures, 0) + 1
    return any(n >= 3 for n in seen.values())
