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
