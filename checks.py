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
# Greetings, thanks and "how are you" get a natural reply in code; they never
# reach SQL generation. A message counts as small talk only if EVERY word is
# conversational, so "hey, what was revenue in 2017?" still goes to the model.
# "yes", "no" and "ok" are left out on purpose: they answer clarifying questions.


def _squash(text: str) -> str:
    """Collapse stretched letters ("heey" -> "hey", "hellooo" -> "helo") for matching."""
    return re.sub(r"(.)\1+", r"\1", text)


CASUAL_WORDS = {_squash(w) for w in """
    hi hey hello hiya howdy hola ola yo sup heya there everyone all folks guys friend buddy
    good morning afternoon evening day
    how are you u r doing going is it things whats what up hows
    thanks thank thx ty cheers much lot a so very appreciate appreciated
    bye goodbye later see soon night
    nice great cool awesome to meet
    who can do help me please assistant
""".split()}
WELLBEING = re.compile(r"\bhow (are|r) (you|u)\b|\bhow is it going\b|\bhows it going\b|\bhow are things\b"
                       r"|\bwhats up\b|\bwhat up\b|\bsup\b|\bhow (you|u) doing\b")
CAPABILITIES = re.compile(r"\bwho are (you|u)\b|\bwhat can (you|u) do\b|\bhelp\b")


def small_talk_reply(message: str, first_date, last_date) -> str:
    """A natural reply for greetings and casual messages, or '' if it isn't one."""
    text = " ".join(re.sub(r"[^a-z ]", " ", plain(message).replace("'", "")).split())
    words = text.split()
    if not words or len(words) > 8 or not all(_squash(w) in CASUAL_WORDS for w in words):
        return ""
    t = _squash(text)
    examples = ('You can ask me things like "Top 5 categories by revenue in 2017" or '
                '"Which categories have the worst reviews?"')
    if CAPABILITIES.search(text):
        return ("I'm a sales analytics assistant for Olist's data: orders, revenue, product "
                f"categories, sellers, customers, deliveries, payments and reviews, from {first_date} "
                f"to {last_date}. I turn your question into SQL, run it, and explain the result. "
                + examples)
    if re.search(r"\b(thanks|thank|thx|ty|cheers|apreciate|apreciated)\b", t):
        return "You're welcome! Is there anything else you'd like to know about the sales data?"
    if re.search(r"\b(bye|godbye|later|night)\b", t):
        return "Bye! Come back any time you have a question about the sales data."
    greeting = next((f"Good {p}!" for p in ("morning", "afternoon", "evening") if p in t), "Hey!")
    if WELLBEING.search(_squash(text)) or WELLBEING.search(text):
        return f"{greeting} I'm doing great, thanks for asking. How can I help you today? {examples}"
    return f"{greeting} How can I help you today? {examples}"


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


def main_group_by(sql: str) -> str:
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
    group_by = main_group_by(sql)

    if not used:
        return ("The query reads no table, so it can't answer a question about the data. Query "
                "the tables, or reply CANNOT if the message isn't about the sales data.")
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
                "it to (SELECT DISTINCT order_id, <column> FROM sales WHERE <your filters on "
                "sales columns>). Keep every filter you had.")
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
    if ("sales" in used and re.search(r"\borders?\b", q) and not re.search(r"\b(items?|units?)\b", q)
            and re.search(r"count\s*\(\s*\*\s*\)|sum\s*\(\s*case\b.*?\bthen\s+1\b", low, re.S)
            and not re.search(r"select\s+distinct\s+order_id", low)):
        return ("sales has one row per item, so COUNT(*) or SUM(CASE ... THEN 1) counts items, not "
                "orders. Count orders with COUNT(DISTINCT order_id), or per period with "
                "COUNT(DISTINCT CASE WHEN purchase_year = 2017 THEN order_id END).")
    grouped = {c.strip().split(".")[-1] for c in group_by.split(",") if c.strip()}
    aggregated = {m.lower() for m in re.findall(
        r"\b(?:avg|sum|min|max)\s*\(\s*(?:\w+\.)?(\w+)\s*\)", sql, re.I)}
    both = sorted(grouped & aggregated)
    if both:
        return (f"You group by {', '.join(both)} and also aggregate it, so each group only "
                f"repeats its own value. Remove {', '.join(both)} from GROUP BY.")
    n = TOP_N.search(q)
    if n and not re.search(r"\blimit\b|row_number|\brank\s*\(|dense_rank|\bqualify\b", low):
        return (f"The question asks for the {n.group(0)}, but the query returns every row. Keep "
                f"only the {n.group(0)}: ORDER BY the measure DESC LIMIT N, or, when breaking "
                "down, pick them in a subquery (WHERE x IN (SELECT x ... LIMIT N)).")
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


