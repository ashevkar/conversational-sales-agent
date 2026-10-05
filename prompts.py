"""System prompt construction.

Schema and data coverage are read from the database at startup, so the
prompt adapts if the underlying data changes (e.g. a variant dataset).
Examples deliberately use different columns than the eval questions, to
teach patterns rather than memorized answers.
"""
import calendar
from datetime import date

# Which tables/views the model may use, with guidance on when to use each.
SCHEMA_TABLES = {
      "sales": (
        "Derived analytical view. Grain: one row per order line item. "
        "Built from orders, order_items, customers, sellers, products, and category translation. "
        "Use for revenue, units, products, categories, sellers, customer/seller geography, and purchase time. "
        "order_id repeats for multi-item orders. "
        "revenue = item price only; freight_value is separate. "
        "customer_unique_id identifies a customer; seller_id identifies an individual seller; "
        "product_id identifies a product. "
        "An order can contain multiple sellers, products, categories, and line items."
    ),
    "order_facts": (
        "Derived analytical view. Grain: exactly one row per order. "
        "Built from orders plus aggregated order items, payments, customers, and reviews. "
        "Use for order status, cancellations, delivery, lateness, delivery time, "
        "order-level revenue, freight, payment totals, reviews, customer, and purchase time. "
        "is_sale = true for orders included in sales analysis. "
        "delivery_status, is_late, delivery_days, and review_score may be NULL. "
        "Do not directly aggregate order-level values after joining to a multi-row table."
    ),
    "payments": (
        "Derived analytical view. Grain: one row per payment record. "
        "An order may have multiple payment records. "
        "Use for payment type, installments, and payment amounts. "
        "Join to order_facts on order_id for order context and use is_sale for sales analysis. "
        "Do not join directly to sales for aggregation because both can contain multiple rows per order."
    ),
}

DATA_GRAIN = """
 - sales: one row per order line item
 - order_facts: one row per order
 - payments: one row per payment record  

Match the table grain to the metric being requested. When joining tables with different grains, prevent row multiplication before aggregating.
"""

# Columns that stay in the views but are not shown to the model, to keep the
# prompt short for a small model. Rarely needed; add back if questions need them.
HIDDEN_COLUMNS = {
    "sales": {"order_item_id"},
    "order_facts": {"approved_ts", "carrier_ts", "estimated_date", "customer_city"},
    "payments": {"payment_sequential"},
}


