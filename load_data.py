"""Load the Olist CSVs into a local DuckDB database (data/olist.duckdb)."""
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

    con.close()
    print(f"\nDatabase written to {DB_PATH}")


if __name__ == "__main__":
    main()