# ---- references to the previous answer ------------------------------------------
# The rewrite model never sees previous result rows. Code finds the reference,
# resolves it to ONE value from the stored result, and only that value is handed
# to the rewrite, so other rows cannot leak into the new question.

ORDINALS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "last": -1}
ENTITY_NOUNS = (r"(one|ones|item|seller|sellers|category|categories|state|states|"
                r"product|products|customer|customers|city|cities|month|quarter)")
ORDINAL_REF = re.compile(
    r"\b(first|second|third|fourth|fifth|last)\s+" + ENTITY_NOUNS + r"\b"
    r"|(?:\bnumber|\bno\.|#)\s*([1-5])\b")
# "it" only as the thing being measured ("did it have", "its revenue"), not as
# the whole previous question ("break it down", "compare it with 2018").
POINTER_REF = re.compile(
    r"\b(did|does|do|was|is|has|had)\s+it\b|\bit\s+(had|has|have|sold|sell|got|get|made|make)\b"
    r"|\bits\s+[a-z]"
    r"|\b(that|this|those|these|the same)\s+" + ENTITY_NOUNS + r"\b")
PREVIOUS_YEAR = re.compile(r"\b(previous|prior|preceding)\s+year\b|\bthe year before\b"
                           r"|\ba year (earlier|before)\b")
SINGULAR_QUESTION = re.compile(
    r"\b(which|what)\s+[a-z_]*[^s\W]\s+(has|had|is|was|did|does|got|made|sold)\b"
    r"|\bwho\s+(is|was)\b|\bwhich\s+(one|seller|category|state|product|customer|city)\b")


def find_reference(message: str) -> dict | None:
    """A reference to an item of the previous answer, or None."""
    q = plain(message)
    m = ORDINAL_REF.search(q)
    if m:
        n = ORDINALS[m.group(1)] if m.group(1) else int(m.group(3))
        return {"kind": "ordinal", "n": n, "text": m.group(0)}
    m = POINTER_REF.search(q)
    if m:
        return {"kind": "pointer", "text": m.group(0)}
    return None


def _describe(columns, row, labels) -> tuple[str, list[str], list[str]]:
    """For one result row: a description ('category watches_gifts'), the values
    that must reach the question, and the SQL filters that select it."""
    parts, values, filters = [], [], []
    for i in labels:
        value = row[i]
        if value is None:
            continue
        parts.append(f"{columns[i]} {value}")
        values.append(str(value))
        filters.append(f"{columns[i]} = '{value}'" if isinstance(value, str)
                       else f"{columns[i]} = {value}")
    return " and ".join(parts), values, filters


def resolve_reference(ref: dict, columns: list[str], rows: list[tuple],
                      previous_question: str) -> tuple[str, str, list[str], list[str]] | None:
    """Resolve a reference against the previous result.

    Returns ("resolved", description, values, sql_filters), ("clarify", question,
    [], []), or None when the previous answer has no item labels (e.g. a total).
    """
    from facts import roles  # local import: facts does not depend on checks
    labels, _ = roles(columns, rows)
    labels = [i for i in labels if not re.search(r"(^|_)(year|quarter|month)$", columns[i].lower())] \
        or labels
    if not rows or not labels:
        return None

    def options():
        # Values only ("bed_bath_table, watches_gifts or ..."), not column names.
        names = [" / ".join(_describe(columns, r, labels)[1]) for r in rows[:5]]
        return ", ".join(names[:-1]) + (" or " if len(names) > 1 else "") + names[-1]

    if ref["kind"] == "ordinal":
        n = ref["n"]
        if n == -1:
            n = len(rows)
        if n > len(rows):
            return ("clarify", f"The previous answer only had {len(rows)} rows. "
                    f"Which one do you mean: {options()}?", [], [])
        desc, values, filters = _describe(columns, rows[n - 1], labels)
        return ("resolved", f'"{ref["text"]}" = {desc}', values, filters)

    # A pointer ("it", "that seller"): unambiguous only for a single-row answer or
    # a question that asked for one item; a list needs a clarifying question.
    if len(rows) == 1 or (SINGULAR_QUESTION.search(plain(previous_question))
                          and not TOP_N.search(plain(previous_question))):
        desc, values, filters = _describe(columns, rows[0], labels)
        return ("resolved", f'"{ref["text"]}" = {desc}', values, filters)
    return ("clarify", f"Which one do you mean: {options()}?", [], [])