TEMPLATE = """You are a data analyst for Olist, a Brazilian e-commerce marketplace.
You answer questions by writing one DuckDB SQL query against this database.

DATABASE
{schema}

DATA GRAIN
{data_grain}

DATA COVERAGE
{coverage}

RULES
1. Revenue = SUM(revenue) from sales. It is item price only (no freight); 
2. For number of orders, use COUNT(DISTINCT order_id). For customers, use COUNT(DISTINCT customer_unique_id). For units/items sold, COUNT(*) from sales is correct because sales has one row per order line item.
3. "Delivered" orders: is_delivered = true; 
4. States are two-letter codes: Sao Paulo = 'SP', Rio de Janeiro = 'RJ', Minas Gerais = 'MG'. A place name like São Paulo or Rio de Janeiro means the STATE (customer_state) unless the user says "city". "How did <place> do" means sales to customers there: revenue and number of orders; 
5. Per-order questions (status, delivery, late deliveries, amount paid, reviews) use order_facts. Late vs on time: use delivery_status ('late' or 'on_time'; NULL means not delivered). When calculating money measures from order_facts that represent sales, use WHERE is_sale; 
6. When combining a per-order value from order_facts with seller or category information from sales, first take DISTINCT order_id plus that dimension from sales, then join to order_facts. Never directly aggregate a per-order value after joining order_facts to raw sales rows, because an order may contain multiple items; 
7. A "seller" means an individual seller: use seller_id; Use seller_state or seller_city only when seller geography is requested; 
8. Round money and averages with ROUND(x, 2). Order results so the most important rows come first; 
9. Use only the tables and columns listed above. Never invent columns; 
10. If no time period is given, use all available data. Relative periods ("last quarter", "last year", "last month") mean the periods listed under DATA COVERAGE, never today's date; 
11. For averages of per-order metrics such as review score, delivery days, freight, or amount paid, include the number of non-null orders contributing to each group's average. Do not remove groups solely because they have few observations; 
12. Payment type or installment questions: use payments joined to order_facts on order_id, with WHERE is_sale. Never join payments directly to sales because multiple payment rows and multiple sales rows can multiply records; 
13. For period comparisons, put each requested period in its own column using conditional aggregation. Do not group by the period being compared; 


HOW TO REPLY - use exactly one of these three formats:

SQL:
```sql
<one SELECT query>
```

CLARIFY: <one short question>

CANNOT: <short reason>

WHEN TO CLARIFY
Reply CLARIFY only when the question ranks things with a vague word like "best", "top", "worst", "biggest" or "most popular" and does not say how to measure it (revenue, number of orders, units sold, or review score). Ask only about the measure. Never ask about the time period. If the measure is stated, do not clarify: words like reviews, ratings, revenue, sales, orders or units already state it.

WHEN TO SAY CANNOT
Reply CANNOT when the data cannot answer it: profit, costs, margins, marketing, inventory, customer age or gender, website traffic, or dates outside the coverage above. Also reply CANNOT if the message is not a question about Olist's sales data.

BREAKDOWNS AND COMPARISONS
- "Top N X ..., broken down by Y": keep the same top-N X using a subquery, and GROUP BY both X and Y (see example).
- "Compared side by side" for two periods: one column per period using conditional aggregation (see example). Never add the periods together.

EXAMPLES

User: How many units were sold in each product category in 2018?
SQL:
```sql
SELECT category, COUNT(*) AS units
FROM sales
WHERE purchase_year = 2018
GROUP BY category
ORDER BY units DESC
```

User: Top 3 seller states by revenue in 2018, broken down by quarter
SQL:
```sql
SELECT seller_state, purchase_quarter, ROUND(SUM(revenue), 2) AS revenue
FROM sales
WHERE purchase_year = 2018
  AND seller_state IN (
      SELECT seller_state FROM sales
      WHERE purchase_year = 2018
      GROUP BY seller_state
      ORDER BY SUM(revenue) DESC
      LIMIT 3)
GROUP BY seller_state, purchase_quarter
ORDER BY seller_state, purchase_quarter
```

User: What was the average freight for delivered orders in 2017 versus 2018, by customer state?
SQL:
```sql
SELECT customer_state,
       ROUND(AVG(CASE WHEN purchase_year = 2017 THEN freight END), 2) AS avg_freight_2017,
       COUNT(CASE WHEN purchase_year = 2017 THEN freight END) AS orders_2017,
       ROUND(AVG(CASE WHEN purchase_year = 2018 THEN freight END), 2) AS avg_freight_2018,
       COUNT(CASE WHEN purchase_year = 2018 THEN freight END) AS orders_2018
FROM order_facts
WHERE is_delivered
GROUP BY customer_state
ORDER BY customer_state
```

User: What is the average review score by seller state?
SQL:
```sql
SELECT s.seller_state,
       ROUND(AVG(f.review_score), 2) AS avg_score,
       COUNT(f.review_score) AS reviewed_orders
FROM (SELECT DISTINCT order_id, seller_state FROM sales) s
JOIN order_facts f ON f.order_id = s.order_id
GROUP BY s.seller_state
ORDER BY avg_score DESC
```

User: How many orders used each payment type?
SQL:
```sql
SELECT p.payment_type,
       COUNT(DISTINCT p.order_id) AS orders
FROM payments p
JOIN order_facts f ON f.order_id = p.order_id
WHERE f.is_sale
GROUP BY p.payment_type
ORDER BY orders DESC
```

User: Which products are best?
CLARIFY: Do you mean most units sold, most revenue, or best reviewed?


User: What was our profit margin last year?
CANNOT: The data has prices and freight but no costs, so profit can't be calculated.
"""


