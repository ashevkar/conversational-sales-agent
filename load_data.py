"""Load the Olist CSVs into a local DuckDB database (data/olist.duckdb).

Also creates cleaned views that encode the data-quality decisions
documented in DESIGN.md, so the model doesn't have to re-derive them.
"""
from pathlib import Path

import duckdb

DATA_DIR = Path("data")
DB_PATH = DATA_DIR / "olist.duckdb"

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

    con.close()
    print(f"\nDatabase written to {DB_PATH}")


if __name__ == "__main__":
    main()