def previous_year_anchor(message: str, previous_question: str,
                         first_date, last_date) -> tuple[str, str, list[str], list[str]] | None:
    """Resolve "the previous year" from the year in the previous question."""
    if not PREVIOUS_YEAR.search(plain(message)):
        return None
    years = sorted({int(y) for y in YEAR.findall(previous_question)})
    if len(years) == 1:
        y = years[0] - 1
        return ("resolved", f'"previous year" = {y}', [str(y)], [f"purchase_year = {y}"])
    if years:
        return ("clarify", f"Previous to which year: {' or '.join(map(str, years))}?", [], [])
    return ("clarify", "Which year should I use? The previous question covered all the data "
                       f"({first_date} to {last_date}).", [], [])


# ---- result and value grounding ---------------------------------------------------

def empty_period_column(question: str, columns: list[str], rows: list[tuple]) -> str:
    """Error if a side-by-side comparison has a period column that is empty everywhere
    (typically: the top N was picked from both periods' rows together)."""
    q = plain(question)
    years = set(YEAR.findall(q))
    if not rows or not (COMPARE.search(q) and len(years) >= 2):
        return ""
    period_cols = [i for i, col in enumerate(columns) if any(y in col for y in years)]
    for i in period_cols:
        if all(r[i] in (None, 0, 0.0) for r in rows):
            return (f"The column {columns[i]} is empty in every row: the top N was probably "
                    "picked from both periods together. Pick the top N for the period the "
                    "question ranks by in a subquery first, then show each period as its own "
                    "column.")
    return ""


def wrong_result_shape(question: str, columns: list[str], rows: list[tuple]) -> str:
    """Results that are never a correct answer, rejected on every attempt:
    - two period columns of a comparison identical in every row (the per-period
      condition is missing, so each holds the combined total);
    - a grouped result where a count column is 1 in every row (it grouped by a
      unique id such as order_id), unless the user asked for a per-item list."""
    q = plain(question)
    years = set(YEAR.findall(q))
    if rows and COMPARE.search(q) and len(years) >= 2:
        period_cols = [i for i, col in enumerate(columns) if any(y in col for y in years)]
        for a, b in [(a, b) for a in period_cols for b in period_cols if a < b]:
            if all(r[a] == r[b] for r in rows):
                return (f"{columns[a]} and {columns[b]} are identical in every row, so the "
                        "year condition is missing. Compute each column with its own period, "
                        "e.g. SUM(CASE WHEN purchase_year = 2017 THEN revenue END) AS revenue_2017.")
    if len(rows) >= 5 and not re.search(r"\b(list|each|every|per order|individual)\b", q):
        for i, col in enumerate(columns):
            values = [r[i] for r in rows]
            if COUNT_COLUMN.search(col.lower()) and all(v == 1 for v in values):
                return ("Every group has exactly one row, so the query groups by a unique id "
                        "(such as order_id). Remove it from GROUP BY to aggregate across rows; "
                        "for one overall number, use no GROUP BY at all.")
    return ""


COUNT_COLUMN = re.compile(r"(^|_)(orders?|count|n|reviews?|items?)$")

# Text columns whose filter values can be checked against the real data.
VALUE_COLUMNS = ("category", "customer_state", "seller_state", "customer_city", "seller_city",
                 "order_status", "payment_type", "delivery_status")
LITERAL_FILTER = re.compile(
    r"\b(?:\w+\.)?(" + "|".join(VALUE_COLUMNS) + r")\s*(=|in\s*\()\s*('[^)]*)", re.I)


def unknown_values(sql: str, known: dict[str, set[str]]) -> str:
    """Error if the SQL filters a text column on a value that does not exist,
    suggesting the closest real value (e.g. 'Toys' -> 'toys')."""
    import difflib
    for col, op, rest in LITERAL_FILTER.findall(sql):
        values = known.get(col.lower())
        if not values:
            continue
        # "= 'x'" has one value; "IN ('x', 'y')" can have several.
        literals = re.findall(r"'([^']*)'", rest) if op.strip() != "=" else re.findall(r"^'([^']*)'", rest)
        lower = {v.lower(): v for v in values}
        for value in literals:
            if value in values:
                continue
            key = value.lower() if value.lower() in lower else next(
                iter(difflib.get_close_matches(value.lower(), lower, n=1, cutoff=0.75)), None)
            hint = f" Did you mean '{lower[key]}'?" if key else ""
            return (f"'{value}' is not a value of {col} in the data.{hint} Use the exact "
                    "value as stored (lowercase, English category names, two-letter states).")
    return ""