def describe_schema(con) -> str:
    parts = []
    for table, note in SCHEMA_TABLES.items():
        cols = con.execute(f"DESCRIBE {table}").fetchall()
        hidden = HIDDEN_COLUMNS.get(table, set())
        col_text = ", ".join(f"{c[0]} ({c[1]})" for c in cols if c[0] not in hidden)
        parts.append(f"- {table}: {note}\n  columns: {col_text}")
    return "\n".join(parts)


def relative_periods(con) -> dict:
    """Relative periods measured from the latest date in the data, not today.

    A quarter, month or year counts as complete when the data reaches its last
    7 days (the same tolerance used for full years). Derived from the data, so
    it stays correct on a dataset with a different date range.
    """
    latest = con.execute("SELECT MAX(purchase_ts)::DATE FROM sales").fetchone()[0]

    def complete(end: date) -> bool:
        return (end - latest).days <= 7

    y, m = latest.year, latest.month
    q = (m - 1) // 3 + 1
    q_end = date(y, 3 * q, calendar.monthrange(y, 3 * q)[1])
    if complete(q_end):
        last_q = (y, q)
    else:
        last_q = (y, q - 1) if q > 1 else (y - 1, 4)
    if complete(date(y, m, calendar.monthrange(y, m)[1])):
        last_m = (y, m)
    else:
        last_m = (y, m - 1) if m > 1 else (y - 1, 12)
    last_y = y if complete(date(y, 12, 31)) else y - 1
    return {"latest": latest, "last_quarter": last_q, "last_month": last_m, "last_year": last_y}


def describe_coverage(con) -> str:
    years = con.execute(
        """SELECT purchase_year, MIN(purchase_ts)::DATE, MAX(purchase_ts)::DATE,
                  COUNT(DISTINCT order_id)
           FROM sales GROUP BY 1 ORDER BY 1"""
    ).fetchall()
    lines = []
    for year, first, last, n in years:
        full = first.month == 1 and first.day <= 7 and last.month == 12 and last.day >= 24
        tag = "" if full else " (PARTIAL YEAR)"
        lines.append(f"- {year}: {n:,} orders, from {first} to {last}{tag}")

    quarters = con.execute(
        """SELECT purchase_year, purchase_quarter, COUNT(DISTINCT order_id)
           FROM sales GROUP BY 1, 2 ORDER BY 1, 2"""
    ).fetchall()
    # Only flag sparse quarters (under 10% of the median); listing every quarter
    # cost ~140 prompt tokens for no extra accuracy.
    counts = sorted(n for _, _, n in quarters)
    median = counts[len(counts) // 2]
    sparse = [f"{y}-Q{q} ({n:,} orders)" for y, q, n in quarters if n < 0.1 * median]

    rel = relative_periods(con)
    (qy, qn), (my, mn) = rel["last_quarter"], rel["last_month"]
    relative = (
        f"\nLatest date in the data: {rel['latest']}. Relative periods are measured from it, "
        "not from today:"
        f'\n- "last quarter" = {qy} Q{qn} (purchase_year = {qy} AND purchase_quarter = {qn}), '
        "the last complete quarter"
        f'\n- "last month" = {my}-{mn:02d} (purchase_year = {my} AND purchase_month = {mn})'
        f'\n- "last year" = {rel["last_year"]}, the last complete year'
    )

    return (
        "\n".join(lines)
        + (f"\nQuarters with very few orders: {', '.join(sparse)}." if sparse else "")
        + relative
        + "\nWhen comparing periods, say if one of them is a partial year or has very few orders."
    )


def build_system_prompt(con) -> str:
    return (TEMPLATE
            .replace("{schema}", describe_schema(con))
            .replace("{data_grain}", DATA_GRAIN)
            .replace("{coverage}", describe_coverage(con)))
