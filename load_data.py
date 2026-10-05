"""Load the Olist CSVs into a local DuckDB database (data/olist.duckdb).

Also creates cleaned views that encode the data-quality decisions
documented in DESIGN.md, so the model doesn't have to re-derive them.
"""
import os
from pathlib import Path

import duckdb

# Resolved from this file, so it runs from any folder. OLIST_DATA_DIR / OLIST_DB
# point it at other CSVs or another database file (e.g. a variant dataset).
DATA_DIR = Path(os.getenv("OLIST_DATA_DIR", Path(__file__).resolve().parent / "data"))
DB_PATH = Path(os.getenv("OLIST_DB", DATA_DIR / "olist.duckdb"))

# Short table names are easier for a small model to use correctly.
TABLES = {
    "orders": "olist_orders_dataset.csv",
    "order_items": "olist_order_items_dataset.csv",
    "payments": "olist_order_payments_dataset.csv",
    "customers": "olist_customers_dataset.csv",
    "products": "olist_products_dataset.csv",
    "sellers": "olist_sellers_dataset.csv",
    "category_translation": "product_category_name_translation.csv",
    "reviews": "olist_order_reviews_dataset.csv",
}

VIEWS = {
    # One row per line item. Rules:
    #  - excludes canceled/unavailable orders (not real sales)
    #  - revenue = item price (freight kept separate; payments not used)
    #  - category falls back to Portuguese name, then 'unknown'
    #  - customer_unique_id identifies a person (customer_id is per order)
    "sales": """
        SELECT
            i.order_id,
            i.order_item_id,
            CAST(o.order_purchase_timestamp AS TIMESTAMP)          AS purchase_ts,
            year(CAST(o.order_purchase_timestamp AS TIMESTAMP))    AS purchase_year,
            quarter(CAST(o.order_purchase_timestamp AS TIMESTAMP)) AS purchase_quarter,
            month(CAST(o.order_purchase_timestamp AS TIMESTAMP))   AS purchase_month,
            o.order_status,
            o.order_status = 'delivered'                           AS is_delivered,
            c.customer_unique_id,
            c.customer_state,
            c.customer_city,
            i.seller_id,
            s.seller_state,
            s.seller_city,
            i.product_id,
            COALESCE(t.product_category_name_english,
                     p.product_category_name, 'unknown')           AS category,
            i.price                                                AS revenue,
            i.freight_value
        FROM order_items i
        JOIN orders o     ON o.order_id = i.order_id
        JOIN customers c  ON c.customer_id = o.customer_id
        JOIN sellers s    ON s.seller_id = i.seller_id
        LEFT JOIN products p             ON p.product_id = i.product_id
        LEFT JOIN category_translation t ON t.product_category_name = p.product_category_name
        WHERE o.order_status NOT IN ('canceled', 'unavailable')
    """,
    # One review per order: keep the latest answered one.
    "order_reviews": """
        SELECT order_id, review_score, review_creation_date
        FROM reviews
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY order_id ORDER BY review_answer_timestamp DESC
        ) = 1
    """,
    # One row per order (all statuses) for anything measured per order.
    # Rules:
    #  - only joins tables that are one row per order, or pre-aggregated to it,
    #    so nothing fans out (sellers, categories and payment types are left
    #    out on purpose: many orders have several of each)
    #  - is_late compares DATES: the estimate has no time of day, so an order
    #    delivered on the estimated day is on time. NULL if not delivered.
    #  - is_canceled is the 'canceled' status only; is_sale excludes canceled and
    #    unavailable orders, matching the sales view (use it for money questions)
    #  - order_revenue = item prices, matching sales.revenue when is_sale
    #  - review_score is NULL for orders without a review (AVG ignores it)
    "order_facts": """
        WITH items AS (
            SELECT order_id, COUNT(*) AS n_items, SUM(price) AS order_revenue,
                   SUM(freight_value) AS freight
            FROM order_items GROUP BY order_id
        ),
        pay AS (
            SELECT order_id, SUM(payment_value) AS payment_total
            FROM payments GROUP BY order_id
        )
        SELECT
            o.order_id,
            o.order_status,
            CAST(o.order_purchase_timestamp AS TIMESTAMP)          AS purchase_ts,
            year(CAST(o.order_purchase_timestamp AS TIMESTAMP))    AS purchase_year,
            quarter(CAST(o.order_purchase_timestamp AS TIMESTAMP)) AS purchase_quarter,
            month(CAST(o.order_purchase_timestamp AS TIMESTAMP))   AS purchase_month,
            o.order_status = 'delivered'                           AS is_delivered,
            o.order_status = 'canceled'                            AS is_canceled,
            -- Same rule as the sales view: canceled/unavailable orders are not sales.
            o.order_status NOT IN ('canceled', 'unavailable')      AS is_sale,
            CAST(o.order_approved_at AS TIMESTAMP)                 AS approved_ts,
            CAST(o.order_delivered_carrier_date AS TIMESTAMP)      AS carrier_ts,
            CAST(o.order_delivered_customer_date AS TIMESTAMP)     AS delivered_ts,
            CAST(o.order_estimated_delivery_date AS DATE)          AS estimated_date,
            CASE WHEN o.order_status = 'delivered'
                  AND o.order_delivered_customer_date IS NOT NULL
                 THEN CAST(o.order_delivered_customer_date AS DATE)
                      > CAST(o.order_estimated_delivery_date AS DATE)
            END                                                    AS is_late,
            -- Same rule as a label, so "late vs on time" can't absorb undelivered orders.
            CASE WHEN o.order_status = 'delivered'
                  AND o.order_delivered_customer_date IS NOT NULL
                 THEN CASE WHEN CAST(o.order_delivered_customer_date AS DATE)
                                > CAST(o.order_estimated_delivery_date AS DATE)
                           THEN 'late' ELSE 'on_time' END
            END                                                    AS delivery_status,
            CASE WHEN o.order_status = 'delivered'
                 THEN date_diff('day',
                                CAST(o.order_purchase_timestamp AS DATE),
                                CAST(o.order_delivered_customer_date AS DATE))
            END                                                    AS delivery_days,
            c.customer_unique_id,
            c.customer_state,
            c.customer_city,
            items.n_items,
            items.order_revenue,
            items.freight,
            pay.payment_total,
            r.review_score
        FROM orders o
        JOIN customers c          ON c.customer_id = o.customer_id
        LEFT JOIN items           ON items.order_id = o.order_id
        LEFT JOIN pay             ON pay.order_id = o.order_id
        LEFT JOIN order_reviews r ON r.order_id = o.order_id
    """,
}


def main():
    if DB_PATH.exists():
        DB_PATH.unlink()  # rebuild from scratch every time

    con = duckdb.connect(str(DB_PATH))
    for table, filename in TABLES.items():
        path = DATA_DIR / filename
        if not path.exists():
            raise SystemExit(f"Missing {path}. See README for how to download the data.")
        con.execute(
            f"CREATE TABLE {table} AS SELECT * FROM read_csv_auto('{path}', header=true)"
        )
        rows = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"{table:22s} {rows:>8,} rows")

    print()
    for view, sql in VIEWS.items():
        con.execute(f"CREATE VIEW {view} AS {sql}")
        rows = con.execute(f"SELECT COUNT(*) FROM {view}").fetchone()[0]
        print(f"view {view:17s} {rows:>8,} rows")

    # order_facts must have exactly one row per order, or per-order sums double count.
    orders, facts, ids = con.execute(
        "SELECT (SELECT COUNT(*) FROM orders), COUNT(*), COUNT(DISTINCT order_id) FROM order_facts"
    ).fetchone()
    if not orders == facts == ids:
        raise SystemExit(f"order_facts fan-out: {facts:,} rows, {ids:,} ids, {orders:,} orders")

    con.close()
    print(f"\nDatabase written to {DB_PATH}")


if __name__ == "__main__":
    main()
